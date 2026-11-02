"""LightRAG 适配服务客户端（``shared.kb``）契约单测。

覆盖四类行为：
1. 检索响应映射：切块 ID、doc_id、doc_name 忠实还原，相似度缺省为 None；
2. 降级口径：引擎可用但召回为空不算降级，只有不可用才回退本地关键词；
3. 索引受理：受理成功记 indexing，未配置/被拒记 failed（不乐观标记）；
4. 删除与状态回读：未配置引擎视为无残留，配置后失败必须如实返回 False。
"""

import shared.kb as kb_module


def _payload_with_contexts():
    """构造适配服务 ``/query`` 的典型响应。"""
    return {
        "text": "",
        "contexts": [
            {
                "id": "chunk-001",
                "doc_id": "doc-a",
                "doc_name": "a.txt",
                "text": "退款 1-3 个工作日到账",
                "reference_id": "1",
            },
            {
                "id": "chunk-002",
                "doc_id": "doc-b",
                "doc_name": "b.txt",
                "text": "改绑手机号",
                "reference_id": "2",
            },
        ],
        "mode": "hybrid",
    }


def test_try_lightrag_maps_contexts(monkeypatch):
    """适配服务返回的上下文映射为平台结构，保留排序且不臆造相似度。"""
    monkeypatch.setattr(
        kb_module, "_lightrag_post", lambda *a, **k: _payload_with_contexts()
    )

    items = kb_module._try_lightrag("kb-1", "退款多久到账", "hybrid", 5)

    assert [item["chunk_id"] for item in items] == ["chunk-001", "chunk-002"]
    assert [item["doc_id"] for item in items] == ["doc-a", "doc-b"]
    assert [item["doc_name"] for item in items] == ["a.txt", "b.txt"]
    assert items[0]["similarity"] is None


def test_try_lightrag_falls_back_to_chunk_prefix(monkeypatch):
    """适配层未给出 doc_id 时按切块 ID 前缀解析，兼容旧数据。"""
    monkeypatch.setattr(
        kb_module,
        "_lightrag_post",
        lambda *a, **k: {"contexts": [{"id": "doc-x#c01", "text": "正文"}]},
    )

    items = kb_module._try_lightrag("kb-1", "q", "naive", 5)

    assert items[0]["doc_id"] == "doc-x"
    assert items[0]["doc_name"] == "doc-x"


def test_empty_contexts_stay_lightrag(monkeypatch):
    """引擎可用但召回为空是真实未命中，不得回退本地并标注为降级。"""
    monkeypatch.setattr(kb_module, "_lightrag_post", lambda *a, **k: {"contexts": []})
    monkeypatch.setattr(
        kb_module, "_local_retrieve", lambda *a, **k: (_ for _ in ()).throw(AssertionError("不应回退"))
    )

    items, source = kb_module.retrieve_with_source(None, "kb-1", "退款多久到账")

    assert items == []
    assert source == kb_module.RETRIEVE_SOURCE_LIGHTRAG


def test_unavailable_engine_falls_back_to_local(monkeypatch):
    """引擎不可用时回退本地关键词检索，并如实标注来源为 local。"""
    monkeypatch.setattr(kb_module, "_lightrag_post", lambda *a, **k: None)
    monkeypatch.setattr(
        kb_module,
        "_local_retrieve",
        lambda db, kb_id, query, k: [
            {"chunk_id": "d#c01", "doc_id": "d", "doc_name": "f.txt", "text": "t", "similarity": 0.5}
        ],
    )

    items, source = kb_module.retrieve_with_source(None, "kb-1", "退款多久到账")

    assert len(items) == 1
    assert source == kb_module.RETRIEVE_SOURCE_LOCAL


def test_index_document_reports_failed_when_engine_missing(monkeypatch):
    """适配服务不可用时不得把文档标记成已建索引。"""
    monkeypatch.setattr(kb_module, "_lightrag_post", lambda *a, **k: None)

    result = kb_module.index_document("kb-1", "doc-a", "a.txt", "正文")

    assert result == {"accepted": False, "status": "failed"}


def test_index_document_accepts_async_indexing(monkeypatch):
    """受理成功返回 indexing，平台据此落库并等待状态回读。"""
    monkeypatch.setattr(
        kb_module, "_lightrag_post", lambda *a, **k: {"doc_id": "doc-a", "status": "indexing"}
    )

    result = kb_module.index_document("kb-1", "doc-a", "a.txt", "正文")

    assert result == {"accepted": True, "status": "indexing"}


def test_index_document_rejects_empty_text(monkeypatch):
    """空正文不发起建索引请求。"""
    calls: list[tuple] = []
    monkeypatch.setattr(kb_module, "_lightrag_post", lambda *a, **k: calls.append(a) or {})

    result = kb_module.index_document("kb-1", "doc-a", "a.txt", "   ")

    assert result == {"accepted": False, "status": "failed"}
    assert calls == []


