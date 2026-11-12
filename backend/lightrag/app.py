"""LightRAG 适配服务（平台内部契约层）。

职责边界：
- 上游是真实的 LightRAG（``lightrag-hku``，锁版本），负责图谱抽取与向量检索；
- 下游只对平台暴露一套稳定契约，平台其余代码不感知 LightRAG 的版本差异：

    GET  /health              引擎就绪状态、文档计数（不含密钥）
    POST /documents/index     受理建索引（异步执行，返回 indexing / failed）
    GET  /documents/status    批量回读文档状态（indexing / indexed / failed）
    POST /documents/delete    批量删除文档及其切块与图谱元素
    POST /query               检索（naive/local/global/hybrid），只返回上下文

平台只把检索结果当作「检索命中」，不把 LightRAG 伪装成 OpenAI Chat
（PRD F-RAG-01）。
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from adapter import (
    MAX_GRAPH_NODES,
    EngineBusy,
    EngineConfig,
    EngineUnavailable,
    LightRAGEngine,
    ensure_data_dir,
    load_config,
)
from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("lightrag.api")

# 平台四模式（PRD F-RAG-05）；mix/bypass 属 LightRAG 扩展能力，平台不开放。
ALLOWED_MODES = {"naive", "local", "global", "hybrid"}
MAX_TOP_K = 20
# 平台单文件上传上限 20MB：解码后的字符数按 UTF-8 上限不会超过字节数，这里留
# 20% 余量，避免恰好 20MB 的纯 ASCII 文档被判超限（否则表现为莫名 422 → failed）。
MAX_DOC_TEXT_CHARS = 24_000_000


class IndexRequest(BaseModel):
    """建索引请求：正文由平台提取后传入，适配层不解析原始文件。"""

    kb_id: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)
    filename: str = ""
    text: str = Field(min_length=1, max_length=MAX_DOC_TEXT_CHARS)

    @field_validator("text")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        """纯空白正文是请求错误（422），不是引擎不可用（503）。"""
        if not value.strip():
            raise ValueError("文档正文不能为空")
        return value


class DeleteRequest(BaseModel):
    """删除请求：按平台文档 ID 精确删除，支持一次删多篇（删除整个知识库）。"""

    kb_id: str = Field(min_length=1)
    doc_ids: list[str] = Field(min_length=1)


class ContextItem(BaseModel):
    """单条检索上下文：``id`` 为切块 ID，``doc_id`` 用于黄金 QA 命中判定。"""

    id: str
    doc_id: str = ""
    doc_name: str = ""
    text: str = ""
    reference_id: str = ""
    # 适配层用同一 embedding 模型补算的余弦分数；补算失败时为 null。
    similarity: float | None = None


class QueryRequest(BaseModel):
    """检索请求。"""

    query: str = Field(min_length=1)
    mode: str = "hybrid"
    top_k: int = Field(default=5, ge=1, le=MAX_TOP_K)
    # 指定知识库时按文档来源前缀过滤；留空表示全部知识库（仅调试用）。
    kb_id: str = ""
    # 是否补算 query↔chunk 余弦相似度：评测批量召回不需要分数，可关掉省一次向量调用。
    include_similarity: bool = True

    @field_validator("query")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        """纯空白检索词属于请求错误：引擎每次检索会先做一轮关键词抽取。"""
        if not value.strip():
            raise ValueError("检索词不能为空")
        return value


class GraphRequest(BaseModel):
    """知识图谱请求（只读）；``limit`` 为返回节点上限。"""

    kb_id: str = Field(min_length=1)
    limit: int = Field(default=200, ge=1, le=MAX_GRAPH_NODES)


class QueryResponse(BaseModel):
    """检索响应；``text`` 恒为空——平台按检索指标评测，不在此处生成答案。"""

    text: str = ""
    contexts: list[ContextItem] = Field(default_factory=list)
    mode: str = "hybrid"
    engine: str = "lightrag"
    engine_version: str = ""


_CONFIG: EngineConfig = load_config()
_ENGINE = LightRAGEngine(_CONFIG)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """启动时初始化引擎存储，退出时释放。"""
    ensure_data_dir(_CONFIG)
    try:
        await _ENGINE.start()
    except Exception:  # noqa: BLE001 - 启动失败保留进程以便 /health 如实报告
        logger.exception("LightRAG 引擎初始化失败，服务保持未就绪")
    yield
    await _ENGINE.stop()


app = FastAPI(title="LightRAG Adapter", version="1.0.0", lifespan=lifespan)


def _authorize(x_api_key: str | None) -> None:
    """内网鉴权：配置了口令就必须匹配，未配置则仅依赖 Compose 内网隔离。"""
    expected = _CONFIG.api_key
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/health")
async def health() -> dict[str, Any]:
    """健康检查：真实反映引擎是否可用，不做「活着就算健康」的假阳性。"""
    snapshot = await _ENGINE.health()
    return {"status": "ok" if snapshot.get("ready") else "degraded", **snapshot}


@app.post("/documents/index")
async def index_document(
    body: IndexRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """受理建索引：立即返回受理状态，长耗时抽取在后台串行执行。"""
    _authorize(x_api_key)
    ensure_data_dir(_CONFIG)
    try:
        return await _ENGINE.index_document(body.kb_id, body.doc_id, body.filename, body.text)
    except EngineBusy as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except EngineUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/documents/status")
async def documents_status(
    doc_ids: str = Query(default="", description="逗号分隔的平台文档 ID"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """批量回读文档状态；未收录的 ID 不出现在 items 中。"""
    _authorize(x_api_key)
    ids = [item.strip() for item in doc_ids.split(",") if item.strip()]
    # 平台侧按 200 分批，这里留一倍余量做防御性上限，避免单次查询过大。
    statuses = await _ENGINE.document_statuses(ids[:500])
    return {"items": [{"doc_id": key, "status": value} for key, value in statuses.items()]}


@app.post("/documents/delete")
async def delete_documents(
    body: DeleteRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """删除文档及其派生数据；不存在按幂等成功处理。"""
    _authorize(x_api_key)
    try:
        return await _ENGINE.delete_documents(body.kb_id, body.doc_ids)
    except EngineUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/query", response_model=QueryResponse)
async def query(
    body: QueryRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> QueryResponse:
    """执行检索：只做召回，不调用答案生成，控制评测成本。"""
    _authorize(x_api_key)
    mode = (body.mode or "hybrid").strip().lower()
    if mode not in ALLOWED_MODES:
        raise HTTPException(status_code=400, detail="unsupported query mode")
    try:
        result = await _ENGINE.query(
            body.query, mode, body.top_k, body.kb_id,
            include_similarity=body.include_similarity,
        )
    except EngineUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return QueryResponse(**result)


@app.post("/graph")
async def graph(
    body: GraphRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """读取当前知识库的实体关系子图；只读，不触发抽取或写入。"""
    _authorize(x_api_key)
    try:
        return await _ENGINE.graph(body.kb_id, body.limit)
    except EngineUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
