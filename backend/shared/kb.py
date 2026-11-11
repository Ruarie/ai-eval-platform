"""知识库域共享工具：文本切块、检索与检索指标计算（api / worker 共用）。

检索与索引统一走 ``backend/lightrag`` 适配服务（真实 LightRAG 引擎）：

- 上传文档 → ``POST /documents/index`` 受理建索引（异步抽取），状态由
  ``/documents/status`` 回读，平台据此展示 indexing / indexed / failed；
- 删除文档 → ``POST /documents/delete`` 清掉切块与图谱元素；
- 检索 → ``POST /query``（naive/local/global/hybrid），按知识库来源前缀过滤。

**降级口径**：只有「未配置 / 不可达 / 5xx」才回退本地关键词检索，并在报告里
标注 ``degraded``；引擎可用但召回为空属于真实「未命中」，仍按 lightrag 记账，
不得用本地兜底掩盖引擎状态（AGENTS.md §5.2 第 5 条）。
"""

import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger("ai-eval.kb")

# 检索返回的最大切块数上限（对齐前端 k ≤ 20 约束）
MAX_K = 20
# 检索默认 Top-K
DEFAULT_K = 5
# 单次切块预览的最大分块数，防止超大文档一次生成海量切块
MAX_CHUNK_PREVIEW = 200
# 三类调用的超时各自独立：单一变量会把删除超时改小、把建索引受理超时放大。
# 检索：hybrid/local/global 模式内部先做一轮关键词抽取，2 秒级别的旧 stub 超时
# 会把正常检索误判为不可用。
LIGHTRAG_QUERY_TIMEOUT_S = 60.0
# 建索引受理：接口只负责入队，返回很快；超时说明服务异常。
LIGHTRAG_INDEX_TIMEOUT_S = 15.0
# 状态回读：只查 doc_status，不应长时间阻塞文档列表。
LIGHTRAG_STATUS_TIMEOUT_S = 15.0
# 删除索引：删除会重建受影响实体的图谱摘要，整库删除可能跨数分钟。
LIGHTRAG_DELETE_TIMEOUT_S = 120.0
# 图谱读取：只读子图，但大图序列化明显慢于状态查询，单独给一个超时。
LIGHTRAG_GRAPH_TIMEOUT_S = 30.0
# 单次图谱返回的节点上限（与 API 契约一致）。
MAX_GRAPH_LIMIT = 2000
# 单次请求携带的文档 ID 上限：避免整库删除/状态回读被服务端或代理截断。
DOC_BATCH_SIZE = 50
STATUS_BATCH_SIZE = 200


def _lightrag_base_url() -> str:
    """读取 LightRAG 服务地址；未配置时返回空串表示禁用上游。"""
    return os.environ.get("LIGHTRAG_BASE_URL", "").strip()


def _lightrag_timeout(env_name: str, default: float, legacy: str = "") -> float:
    """读取指定环境变量覆盖该类调用的超时（非法值回退默认）。

    ``legacy`` 指向旧版单一变量（``LIGHTRAG_TIMEOUT_SECONDS``）：只有检索沿用它，
    删除与建索引必须使用各自的默认值，否则调小检索超时会连带缩短删除窗口。
    """
    names = [env_name] + ([legacy] if legacy else [])
    for name in names:
        raw = os.environ.get(name, "").strip()
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if value > 0:
            return value
    return default


def _batched(items: list[str], size: int) -> list[list[str]]:
    """按固定大小切分 ID 列表；``size`` 非法时退化为单批。"""
    step = size if size and size > 0 else len(items) or 1
    return [items[i : i + step] for i in range(0, len(items), step)]


def _query_timeout() -> float:
    """检索超时：优先新变量，兼容旧版 ``LIGHTRAG_TIMEOUT_SECONDS``。"""
    return _lightrag_timeout(
        "LIGHTRAG_QUERY_TIMEOUT_SECONDS", LIGHTRAG_QUERY_TIMEOUT_S, legacy="LIGHTRAG_TIMEOUT_SECONDS"
    )


def _lightrag_headers() -> dict:
    """构造调用适配服务的请求头；内部口令仅走容器内网，不落日志。"""
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("LIGHTRAG_API_KEY", "").strip()
    if token:
        headers["X-API-Key"] = token
    return headers


