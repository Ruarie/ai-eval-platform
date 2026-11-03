"""LightRAG 引擎封装：真正的写入、删除、状态与检索能力。

设计要点（对应《AI测试与评估平台-LightRAG接入技术方案.md》）：

1. **单实例多知识库**：一个容器一个 LightRAG 工作区，知识库隔离靠文档来源
   标识 ``{kb_id}__{doc_id}__{filename}`` 前缀过滤；LightRAG 的 query 本身
   不支持按文档过滤，因此召回候选窗口在指定知识库时放大（见
   :func:`contract.chunk_top_k_for`）。
2. **写入异步化**：实体/关系抽取需要多次 LLM 调用，单篇长文档可能耗时数分钟。
   接口层只负责受理，真正的 ``ainsert`` 在后台任务里串行执行，状态通过
   LightRAG 自己的 doc_status 回读，平台据此展示 indexing / indexed / failed。
3. **诚实降级**：引擎未配置或调用失败时抛 :class:`EngineUnavailable`，由接口层
   返回 503；禁止返回空结果冒充「检索成功」。

约束：引擎状态在进程内（队列、锁、失败表）且存储为单写入者模型，因此适配服务
必须按「单容器、单 uvicorn worker」部署；多副本共享同一数据目录会损坏图与向量库。
"""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from functools import partial
from typing import Any

from .config import EngineConfig
from .contract import (
    MAX_GRAPH_NODES,
    STATUS_FAILED,
    STATUS_INDEXING,
    belongs_to_kb,
    build_file_source,
    chunk_top_k_for,
    map_chunks,
    map_engine_status,
    map_graph,
)

logger = logging.getLogger("lightrag.engine")

# 失败表上限：失败原因只需保留到平台回读一次，无界增长会缓慢泄漏。
_MAX_FAILED_RECORDS = 1000


def _placeholder_key(api_key: str) -> str:
    """OpenAI SDK 要求密钥为非空字符串；本地无鉴权网关用占位值，不伪造真实凭据。"""
    return api_key.strip() or "EMPTY"


def _record_file_path(record: Any) -> str:
    """读取 doc_status 记录里的来源标识；兼容对象与 dict 两种返回形态。"""
    if record is None:
        return ""
    value = getattr(record, "file_path", None)
    if value is None and isinstance(record, dict):
        value = record.get("file_path")
    return str(value or "")


class EngineUnavailable(RuntimeError):
    """LightRAG 引擎未就绪或本次调用失败（接口层转 503，平台侧据此标注降级）。"""


class EngineBusy(RuntimeError):
    """受理队列已满（接口层转 429，平台按 failed 落库，用户可稍后重试）。"""


