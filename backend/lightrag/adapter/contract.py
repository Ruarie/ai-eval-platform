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


def map_chunks(payload: dict, kb_id: str, top_k: int) -> list[dict]:
    """把 ``aquery_data`` 结果映射为平台上下文列表。

    返回 ``[{id, doc_id, doc_name, text, reference_id}]``，保持 LightRAG 的
    召回排序；``kb_id`` 非空时只保留该知识库的切块，并截断到 ``top_k``。
    来源标识非法的切块无法归属知识库：指定知识库时被过滤，未指定时作为纯文本
    上下文返回，但不参与命中判定。
    """
    data = (payload or {}).get("data") or {}
    chunks = data.get("chunks") or []

    items: list[dict] = []
    seen: set[str] = set()
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
            chunk_uid = f"{doc_id or 'chunk'}#{len(items) + 1}"
        if chunk_uid in seen:
            continue
        seen.add(chunk_uid)
        items.append(
            {
                "id": chunk_uid,
                "doc_id": doc_id,
                "doc_name": filename or doc_id,
                "text": str(chunk.get("content") or ""),
                "reference_id": str(chunk.get("reference_id") or ""),
            }
        )
        if len(items) >= max(1, int(top_k or 1)):
            break
    return items