def _lightrag_post(path: str, payload: dict, timeout: float) -> dict | None:
    """POST 调用适配服务；不可达、未配置或返回 5xx 时返回 None。"""
    base = _lightrag_base_url()
    if not base:
        return None
    request = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=_lightrag_headers(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        # 只记录路径与结果，不打上游响应正文，避免把引擎细节或密钥带进日志。
        logger.warning("LightRAG 调用失败 path=%s，由调用方按降级口径处理", path)
        return None


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 64,
    doc_id: str = "d",
    limit: int = MAX_CHUNK_PREVIEW,
) -> list[dict]:
    """按字符滑动窗口切块，返回 ``[{chunk_id, doc_id, text, tokens}]``。

    ``chunk_id`` 形如 ``{doc_id}#c01``，与前端「切块流」契约一致。
    ``tokens`` 按字符数粗估（中文一字一 token 的近似）。
    """
    chunk_size = max(64, min(int(chunk_size or 512), 24_000))
    overlap = max(0, min(int(overlap or 0), chunk_size - 1))
    step = chunk_size - overlap

    raw = text or ""
    chunks: list[dict] = []
    start = 0
    n = 0
    while start < len(raw) and n < limit:
        seg = raw[start : start + chunk_size]
        if not seg:
            break
        n += 1
        chunks.append(
            {
                "chunk_id": f"{doc_id}#c{n:02d}",
                "doc_id": doc_id,
                "text": seg,
                "tokens": len(seg),
            }
        )
        start += step
    if not chunks and raw:
        chunks.append(
            {"chunk_id": f"{doc_id}#c01", "doc_id": doc_id, "text": raw, "tokens": len(raw)}
        )
    return chunks


def _query_terms(query: str) -> list[str]:
    """把查询拆成检索词元：拉丁词 + 中文相邻字符二元组。"""
    text = (query or "").strip()
    if not text:
        return []
    terms: list[str] = re.findall(r"[A-Za-z0-9_]+", text.lower())
    han = re.findall(r"[\u4e00-\u9fff]+", text)
    for run in han:
        if len(run) == 1:
            terms.append(run)
        else:
            terms.extend(run[i : i + 2] for i in range(len(run) - 1))
    return [t for t in terms if t]


def _score_chunk(chunk_text_: str, terms: list[str]) -> float:
    """词元命中比例打分：命中词元数 / 总词元数，落在 [0, 1]。"""
    if not terms:
        return 0.0
    low = chunk_text_.lower()
    hits = sum(1 for t in terms if t in low)
    return hits / len(terms)


def _try_lightrag(kb_id: str, query: str, mode: str, k: int) -> list[dict] | None:
    """调用适配服务 ``/query``；返回映射后的上下文列表，不可用返回 None。

    注意与旧 stub 的差别：引擎可用但召回为空时返回空列表（真实未命中），
    只有未配置 / 不可达 / 5xx 才返回 None 触发本地兜底。
    """
    data = _lightrag_post(
        "/query",
        {"query": query, "mode": mode or "hybrid", "top_k": min(k, MAX_K), "kb_id": kb_id},
        timeout=_query_timeout(),
    )
    if data is None:
        return None
    items: list[dict] = []
    for ctx in data.get("contexts") or []:
        if not isinstance(ctx, dict):
            continue
        chunk_id = str(ctx.get("id") or "")
        if not chunk_id:
            continue
        # 适配层直接给出平台 doc_id；缺失时退化为按切块 ID 前缀解析（兼容旧数据）。
        doc_id = str(ctx.get("doc_id") or "") or chunk_id.split("#", 1)[0]
        # 适配层用同一 embedding 模型补算了余弦分数；拿不到时保持 None，
        # 前端显示占位符，绝不用 0 冒充真实相似度。
        raw_score = ctx.get("similarity")
        similarity = (
            round(float(raw_score), 4)
            if isinstance(raw_score, int | float) and not isinstance(raw_score, bool)
            else None
        )
        items.append(
            {
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "doc_name": str(ctx.get("doc_name") or "") or doc_id,
                "text": str(ctx.get("text") or ""),
                "similarity": similarity,
            }
        )
    return items


def index_document(kb_id: str, doc_id: str, filename: str, text: str) -> dict:
    """请求适配服务为文档建索引（异步受理），受理失败时重试一次。

    返回 ``{"accepted": bool, "status": "indexing"|"failed"}``：适配服务不可用
    或拒绝受理时为 ``failed``，由调用方如实落库，禁止把未建索引的文档标成
    ``indexed``。

    引擎在抽取高峰会短暂超出 15s 受理窗口；单次超时即落 failed 会让用户只能
    重新上传。适配层对同一 doc_id 的重复受理是幂等的（``_queued`` 去重），
    因此这里可以安全重试一次。
    """
    if not (text or "").strip():
        return {"accepted": False, "status": "failed"}
    payload = {"kb_id": kb_id, "doc_id": doc_id, "filename": filename, "text": text}
    timeout = _lightrag_timeout("LIGHTRAG_INDEX_TIMEOUT_SECONDS", LIGHTRAG_INDEX_TIMEOUT_S)
    for attempt in range(2):
        data = _lightrag_post("/documents/index", payload, timeout=timeout)
        if data is not None and data.get("status") in {"indexing", "indexed", "failed"}:
            return {"accepted": data.get("status") != "failed", "status": data.get("status")}
        if attempt == 0:
            logger.warning("LightRAG 建索引受理失败，重试一次 kb_id=%s doc_id=%s", kb_id, doc_id)
            time.sleep(0.5)
    return {"accepted": False, "status": "failed"}


