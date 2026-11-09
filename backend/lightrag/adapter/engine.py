"""LightRAG 引擎封装：真正的写入、删除、状态与检索能力。

设计要点（对应《AI测试与评估平台-LightRAG接入技术方案.md》）：

1. **单实例多知识库**：一个容器一个 LightRAG 工作区，知识库隔离靠文档来源
   标识 ``{kb_id}__{doc_id}__{filename}`` 前缀过滤；LightRAG 的 query 本身
   不支持按文档过滤，因此召回候选窗口在指定知识库时放大（见
   :func:`contract.chunk_top_k_for`）。
2. **写入异步化**：实体/关系抽取需要多次 LLM 调用，单篇长文档可能耗时数分钟。
   接口层只负责受理，真正的 ``ainsert`` 在后台任务里按配置并发执行，状态通过
   LightRAG 自己的 doc_status 回读，平台据此展示 indexing / indexed / failed。
3. **诚实降级**：引擎未配置或调用失败时抛 :class:`EngineUnavailable`，由接口层
   返回 503；禁止返回空结果冒充「检索成功」。

约束：引擎状态在进程内（队列、锁、失败表）且存储为单写入者模型，因此适配服务
必须按「单容器、单 uvicorn worker」部署；多副本共享同一数据目录会损坏图与向量库。
"""

from __future__ import annotations

import asyncio
import logging
import time
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
# 「引擎在处理、但本进程没有对应任务」的观察窗口：重启后 LightRAG 会从
# doc_status 恢复未完成的抽取，此刻本地任务表是空的，立刻判 failed 会把
# 正在恢复的文档误报成失败；超过该窗口仍无进展才认定中断残留。
_STALE_GRACE_S = 180.0


def _placeholder_key(api_key: str) -> str:
    """OpenAI SDK 要求密钥为非空字符串；本地无鉴权网关用占位值，不伪造真实凭据。"""
    return api_key.strip() or "EMPTY"


_LANGUAGE_HINT = """

---Output Language---
- The input text is usually Chinese. Keep every entity name and both relation
  endpoints EXACTLY as they appear in the text (do not translate them into
  English, do not normalise them to another language).
- Write entity descriptions, relation descriptions and keywords in the same
  language as the input text.
"""


