"""适配层引擎行为单测：用假 LightRAG 实例覆盖队列、停机、状态自愈与删除归属。

不依赖 ``lightrag-hku``：引擎只在 ``start()`` 里懒导入，这里直接注入假实例，
因此本文件可在普通 CI 环境运行。
"""

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest
from adapter.config import load_config
from adapter.engine import _MAX_FAILED_RECORDS, EngineBusy, EngineUnavailable, LightRAGEngine


class FakeDocStatus:
    """假 doc_status：按 doc_id 返回传入的记录。"""

    def __init__(self, records: dict[str, object] | None = None) -> None:
        self.records = records or {}

    async def get_full_docs_by_ids(self, doc_ids: list[str]) -> dict[str, object]:
        return {doc_id: self.records[doc_id] for doc_id in doc_ids if doc_id in self.records}


class FakeRag:
    """假 LightRAG：记录插入/删除调用，可配置阻塞或延迟。"""

    def __init__(
        self,
        records: dict[str, object] | None = None,
        *,
        block: bool = False,
        delay: float = 0.0,
        graph_nodes: list[object] | None = None,
        graph_edges: list[object] | None = None,
        graph_truncated: bool = False,
    ) -> None:
        self.doc_status = FakeDocStatus(records)
        self.inserted: list[str] = []
        self.deleted: list[str] = []
        self.cancelled = False
        self.graph_calls: list[tuple[str, int, int | None]] = []
        self._block = block
        self._delay = delay
        self._graph = SimpleNamespace(
            nodes=graph_nodes or [], edges=graph_edges or [], is_truncated=graph_truncated
        )

    async def ainsert(self, text: str, ids=None, file_paths=None, track_id=None) -> None:
        if self._block:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        if self._delay:
            await asyncio.sleep(self._delay)
        self.inserted.append((ids or [""])[0])

    async def adelete_by_doc_id(self, doc_id: str) -> SimpleNamespace:
        self.deleted.append(doc_id)
        return SimpleNamespace(status="success")

    async def get_knowledge_graph(
        self, node_label: str, max_depth: int = 3, max_nodes: int | None = None
    ) -> SimpleNamespace:
        self.graph_calls.append((node_label, max_depth, max_nodes))
        return self._graph


def _engine(**overrides) -> LightRAGEngine:
    """构造引擎并注入配置覆盖项（默认队列上限放宽，避免测试互相影响）。"""
    config = replace(load_config(), **{"max_queue_documents": 8, "shutdown_grace_s": 1.0, **overrides})
    return LightRAGEngine(config)


def test_queue_limit_rejects_overflow():
    """队列已满时返回 EngineBusy，接口层据此转 429，而不是继续占内存。"""

    async def case() -> None:
        engine = _engine(max_queue_documents=1)
        engine._rag = FakeRag(block=True)
        await engine.index_document("kb-1", "doc-a", "a.txt", "正文")
        await asyncio.sleep(0)  # 让任务进入阻塞态，doc-a 留在队列里
        try:
            await engine.index_document("kb-1", "doc-b", "b.txt", "正文")
        except EngineBusy:
            pass
        else:  # pragma: no cover - 触发即说明限额失效
            raise AssertionError("队列超限未拒绝")
        await engine.stop()

    asyncio.run(case())


def test_stop_waits_for_task_within_grace():
    """宽限期内完成的索引任务正常收尾，不被取消。"""

    async def case() -> None:
        engine = _engine(shutdown_grace_s=2.0)
        rag = FakeRag(delay=0.05)
        engine._rag = rag
        await engine.index_document("kb-1", "doc-a", "a.txt", "正文")
        await engine.stop()
        assert rag.inserted == ["doc-a"]

    asyncio.run(case())


def test_stop_cancels_after_grace():
    """超过宽限期仍在抽取的任务被取消，避免停机无限等待。"""

    async def case() -> None:
        engine = _engine(shutdown_grace_s=0.01)
        rag = FakeRag(block=True)
        engine._rag = rag
        await engine.index_document("kb-1", "doc-a", "a.txt", "正文")
        await asyncio.sleep(0)
        await engine.stop()
        assert rag.cancelled is True

    asyncio.run(case())


