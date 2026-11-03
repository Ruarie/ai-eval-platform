"""适配服务的内部契约：文档来源标识、状态映射与检索结果映射（纯函数，无引擎依赖）。

平台与 LightRAG 之间唯一的稳定标识是「知识库 ID + 平台文档 ID」。LightRAG 的
``file_path`` 字段只保留最终 basename（``normalize_document_file_path`` 会剥掉
目录层级），因此不能把 ID 放在路径目录里，改用双下划线前缀：

    ``{kb_id}__{doc_id}__{原始文件名}``

UUID 不含 ``__``，因此按 ``__`` 最多拆三段即可稳定还原。写入时带上该标识，
检索时按 ``{kb_id}__`` 前缀过滤，从而在单实例多知识库共享同一图谱的情况下
实现按库隔离与 doc_id 还原。
"""

from __future__ import annotations

import re

# 平台文档状态（与 API.md §3.9 一致）
STATUS_INDEXING = "indexing"
STATUS_INDEXED = "indexed"
STATUS_FAILED = "failed"

# 来源标识分段符：UUID 不会出现连续双下划线，避免与文件名冲突。
_SOURCE_SEPARATOR = "__"

# LightRAG doc_status 取值 → 平台状态
_ENGINE_STATUS_MAP = {
    "pending": STATUS_INDEXING,
    "processing": STATUS_INDEXING,
    "processed": STATUS_INDEXED,
    "failed": STATUS_FAILED,
}

_UNSAFE_NAME = re.compile(r"[/\\\x00-\x1f]")

# LightRAG 在一个字段里用该分隔符连接多个来源（``GRAPH_FIELD_SEP``）。
# 这里重复声明而不 import lightrag，保证契约层可脱离引擎依赖做单测。
GRAPH_FIELD_SEP = "<SEP>"
# 单次图谱返回的节点上限（与 API 契约一致）。
MAX_GRAPH_NODES = 500
# 节点/关系描述来自多个切块摘要拼接，回传前截断，避免单次响应过大。
GRAPH_DESCRIPTION_LIMIT = 400


def sanitize_filename(filename: str) -> str:
    """把上传文件名收敛成单段安全名称（去掉路径分隔符与控制字符）。"""
    name = _UNSAFE_NAME.sub("_", (filename or "").strip())
    return name or "document"


def build_file_source(kb_id: str, doc_id: str, filename: str) -> str:
    """构造写入 LightRAG 的文档来源标识 ``{kb_id}__{doc_id}__{filename}``。

    分隔符是三段结构的唯一依据：``kb_id`` / ``doc_id`` 里出现 ``__`` 会让
    :func:`parse_file_source` 静默切错，因此在这里显式拒绝（当前两者均为 UUID）。
    """
    if not kb_id or not doc_id:
        raise ValueError("来源标识缺少知识库或文档 ID")
    for name, value in (("kb_id", kb_id), ("doc_id", doc_id)):
        if _SOURCE_SEPARATOR in value:
            raise ValueError(f"{name} 不能包含分隔符 {_SOURCE_SEPARATOR}")
    return f"{kb_id}{_SOURCE_SEPARATOR}{doc_id}{_SOURCE_SEPARATOR}{sanitize_filename(filename)}"


def parse_file_source(file_source: str) -> tuple[str, str, str]:
    """从来源标识还原 ``(kb_id, doc_id, filename)``；结构不符时返回空串三元组。"""
    parts = (file_source or "").split(_SOURCE_SEPARATOR, 2)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return "", "", ""
    filename = parts[2] if len(parts) > 2 else ""
    return parts[0], parts[1], filename


def belongs_to_kb(file_source: str, kb_id: str) -> bool:
    """判断来源标识是否属于指定知识库；``kb_id`` 为空表示不做过滤。"""
    if not kb_id:
        return True
    return (file_source or "").startswith(f"{kb_id}{_SOURCE_SEPARATOR}")


def map_engine_status(status: str | None) -> str:
    """把 LightRAG 文档状态映射成平台三态；未知状态按索引中处理（不谎报完成）。"""
    return _ENGINE_STATUS_MAP.get((status or "").strip().lower(), STATUS_INDEXING)


def chunk_top_k_for(kb_id: str, top_k: int) -> int:
    """计算召回候选数。

    单实例多库共享同一向量库时，按知识库过滤发生在召回之后，因此指定知识库
    时需要放大候选窗口，降低其它知识库结果挤占导致的召回损失；上限 60 与
    LightRAG 服务端 ``chunk_top_k`` 的合理区间一致。
    """
    k = max(1, int(top_k or 1))
    if not kb_id:
        return k
    return min(max(k * 4, 20), 60)