def localize_prompts() -> None:
    """给抽取 prompt 追加语言约束，避免中文语料被抽成英文实体。

    LightRAG 默认 prompt 是英文，模型会把「房间」「账号B」翻译成 ``Room`` /
    ``Account B``，同一概念还会因语言不一致被拆成多个节点（图谱碎片化）。
    这里只在 system prompt 末尾追加语言要求，不动输出格式说明与示例，
    保证与原解析器兼容。
    """
    from lightrag.prompt import PROMPTS

    for key in ("entity_extraction_system_prompt", "entity_extraction_json_system_prompt"):
        base = PROMPTS.get(key) or ""
        if base and "---Output Language---" not in base:
            PROMPTS[key] = base + _LANGUAGE_HINT


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
        # 管线并发：LightRAG 的 max_parallel_insert 只有在多个 ainsert 并发时才生效，
        # 旧实现用单把锁把文档串起来，配置调大也不会提速。用信号量按配置放行。
        self._pipeline_slots = asyncio.Semaphore(max(1, int(self.config.max_parallel_insert)))
        # 已受理但尚未写入 doc_status 的文档，用于「受理后立刻查询」的状态兜底。
        self._queued: set[str] = set()
        # 后台任务引用集合，防止任务被 GC 提前回收。
        self._tasks: set[asyncio.Task] = set()
        # 受理即失败（连入队都没成功）的文档，避免状态永远停在 indexing；
        # 用有序字典做容量上限，避免长期运行后无界增长。
        self._failed: OrderedDict[str, str] = OrderedDict()
        # 无本地任务却仍在 processing 的首见时间，用于判断是"重启恢复"还是"残留"。
        self._stale_since: dict[str, float] = {}

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

        # 先本地化抽取 prompt，再建引擎实例（引擎在调用期读取 PROMPTS）。
        localize_prompts()
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
            # LightRAG 内部默认 240s，会先于 openai client 的 timeout 触发失败。
            default_llm_timeout=int(self.config.llm_timeout_s),
            # 输出语言：默认 English 会把中文实体翻译成英文，图谱因此中英混杂。
            addon_params={"language": self.config.output_language},
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
        # 同一 doc_id 重复受理直接返回 indexing：已经在队列里再建任务会让两个
        # ainsert 串行写同一份文档，后一个还会被内容哈希判重而报错。
        if doc_id in self._queued:
            logger.info("文档已在索引队列中，忽略重复受理 doc_id=%s", doc_id)
            return {"doc_id": doc_id, "status": "indexing"}
        # 排队文档的正文驻留内存，必须设上限；超限让平台落 failed 后由用户重试，
        # 而不是把容器推到 OOM。
        limit = max(1, self.config.max_queue_documents)
        if len(self._queued) >= limit:
            raise EngineBusy(f"索引队列已满（{limit}），请稍后重试")

        file_source = build_file_source(kb_id, doc_id, filename)
        self._queued.add(doc_id)
        self._failed.pop(doc_id, None)
        self._stale_since.pop(doc_id, None)

        async def _worker() -> None:
            try:
                async with self._pipeline_slots:
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
        async with self._pipeline_slots:
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
                self._stale_since.pop(doc_id, None)
                results[doc_id] = str(getattr(result, "status", "") or "")
        # not_found 属幂等场景：平台侧记录已删除，引擎无残留即可。
        deleted = all(status in {"success", "not_found"} for status in results.values())
        return {"deleted": deleted, "results": results}

    async def document_statuses(self, doc_ids: list[str]) -> dict[str, str]:
        """批量回读文档索引状态，返回 ``{doc_id: 平台三态}``。

        - 引擎有记录：按 doc_status 映射；
        - 引擎无记录但本进程正在排队/抽取：仍为 indexing；
        - 引擎无记录且本进程没有任务：内容哈希被判重复（LightRAG 会把重复文档
          合并到原文档、不为新 doc_id 建记录）或上次进程中断，返回 failed，
          否则平台会永远停在 indexing 并让前端无限轮询。
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
                # 引擎没有记录（内容重复被合并 / 已删除）：清掉观察窗口，避免残留。
                self._stale_since.pop(doc_id, None)
                result[doc_id] = STATUS_INDEXING if doc_id in self._queued else STATUS_FAILED
                continue
            engine_status = getattr(record, "status", None)
            if engine_status is None and isinstance(record, dict):
                engine_status = record.get("status")
            mapped = map_engine_status(
                str(getattr(engine_status, "value", engine_status) or "")
            )
            if mapped == STATUS_INDEXING and doc_id not in self._queued:
                # 引擎报 pending/processing 但本进程没有对应任务：可能是重启后
                # LightRAG 正在恢复抽取（正常），也可能是上一次抽取被硬中断（残留）。
                # 给一个观察窗口，窗口内仍按 indexing 返回；超时无进展才判 failed，
                # 避免把重启后正在恢复的文档误报成失败。
                first_seen = self._stale_since.setdefault(doc_id, time.monotonic())
                if time.monotonic() - first_seen >= _STALE_GRACE_S:
                    mapped = STATUS_FAILED
            else:
                self._stale_since.pop(doc_id, None)
            result[doc_id] = mapped
        return result

    # ─── 检索 ─────────────────────────────────────────────────────────

    async def query(
        self, query: str, mode: str, top_k: int, kb_id: str = ""
    ) -> dict[str, Any]:
        """执行一次只有检索、不生成答案的查询，并映射为平台上下文结构。"""
        rag = self._require_rag()
        from lightrag import QueryParam

        window = chunk_top_k_for(kb_id, top_k)
        param = QueryParam(
            mode=mode,
            only_need_context=True,
            # 平台不配置 rerank 模型，显式关闭以免 LightRAG 每次检索都告警。
            enable_rerank=False,
            top_k=self.config.entity_top_k,
            chunk_top_k=window,
        )
        contexts = await self._retrieve(rag, query, param, kb_id, top_k, mode)
        # 过滤后明显不足（低于一半）：多库共享同一向量库/图谱时，目标库的切块
        # 容易被其它库挤出候选窗口。只在召回明显偏少时扩窗，否则「少 1 条」也会
        # 触发一次完整重查（关键词抽取 + 向量检索），检索成本翻倍。
        needed = max(1, int(top_k or 1) // 2)
        if kb_id and len(contexts) < needed and window < 200:
            param.chunk_top_k = min(max(window * 3, 60), 200)
            wider = await self._retrieve(rag, query, param, kb_id, top_k, mode)
            # 扩窗结果更少时保留首次结果：重取不应让已有召回倒退。
            if len(wider) > len(contexts):
                contexts = wider
        contexts = await self._attach_similarity(query, contexts)
        return {
            "text": "",
            "contexts": contexts,
            "mode": mode,
            "engine": "lightrag",
            "engine_version": self._version,
        }

    async def _retrieve(
        self,
        rag: Any,
        query: str,
        param: Any,
        kb_id: str,
        top_k: int,
        mode: str,
    ) -> list[dict]:
        """调用引擎并把结果映射为平台上下文；失败统一转引擎不可用。"""
        try:
            payload = await rag.aquery_data(query, param=param)
        except Exception as exc:  # noqa: BLE001 - 统一转引擎不可用
            logger.warning("LightRAG 检索失败 mode=%s err=%s", mode, type(exc).__name__)
            raise EngineUnavailable("LightRAG 检索失败") from exc
        return map_chunks(
            payload, kb_id, top_k, max_per_doc=self.config.max_chunks_per_doc
        )

    async def _attach_similarity(self, query: str, contexts: list[dict]) -> list[dict]:
        """用与索引一致的 embedding 模型补算 query↔chunk 余弦相似度。

        LightRAG 的 ``aquery_data`` 只给排序不给分数，平台此前把 ``similarity``
        填 null。这里复用引擎同一个 embedding 函数补算，前端能显示真实分数；
        补算失败时保持 null，不影响召回顺序（不重排，避免破坏图检索语义）。
        """
        if not contexts:
            return contexts
        try:
            vectors = await self._require_rag().embedding_func(
                [query] + [item["text"] for item in contexts]
            )
        except Exception:  # noqa: BLE001 - 分数是增强信息，失败不阻断检索
            logger.warning("检索相似度补算失败，similarity 保持为空", exc_info=True)
            return contexts
        try:
            import numpy as np

            matrix = np.asarray(vectors, dtype=float)
            base = matrix[0]
            base_norm = float(np.linalg.norm(base)) or 1.0
            for item, vector in zip(contexts, matrix[1:]):
                norm = float(np.linalg.norm(vector)) or 1.0
                score = float(np.dot(base, vector) / (base_norm * norm))
                item["similarity"] = round(max(0.0, min(1.0, score)), 4)
        except Exception:  # noqa: BLE001 - 维度异常等只影响分数
            logger.warning("检索相似度计算失败", exc_info=True)
        return contexts

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