def delete_documents(kb_id: str, doc_ids: list[str]) -> bool:
    """请求适配服务删除文档索引；返回是否成功（未配置引擎视为无残留成功）。

    LightRAG 未配置时本就没有索引可删，按成功处理以免阻塞知识库维护；一旦
    配置了引擎，删除失败必须返回 False，由调用方中止并报错。删除会重建受影响
    实体的图谱摘要，属于长耗时操作，因此使用独立的超时。
    """
    ids = [str(doc_id) for doc_id in (doc_ids or []) if doc_id]
    if not ids:
        return True
    if not engine_available():
        return True
    timeout = _lightrag_timeout("LIGHTRAG_DELETE_TIMEOUT_SECONDS", LIGHTRAG_DELETE_TIMEOUT_S)
    # 整库删除可能有上千篇文档，单请求既可能超出服务端也会撞上代理超时，按批提交。
    for batch in _batched(ids, DOC_BATCH_SIZE):
        data = _lightrag_post(
            "/documents/delete",
            {"kb_id": kb_id, "doc_ids": batch},
            timeout=timeout,
        )
        if not data or not data.get("deleted"):
            logger.warning(
                "LightRAG 删除批次失败 kb_id=%s 本批=%d 已提交=%d", kb_id, len(batch), len(ids)
            )
            return False
    return True


def _fetch_status_batch(base: str, ids: list[str]) -> dict[str, str] | None:
    """回读一批文档状态；请求失败返回 None（调用方保留本地状态）。"""
    query = urllib.parse.urlencode({"doc_ids": ",".join(ids)})
    request = urllib.request.Request(
        f"{base.rstrip('/')}/documents/status?{query}",
        headers=_lightrag_headers(),
        method="GET",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=_lightrag_timeout("LIGHTRAG_STATUS_TIMEOUT_SECONDS", LIGHTRAG_STATUS_TIMEOUT_S),
        ) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        return None
    statuses: dict[str, str] = {}
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        doc_id = str(item.get("doc_id") or "")
        status = str(item.get("status") or "")
        if doc_id and status in {"indexing", "indexed", "failed"}:
            statuses[doc_id] = status
    return statuses


def document_statuses(doc_ids: list[str]) -> dict[str, str]:
    """批量回读引擎侧文档状态；不可用或未收录的 ID 不出现在结果中。

    按批提交，避免库内待索引文档超过单次上限时尾部永远无法收敛（前端会因此
    一直轮询）。某批失败即停止，已取到的批次照常返回，其余保留平台本地状态。
    """
    ids = [str(doc_id) for doc_id in (doc_ids or []) if doc_id]
    if not ids:
        return {}
    base = _lightrag_base_url()
    if not base:
        return {}
    statuses: dict[str, str] = {}
    for batch in _batched(ids, STATUS_BATCH_SIZE):
        part = _fetch_status_batch(base, batch)
        if part is None:
            logger.warning(
                "LightRAG 文档状态回读不可用，保留平台本地状态 已回读=%d 总数=%d",
                len(statuses),
                len(ids),
            )
            break
        statuses.update(part)
    return statuses


def engine_available() -> bool:
    """适配服务是否已配置（仅判断地址，不发起网络请求）。"""
    return bool(_lightrag_base_url())