def test_delete_documents_without_engine_is_noop(monkeypatch):
    """未配置引擎时没有索引可删，按成功处理以免阻塞知识库维护。"""
    monkeypatch.delenv("LIGHTRAG_BASE_URL", raising=False)

    assert kb_module.delete_documents("kb-1", ["doc-a"]) is True


def test_delete_documents_failure_is_reported(monkeypatch):
    """配置了引擎但删除失败必须返回 False，由调用方中止。"""
    monkeypatch.setenv("LIGHTRAG_BASE_URL", "http://lightrag:9621")
    monkeypatch.setattr(kb_module, "_lightrag_post", lambda *a, **k: None)

    assert kb_module.delete_documents("kb-1", ["doc-a"]) is False


def test_legacy_timeout_only_affects_query(monkeypatch):
    """旧版单一超时变量只作检索回退，不得缩短删除窗口。"""
    captured: dict[str, float] = {}

    def fake_post(path: str, payload: dict, timeout: float):
        captured.setdefault(path, timeout)
        return {"contexts": []} if path == "/query" else {"deleted": True}

    monkeypatch.setattr(kb_module, "_lightrag_post", fake_post)
    monkeypatch.setenv("LIGHTRAG_BASE_URL", "http://lightrag:9621")
    monkeypatch.setenv("LIGHTRAG_TIMEOUT_SECONDS", "5")

    kb_module._try_lightrag("kb-1", "q", "naive", 5)
    kb_module.delete_documents("kb-1", ["doc-a"])

    assert captured["/query"] == 5
    assert captured["/documents/delete"] == kb_module.LIGHTRAG_DELETE_TIMEOUT_S


def test_delete_documents_is_batched(monkeypatch):
    """整库删除按批提交，避免单请求过大或撞上代理超时。"""
    batches: list[list[str]] = []

    def fake_post(path: str, payload: dict, timeout: float):
        batches.append(list(payload["doc_ids"]))
        return {"deleted": True}

    monkeypatch.setattr(kb_module, "_lightrag_post", fake_post)
    monkeypatch.setenv("LIGHTRAG_BASE_URL", "http://lightrag:9621")

    assert kb_module.delete_documents("kb-1", [f"doc-{i}" for i in range(120)]) is True
    assert [len(batch) for batch in batches] == [50, 50, 20]


def test_delete_documents_stops_on_failed_batch(monkeypatch):
    """任一批失败即返回 False，由调用方中止（已提交批次在引擎侧已删）。"""
    calls: list[int] = []

    def fake_post(path: str, payload: dict, timeout: float):
        calls.append(len(payload["doc_ids"]))
        return None

    monkeypatch.setattr(kb_module, "_lightrag_post", fake_post)
    monkeypatch.setenv("LIGHTRAG_BASE_URL", "http://lightrag:9621")

    assert kb_module.delete_documents("kb-1", [f"doc-{i}" for i in range(120)]) is False
    assert calls == [50]


def test_document_statuses_is_batched(monkeypatch):
    """状态回读按批进行，避免超过单批上限的文档永远无法收敛。"""
    sizes: list[int] = []

    def fake_fetch(base: str, ids: list[str]):
        sizes.append(len(ids))
        return {doc_id: "indexed" for doc_id in ids}

    monkeypatch.setattr(kb_module, "_fetch_status_batch", fake_fetch)
    monkeypatch.setenv("LIGHTRAG_BASE_URL", "http://lightrag:9621")

    statuses = kb_module.document_statuses([f"doc-{i}" for i in range(450)])

    assert sizes == [200, 200, 50]
    assert len(statuses) == 450


def test_document_statuses_keeps_earlier_batches_on_failure(monkeypatch):
    """某批失败时保留已回读结果并停止，其余由平台保留本地状态。"""
    responses = iter([{"doc-a": "indexed"}, None, {"doc-c": "failed"}])

    monkeypatch.setattr(kb_module, "_fetch_status_batch", lambda base, ids: next(responses))
    monkeypatch.setenv("LIGHTRAG_BASE_URL", "http://lightrag:9621")

    statuses = kb_module.document_statuses([f"doc-{i}" for i in range(300)])

    assert statuses == {"doc-a": "indexed"}


def test_document_statuses_filters_unknown_values(monkeypatch):
    """只接受平台三态，未知取值不覆盖平台本地状态。"""
    monkeypatch.setenv("LIGHTRAG_BASE_URL", "http://lightrag:9621")

    class _Resp:
        def read(self):
            return (
                b'{"items":[{"doc_id":"doc-a","status":"indexed"},'
                b'{"doc_id":"doc-b","status":"weird"}]}'
            )

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(kb_module.urllib.request, "urlopen", lambda *a, **k: _Resp())

    assert kb_module.document_statuses(["doc-a", "doc-b"]) == {"doc-a": "indexed"}