class LightRAGEngine:
    """LightRAG 实例的生命周期与业务封装。"""

    def __init__(self, config: EngineConfig) -> None:
        self.config = config
        self._rag: Any = None
        self._version: str = ""
        # LightRAG 的写入/删除共用同一条管线（busy 时直接拒绝），必须串行。
        self._pipeline_lock = asyncio.Lock()
        # 已受理但尚未写入 doc_status 的文档，用于「受理后立刻查询」的状态兜底。
        self._queued: set[str] = set()
        # 后台任务引用集合，防止任务被 GC 提前回收。
        self._tasks: set[asyncio.Task] = set()
        # 受理即失败（连入队都没成功）的文档，避免状态永远停在 indexing；
        # 用有序字典做容量上限，避免长期运行后无界增长。
        self._failed: OrderedDict[str, str] = OrderedDict()

    # ─── 生命周期 ─────────────────────────────────────────────────────

    @property
    def ready(self) -> bool:
        """引擎是否已初始化成功（配置齐备且存储已就绪）。"""
        return self._rag is not None

    async def start(self) -> None:
        """构造并初始化 LightRAG；配置缺失时保持未就绪而不抛异常。"""
        if not self.config.ready:
            logger.warning(
                "LightRAG 引擎未配置，缺失项=%s；索引与检索将返回不可用",
                ",".join(self.config.missing),
            )
            return

        # 懒导入：缺依赖时容器仍可启动并如实报告未就绪，而不是直接崩溃。
        import lightrag as lightrag_pkg
        from lightrag import LightRAG
        from lightrag.llm.openai import openai_complete_if_cache, openai_embed
        from lightrag.utils import EmbeddingFunc

        self._version = str(getattr(lightrag_pkg, "__version__", ""))

        llm_func = self._build_llm_func(openai_complete_if_cache)
        embedding_func = EmbeddingFunc(
            embedding_dim=self.config.embedding_dim,
            max_token_size=self.config.embedding_max_tokens,
            # 已带 wrap 装饰的绑定函数用 .func 取原函数，避免重复包裹维度校验。
            func=partial(
                openai_embed.func,
                model=self.config.embedding_model,
                base_url=self.config.embedding_base_url,
                api_key=_placeholder_key(self.config.embedding_api_key),
                embedding_dim=self.config.embedding_dim,
                max_token_size=self.config.embedding_max_tokens,
            ),
        )

        rag = LightRAG(
            working_dir=self.config.data_dir,
            workspace=self.config.workspace,
            llm_model_func=llm_func,
            llm_model_name=self.config.llm_model,
            embedding_func=embedding_func,
            chunk_token_size=self.config.chunk_token_size,
            chunk_overlap_token_size=self.config.chunk_overlap_token_size,
            top_k=self.config.entity_top_k,
            max_parallel_insert=self.config.max_parallel_insert,
        )
        await rag.initialize_storages()
        self._rag = rag
        logger.info(
            "LightRAG 引擎已就绪 version=%s workspace=%s dir=%s",
            self._version,
            self.config.workspace,
            self.config.data_dir,
        )

    async def stop(self) -> None:
        """先给在建索引任务收尾窗口，超时再取消，最后释放存储。

        直接取消会把 LightRAG 的 doc_status 留在 ``processing``，重启后平台侧
        该文档永远停在 indexing；宽限期内完成的任务能正常写入 ``processed``。
        """
        pending = set(self._tasks)
        if pending:
            _, still_running = await asyncio.wait(pending, timeout=self.config.shutdown_grace_s)
            for task in still_running:
                task.cancel()
            if still_running:
                logger.warning("停机时仍有索引任务未完成，已取消 count=%d", len(still_running))
            await asyncio.gather(*pending, return_exceptions=True)
        if self._rag is not None:
            try:
                await self._rag.finalize_storages()
            except Exception:  # noqa: BLE001 - 收尾失败不阻塞进程退出
                logger.warning("LightRAG 存储收尾失败", exc_info=True)
            self._rag = None

    def _build_llm_func(self, complete_if_cache: Any) -> Any:
        """构造 LLM 调用函数；超时与模型参数在此统一注入，避免散落。"""
        model = self.config.llm_model
        base_url = self.config.llm_base_url
        api_key = _placeholder_key(self.config.llm_api_key)
        timeout = self.config.llm_timeout_s

        async def _complete(
            prompt: str,
            system_prompt: str | None = None,
            history_messages: list[dict[str, Any]] | None = None,
            **kwargs: Any,
        ) -> str:
            kwargs.setdefault("timeout", timeout)
            return await complete_if_cache(
                model,
                prompt,
                system_prompt=system_prompt,
                history_messages=history_messages or [],
                base_url=base_url,
                api_key=api_key,
                **kwargs,
            )

        return _complete

    def _require_rag(self) -> Any:
        """取引擎实例；未就绪时抛统一不可用异常。"""
        if self._rag is None:
            raise EngineUnavailable("LightRAG 引擎未就绪")
        return self._rag

    def _remember_failure(self, doc_id: str, reason: str) -> None:
        """登记失败原因；超过容量上限时淘汰最旧记录。"""
        self._failed[doc_id] = reason
        self._failed.move_to_end(doc_id)
        while len(self._failed) > _MAX_FAILED_RECORDS:
            self._failed.popitem(last=False)

    # ─── 文档索引 ─────────────────────────────────────────────────────

    async def index_document(
        self, kb_id: str, doc_id: str, filename: str, text: str
    ) -> dict[str, str]:
        """受理一篇文档的建索引请求并异步执行。

        返回 ``{"doc_id", "status"}``：受理成功为 ``indexing``；正文为空或引擎
        未就绪时明确返回 ``failed``，由平台如实落库。
        """
        rag = self._require_rag()
        if not (text or "").strip():
            raise EngineUnavailable("文档正文为空，无法建索引")
        # 排队文档的正文驻留内存，必须设上限；超限让平台落 failed 后由用户重试，
        # 而不是把容器推到 OOM。
        limit = max(1, self.config.max_queue_documents)
        if doc_id not in self._queued and len(self._queued) >= limit:
            raise EngineBusy(f"索引队列已满（{limit}），请稍后重试")

        file_source = build_file_source(kb_id, doc_id, filename)
        self._queued.add(doc_id)
        self._failed.pop(doc_id, None)

        async def _worker() -> None:
            try:
                async with self._pipeline_lock:
                    await rag.ainsert(
                        text,
                        ids=[doc_id],
                        file_paths=[file_source],
                        track_id=doc_id,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - 后台任务必须自兜底
                self._remember_failure(doc_id, type(exc).__name__)
                logger.warning(
                    "LightRAG 建索引失败 doc_id=%s err=%s", doc_id, type(exc).__name__
                )
            finally:
                self._queued.discard(doc_id)

        task = asyncio.create_task(_worker())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return {"doc_id": doc_id, "status": "indexing"}

    async def delete_documents(self, kb_id: str, doc_ids: list[str]) -> dict[str, Any]:
        """批量删除文档及其切块、图谱元素；不存在视为幂等成功。

        删除会重建受影响实体的摘要，单次串行执行以避免管线锁冲突；批量接口
        只发一次 HTTP 请求，减少删除整个知识库时的往返开销。
        """
        rag = self._require_rag()
        results: dict[str, str] = {}
        async with self._pipeline_lock:
            # 删除前核对来源前缀：平台侧已校验归属，这里再挡一次跨知识库误删。
            sources: dict[str, Any] = {}
            try:
                fetched = await rag.doc_status.get_full_docs_by_ids(list(doc_ids))
                sources = fetched if isinstance(fetched, dict) else {}
            except Exception:  # noqa: BLE001 - 校验失败不阻断删除，交给引擎按 ID 精确删
                logger.warning("删除前读取文档来源失败，跳过归属校验", exc_info=True)
            for doc_id in doc_ids:
                file_source = _record_file_path(sources.get(doc_id))
                if kb_id and file_source and not belongs_to_kb(file_source, kb_id):
                    logger.warning("拒绝跨知识库删除 doc_id=%s kb_id=%s", doc_id, kb_id)
                    results[doc_id] = "forbidden"
                    continue
                try:
                    result = await rag.adelete_by_doc_id(doc_id)
                except Exception as exc:  # noqa: BLE001 - 统一转引擎不可用
                    logger.warning(
                        "LightRAG 删除文档失败 doc_id=%s err=%s",
                        doc_id,
                        type(exc).__name__,
                    )
                    raise EngineUnavailable("LightRAG 删除文档失败") from exc
                self._queued.discard(doc_id)
                self._failed.pop(doc_id, None)
                results[doc_id] = str(getattr(result, "status", "") or "")
        # not_found 属幂等场景：平台侧记录已删除，引擎无残留即可。
        deleted = all(status in {"success", "not_found"} for status in results.values())
        return {"deleted": deleted, "results": results}

    async def document_statuses(self, doc_ids: list[str]) -> dict[str, str]:
        """批量回读文档索引状态，返回 ``{doc_id: 平台三态}``。

        只返回引擎确实有记录的文档；平台对未返回的 ID 保留自身状态，避免把
        「尚未受理」误判成失败。
        """
        if not doc_ids:
            return {}
        rag = self._rag
        if rag is None:
            return {}
        result: dict[str, str] = {}
        try:
            records = await rag.doc_status.get_full_docs_by_ids(doc_ids)
        except Exception:  # noqa: BLE001 - 状态回读失败不影响主流程
            logger.warning("LightRAG 文档状态回读失败", exc_info=True)
            records = {}
        for doc_id in doc_ids:
            if doc_id in self._failed:
                result[doc_id] = STATUS_FAILED
                continue
            record = records.get(doc_id) if isinstance(records, dict) else None
            if record is None:
                if doc_id in self._queued:
                    result[doc_id] = STATUS_INDEXING
                continue
            engine_status = getattr(record, "status", None)
            if engine_status is None and isinstance(record, dict):
                engine_status = record.get("status")
            mapped = map_engine_status(
                str(getattr(engine_status, "value", engine_status) or "")
            )
            if mapped == STATUS_INDEXING and doc_id not in self._queued:
                # 引擎报 pending/processing 但本进程没有对应任务：上次进程在抽取
                # 中途被中断，该文档不会再有进展。标 failed 让用户重传，而不是
                # 让它永远停在 indexing 并让前端无限轮询。
                mapped = STATUS_FAILED
            result[doc_id] = mapped
        return result

    # ─── 检索 ─────────────────────────────────────────────────────────

    async def query(
        self, query: str, mode: str, top_k: int, kb_id: str = ""
    ) -> dict[str, Any]:
        """执行一次只有检索、不生成答案的查询，并映射为平台上下文结构。"""
        rag = self._require_rag()
        from lightrag import QueryParam

        param = QueryParam(
            mode=mode,
            only_need_context=True,
            # 平台不配置 rerank 模型，显式关闭以免 LightRAG 每次检索都告警。
            enable_rerank=False,
            top_k=self.config.entity_top_k,
            chunk_top_k=chunk_top_k_for(kb_id, top_k),
        )
        try:
            payload = await rag.aquery_data(query, param=param)
        except Exception as exc:  # noqa: BLE001 - 统一转引擎不可用
            logger.warning("LightRAG 检索失败 mode=%s err=%s", mode, type(exc).__name__)
            raise EngineUnavailable("LightRAG 检索失败") from exc

        contexts = map_chunks(payload, kb_id, top_k)
        return {
            "text": "",
            "contexts": contexts,
            "mode": mode,
            "engine": "lightrag",
            "engine_version": self._version,
        }

    # ─── 知识图谱（只读） ──────────────────────────────────────────────

    async def graph(self, kb_id: str, limit: int = 200) -> dict[str, Any]:
        """读取当前知识库的实体关系子图。

        单实例多库共享同一图谱，过滤只能发生在召回之后，因此先按倍数取候选
        （与检索的 ``chunk_top_k`` 同一思路），再按文档来源前缀过滤并截断。
        """
        rag = self._require_rag()
        limit = max(1, min(int(limit or 1), MAX_GRAPH_NODES))
        fetch_nodes = min(max(limit * 5, 200), 1000)
        try:
            kg = await rag.get_knowledge_graph("*", max_depth=1, max_nodes=fetch_nodes)
        except Exception as exc:  # noqa: BLE001 - 统一转引擎不可用
            logger.warning("LightRAG 图谱读取失败 err=%s", type(exc).__name__)
            raise EngineUnavailable("LightRAG 图谱读取失败") from exc

        payload = {
            "nodes": [
                {"id": str(node.id), "properties": dict(node.properties or {})}
                for node in getattr(kg, "nodes", None) or []
            ],
            "edges": [
                {
                    "source": str(edge.source),
                    "target": str(edge.target),
                    "properties": dict(edge.properties or {}),
                }
                for edge in getattr(kg, "edges", None) or []
            ],
            "is_truncated": bool(getattr(kg, "is_truncated", False)),
        }
        return map_graph(payload, kb_id, limit)

    # ─── 健康检查 ─────────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        """返回不含密钥的引擎状态快照，供平台与运维判断是否真的可用。"""
        snapshot: dict[str, Any] = {
            "engine": "lightrag",
            "engine_version": self._version,
            "ready": self.ready,
            "configured": self.config.ready,
            "workspace": self.config.workspace,
            "data_dir": self.config.data_dir,
            "llm_model": self.config.llm_model,
            "embedding_model": self.config.embedding_model,
            "embedding_dim": self.config.embedding_dim,
            "chunk_token_size": self.config.chunk_token_size,
            "queued_documents": len(self._queued),
        }
        if not self.config.ready:
            snapshot["missing"] = self.config.missing
        if self._rag is not None:
            try:
                snapshot["documents"] = await self._rag.doc_status.get_status_counts()
            except Exception:  # noqa: BLE001 - 健康检查自身不能抛错
                snapshot["documents"] = {}
        return snapshot