def fetch_graph(kb_id: str, limit: int = 200) -> dict | None:
    """读取知识库的实体关系子图；不可用或响应异常时返回 None。

    与检索不同，这里**不做本地兜底**：图谱是引擎独有的产物，本地没有等价数据，
    伪造空图会把「引擎不可用」误导成「库里没有实体」，调用方应报 UPSTREAM。
    """
    data = _lightrag_post(
        "/graph",
        {"kb_id": kb_id, "limit": max(1, min(int(limit or 200), MAX_GRAPH_LIMIT))},
        timeout=_lightrag_timeout("LIGHTRAG_GRAPH_TIMEOUT_SECONDS", LIGHTRAG_GRAPH_TIMEOUT_S),
    )
    if not isinstance(data, dict):
        return None
    nodes: list[dict] = []
    for item in data.get("nodes") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        try:
            degree = int(item.get("degree") or 0)
        except (TypeError, ValueError):
            degree = 0
        nodes.append(
            {
                "id": str(item["id"]),
                "entity_type": str(item.get("entity_type") or ""),
                "description": str(item.get("description") or ""),
                "degree": degree,
                "doc_ids": [str(doc_id) for doc_id in (item.get("doc_ids") or []) if doc_id],
            }
        )
    edges: list[dict] = []
    for item in data.get("edges") or []:
        if not isinstance(item, dict) or not item.get("source") or not item.get("target"):
            continue
        try:
            weight = float(item.get("weight") if item.get("weight") is not None else 1.0)
        except (TypeError, ValueError):
            weight = 1.0
        edges.append(
            {
                "source": str(item["source"]),
                "target": str(item["target"]),
                "description": str(item.get("description") or ""),
                "weight": weight,
            }
        )
    return {
        "nodes": nodes,
        "edges": edges,
        "truncated": bool(data.get("truncated")),
        "engine": str(data.get("engine") or "lightrag"),
    }


def _local_retrieve(db, kb_id: str, query: str, k: int) -> list[dict]:
    """本地关键词检索：对库内文档正文切块后按词元命中比例取 top-k。"""
    from shared.models import KbDocument  # 延迟导入避免循环依赖

    docs = db.query(KbDocument).filter(KbDocument.kb_id == kb_id).all()
    terms = _query_terms(query)
    scored: list[dict] = []
    for doc in docs:
        for chunk in chunk_text(doc.text, chunk_size=512, overlap=64, doc_id=doc.id):
            score = _score_chunk(chunk["text"], terms)
            if score > 0:
                scored.append(
                    {
                        "chunk_id": chunk["chunk_id"],
                        "doc_id": doc.id,
                        "doc_name": doc.filename,
                        "text": chunk["text"],
                        "similarity": round(score, 4),
                    }
                )
    scored.sort(key=lambda item: item["similarity"], reverse=True)
    return scored[: min(k, MAX_K)]


# 检索引擎来源标识（报告诚实标注降级用）
RETRIEVE_SOURCE_LIGHTRAG = "lightrag"
RETRIEVE_SOURCE_LOCAL = "local"


def retrieve_with_source(
    db, kb_id: str, query: str, mode: str = "hybrid", k: int = 5
) -> tuple[list[dict], str]:
    """执行一次 Top-K 检索并返回引擎来源，供评测报告诚实标注降级。

    返回 ``(items, source)``：``source`` ∈ {lightrag, local}——适配服务可用
    （HTTP 2xx）即为 ``lightrag``，召回为空也算引擎的真实结论；只有未配置 /
    不可达 / 服务端错误才回退本地关键词检索并记 ``local``。评测报告必须据此
    区分引擎来源，禁止把本地兜底结果无标注地当作 LightRAG 引擎成绩对外呈现。
    """
    k = max(1, min(int(k or DEFAULT_K), MAX_K))
    items = _try_lightrag(kb_id, query, mode, k)
    if items is not None:
        return items, RETRIEVE_SOURCE_LIGHTRAG
    return _local_retrieve(db, kb_id, query, k), RETRIEVE_SOURCE_LOCAL


def retrieve(db, kb_id: str, query: str, mode: str = "hybrid", k: int = 5) -> list[dict]:
    """向后兼容封装：只返回 Top-K 检索结果，不暴露引擎来源（REST 目录等场景）。"""
    items, _ = retrieve_with_source(db, kb_id, query, mode=mode, k=k)
    return items


def compute_metrics(retrieved: list[dict], expected_doc_ids: list[str], reference: str = "") -> dict:
    """按「命中文档 ∈ 期望文档」计算单查询检索指标。

    返回 ``{hit_rate, mrr, recall, contain}``；无 expected_doc_ids 时各指标为 0
    （分母口径由调用方通过 ``hit_denominator_note`` 说明）。
    """
    expected = {str(e) for e in (expected_doc_ids or []) if e}
    hit_rate = mrr = recall = contain = 0.0
    if expected:
        hit_idx = next((i for i, item in enumerate(retrieved) if item.get("doc_id") in expected), None)
        if hit_idx is not None:
            hit_rate = 1.0
            mrr = 1.0 / (hit_idx + 1)
        hit_docs = {item.get("doc_id") for item in retrieved if item.get("doc_id") in expected}
        recall = len(hit_docs) / len(expected)
    if reference:
        contain = 1.0 if any((reference or "") in (item.get("text") or "") for item in retrieved) else 0.0
    return {
        "hit_rate": round(hit_rate, 4),
        "mrr": round(mrr, 4),
        "recall": round(recall, 4),
        "contain": round(contain, 4),
    }
