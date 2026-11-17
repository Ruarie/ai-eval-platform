"""知识图谱端点空库短路回归（SQLite 功能验证）。

背景：新建的空知识库在引擎侧还没有命名空间，`/graph` 会失败并返回 UPSTREAM，
前端把「还没上传文档」显示成「图谱读取失败」。平台侧已经知道这个库一条文档
都没有时，空图就是事实，应当直接返回空图，不触达引擎。
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import JSON, BigInteger, Integer, MetaData, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import AuditLog, KbDocument, KnowledgeBase
from app.routers import kb as kb_router

_NEEDED_MODELS = (KnowledgeBase, KbDocument, AuditLog)


@pytest.fixture
def kb_graph_case(monkeypatch: pytest.MonkeyPatch):
    """最小表集合：空库 kb-empty 与有文档库 kb-doc。"""
    metadata = MetaData()
    for model in _NEEDED_MODELS:
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            elif isinstance(column.type, BigInteger) and column.primary_key:
                column.type = Integer()
            column.foreign_keys.clear()
        table.constraints = {
            c for c in table.constraints if c.__class__.__name__ != "ForeignKeyConstraint"
        }
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for table in metadata.tables.values():
        table.create(engine, checkfirst=True)
    factory = sessionmaker(engine, expire_on_commit=False)

    with factory.begin() as db:
        db.add(KnowledgeBase(id="kb-empty", name="空知识库", kind="lightrag", is_core=False))
        db.add(KnowledgeBase(id="kb-doc", name="有文档库", kind="lightrag", is_core=False))
        db.add(
            KbDocument(
                id="doc-1", kb_id="kb-doc", filename="退款说明.md", size=64, text="退款 3 天到账", status="indexed"
            )
        )

    def database():
        with factory() as db:
            yield db

    calls: list[tuple] = []

    def fake_fetch_graph(kb_id: str, limit: int = 200):
        calls.append((kb_id, limit))
        return None

    monkeypatch.setattr(kb_router, "fetch_graph", fake_fetch_graph)

    old_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="member", username="member")
    try:
        yield SimpleNamespace(client=TestClient(app), calls=calls)
    finally:
        app.dependency_overrides = old_overrides


def test_empty_library_returns_empty_graph_without_engine_call(kb_graph_case):
    """空库直接返回空图，不调用 LightRAG，也不报 502。"""
    response = kb_graph_case.client.get("/api/kb/kb-empty/graph")

    assert response.status_code == 200
    body = response.json()
    assert body["kb_id"] == "kb-empty"
    assert body["nodes"] == [] and body["edges"] == []
    assert body["truncated"] is False
    assert kb_graph_case.calls == []


def test_library_with_documents_still_reports_upstream(kb_graph_case):
    """有文档的库仍按原契约上报 UPSTREAM，不用空图掩盖引擎故障。"""
    response = kb_graph_case.client.get("/api/kb/kb-doc/graph")

    assert response.status_code == 502
    assert response.json()["code"] == "UPSTREAM"
    assert kb_graph_case.calls == [("kb-doc", 200)]