def map_chunks(payload: dict, kb_id: str, top_k: int, max_per_doc: int = 0) -> list[dict]:
    """把 ``aquery_data`` 结果映射为平台上下文列表。

    返回 ``[{id, doc_id, doc_name, text, reference_id}]``，保持 LightRAG 的
    召回排序；``kb_id`` 非空时只保留该知识库的切块，并截断到 ``top_k``。
    来源标识非法的切块无法归属知识库：指定知识库时被过滤，未指定时作为纯文本
    上下文返回，但不参与命中判定。

    ``max_per_doc > 0`` 时先按「每篇文档最多 N 条」做一轮配额，再补齐不足：
    平台指标是文档级的（Hit Rate / Recall），一篇长文档切出的多个相近切块
    占满 Top-K 会让其它文档永远进不了结果。
    """
    limit = max(1, int(top_k or 1))
    data = (payload or {}).get("data") or {}
    chunks = data.get("chunks") or []

    candidates: list[dict] = []
    seen_ids: set[str] = set()
    seen_text: set[str] = set()
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        file_path = str(chunk.get("file_path") or "")
        if not belongs_to_kb(file_path, kb_id):
            continue
        _, doc_id, filename = parse_file_source(file_path)
        chunk_uid = str(chunk.get("chunk_id") or "")
        # 来源标识结构不合法（旧数据或人工写入）时不参与指标命中判定，
        # 但仍作为纯文本上下文返回，避免静默丢弃真实召回。
        if not chunk_uid:
            chunk_uid = f"{doc_id or 'chunk'}#{len(candidates) + 1}"
        if chunk_uid in seen_ids:
            continue
        text = str(chunk.get("content") or "")
        # 相邻切块有重叠窗口，文本前缀相同视为同一段内容，避免重复占位。
        fingerprint = text[:80]
        if fingerprint and fingerprint in seen_text:
            continue
        seen_ids.add(chunk_uid)
        if fingerprint:
            seen_text.add(fingerprint)
        candidates.append(
            {
                "id": chunk_uid,
                "doc_id": doc_id,
                "doc_name": filename or doc_id,
                "text": text,
                "reference_id": str(chunk.get("reference_id") or ""),
            }
        )

    if max_per_doc <= 0:
        return candidates[:limit]

    selected: list[dict] = []
    counts: dict[str, int] = {}
    for item in candidates:
        key = item["doc_id"] or item["id"]
        if counts.get(key, 0) >= max_per_doc:
            continue
        counts[key] = counts.get(key, 0) + 1
        selected.append(item)
        if len(selected) >= limit:
            return selected
    # 配额导致不足时再放宽填满，保证召回数量不因多样性下降。
    chosen = {item["id"] for item in selected}
    for item in candidates:
        if item["id"] in chosen:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def parse_doc_ids(file_path: str, kb_id: str, separator: str = GRAPH_FIELD_SEP) -> list[str]:
    """从 LightRAG 的 ``file_path`` 字段解析出属于该知识库的文档 ID（去重保序）。

    实体/关系节点会把多个来源用 ``<SEP>`` 拼在一起，因此先拆分再逐个判定前缀，
    避免多库共享图谱时把其它知识库的实体算进来。
    """
    doc_ids: list[str] = []
    for item in str(file_path or "").split(separator):
        item = item.strip()
        if not item or not belongs_to_kb(item, kb_id):
            continue
        _, doc_id, _ = parse_file_source(item)
        if doc_id and doc_id not in doc_ids:
            doc_ids.append(doc_id)
    return doc_ids


def _graph_properties(item: dict) -> dict:
    """取节点/边的属性字典；结构异常时返回空字典。"""
    props = item.get("properties") if isinstance(item, dict) else None
    return props if isinstance(props, dict) else {}


def _graph_text(value: object, limit: int = GRAPH_DESCRIPTION_LIMIT) -> str:
    """把属性值收敛成受长度限制的文本（实体类型可能是列表）。"""
    if isinstance(value, list):
        text = ",".join(str(part) for part in value if part)
    else:
        text = str(value or "")
    text = text.strip()
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "…"


def _graph_weight(value: object) -> float:
    """边权重缺失或非法时按 1.0 处理，不臆造 0 权重。"""
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return 1.0


def map_graph(payload: dict, kb_id: str, limit: int) -> dict:
    """把 LightRAG 子图映射为平台图谱结构（按知识库过滤、按度截断）。

    返回 ``{nodes, edges, truncated, engine}``：

    - 实体/关系只保留来源标识以 ``{kb_id}__`` 开头的记录（单实例多库共享图谱）；
    - 节点按过滤后的度数降序排序，截断到 ``limit``；
    - 边只保留两端都在结果中的记录，避免前端出现悬空边。
    """
    limit = max(1, min(int(limit or 1), MAX_GRAPH_NODES))
    raw_nodes = (payload or {}).get("nodes") or []
    raw_edges = (payload or {}).get("edges") or []

    kept: dict[str, dict] = {}
    for node in raw_nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "")
        if not node_id:
            continue
        props = _graph_properties(node)
        doc_ids = parse_doc_ids(str(props.get("file_path") or ""), kb_id)
        # 指定知识库时，无法归属的实体直接过滤（属于其它知识库的抽取结果）。
        if kb_id and not doc_ids:
            continue
        kept[node_id] = {
            "id": node_id,
            "entity_type": _graph_text(props.get("entity_type"), 80),
            "description": _graph_text(props.get("description")),
            "doc_ids": doc_ids,
        }

    degree: dict[str, int] = {node_id: 0 for node_id in kept}
    links: list[dict] = []
    for edge in raw_edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in kept or target not in kept or source == target:
            continue
        degree[source] += 1
        degree[target] += 1
        props = _graph_properties(edge)
        links.append(
            {
                "source": source,
                "target": target,
                "description": _graph_text(props.get("description")),
                "weight": _graph_weight(props.get("weight")),
            }
        )

    ordered = sorted(kept.values(), key=lambda item: (-degree[item["id"]], item["id"]))
    nodes = [{**item, "degree": degree[item["id"]]} for item in ordered[:limit]]
    visible = {item["id"] for item in nodes}
    edges = [link for link in links if link["source"] in visible and link["target"] in visible]
    truncated = bool((payload or {}).get("is_truncated")) or len(ordered) > limit
    return {"nodes": nodes, "edges": edges, "truncated": truncated, "engine": "lightrag"}