def test_processing_without_local_task_is_reported_failed():
    """引擎报 processing 但本进程无任务：判定为上次中断残留，标 failed 让用户重传。"""

    async def case() -> None:
        engine = _engine()
        engine._rag = FakeRag({"doc-a": SimpleNamespace(status="processing", file_path="kb-1__doc-a__a.txt")})
        assert await engine.document_statuses(["doc-a"]) == {"doc-a": "failed"}

    asyncio.run(case())


def test_processing_with_local_task_stays_indexing():
    """同一进程内正在抽取的文档保持 indexing，不误判为失败。"""

    async def case() -> None:
        engine = _engine()
        engine._rag = FakeRag({"doc-a": SimpleNamespace(status="processing", file_path="kb-1__doc-a__a.txt")}, block=True)
        await engine.index_document("kb-1", "doc-a", "a.txt", "正文")
        assert await engine.document_statuses(["doc-a"]) == {"doc-a": "indexing"}
        await engine.stop()

    asyncio.run(case())


def test_concluded_statuses_pass_through():
    """processed / failed 与引擎记录一致，不参与中断判定。"""

    async def case() -> None:
        engine = _engine()
        engine._rag = FakeRag(
            {
                "doc-a": SimpleNamespace(status="processed", file_path="kb-1__doc-a__a.txt"),
                "doc-b": SimpleNamespace(status="failed", file_path="kb-1__doc-b__b.txt"),
            }
        )
        assert await engine.document_statuses(["doc-a", "doc-b"]) == {
            "doc-a": "indexed",
            "doc-b": "failed",
        }

    asyncio.run(case())


def test_delete_rejects_cross_kb_document():
    """来源前缀不匹配时拒绝删除，避免拿到别库 ID 就能清索引。"""

    async def case() -> None:
        engine = _engine()
        rag = FakeRag({"doc-x": SimpleNamespace(status="processed", file_path="kb-2__doc-x__x.txt")})
        engine._rag = rag
        result = await engine.delete_documents("kb-1", ["doc-x"])
        assert result == {"deleted": False, "results": {"doc-x": "forbidden"}}
        assert rag.deleted == []

    asyncio.run(case())


def test_delete_allows_same_kb_and_missing_record():
    """同库文档正常删除；引擎无记录按幂等成功（平台侧记录可清理）。"""

    async def case() -> None:
        engine = _engine()
        rag = FakeRag({"doc-a": SimpleNamespace(status="processed", file_path="kb-1__doc-a__a.txt")})
        engine._rag = rag
        result = await engine.delete_documents("kb-1", ["doc-a", "doc-missing"])
        assert result["deleted"] is True
        assert rag.deleted == ["doc-a", "doc-missing"]

    asyncio.run(case())


def test_graph_reads_wildcard_with_widened_window():
    """图谱按全局最高度数取候选，再按库过滤，因此请求窗口要大于返回上限。"""

    async def case() -> None:
        engine = _engine()
        rag = FakeRag(
            graph_nodes=[
                SimpleNamespace(
                    id="退款",
                    properties={
                        "file_path": "kb-1__doc-a__a.txt",
                        "entity_type": "业务",
                        "description": "退款业务对象",
                    },
                )
            ]
        )
        engine._rag = rag
        result = await engine.graph("kb-1", 10)
        assert result["nodes"] == [
            {"id": "退款", "entity_type": "业务", "description": "退款业务对象", "doc_ids": ["doc-a"], "degree": 0}
        ]
        assert rag.graph_calls[0][0] == "*"
        assert rag.graph_calls[0][2] >= 200

    asyncio.run(case())


def test_graph_requires_ready_engine():
    """引擎未就绪时抛 EngineUnavailable，由接口层转 503，不返回空图冒充无实体。"""

    async def case() -> None:
        engine = _engine()
        with pytest.raises(EngineUnavailable):
            await engine.graph("kb-1", 10)

    asyncio.run(case())


def test_failure_table_is_bounded():
    """失败表超过容量上限时淘汰最旧记录，避免长期运行无界增长。"""

    engine = _engine()
    for index in range(_MAX_FAILED_RECORDS + 5):
        engine._remember_failure(f"doc-{index}", "boom")

    assert len(engine._failed) == _MAX_FAILED_RECORDS
    assert "doc-0" not in engine._failed
    assert f"doc-{_MAX_FAILED_RECORDS + 4}" in engine._failed
