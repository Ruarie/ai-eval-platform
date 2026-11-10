"""知识库文档列表投影回归（SQLite 功能验证）。

文档正文单篇上限 20MB，列表接口只应读取元信息列；本测试通过捕获实际 SQL
确认 `kb_documents.text` 不进入 SELECT，防止后续改动重新把正文读进内存。
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import JSON, BigInteger, Integer, MetaData, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import AuditLog, KbDocument, KnowledgeBase

_NEEDED_MODELS = (KnowledgeBase, KbDocument, AuditLog)


@pytest.fixture
def kb_docs_case():
    """建立最小 SQLite 表集合并插入两篇含正文的文档。"""
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
            constraint for constraint in table.constraints if constraint.__class__.__name__ != "ForeignKeyConstraint"
        }
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    for table in metadata.tables.values():
        table.create(engine, checkfirst=True)
    factory = sessionmaker(engine, expire_on_commit=False)

    with factory.begin() as db:
        db.add(KnowledgeBase(id="kb-1", name="支付知识库", kind="lightrag", is_core=False))
        db.add_all(
            [
                KbDocument(
                    id="doc-1",
                    kb_id="kb-1",
                    filename="退款说明.md",
                    size=2048,
                    text="很长的正文" * 1000,
                    status="indexed",
                ),
                KbDocument(
                    id="doc-2",
                    kb_id="kb-1",
                    filename="支付规则.md",
                    size=1024,
                    text="另一段正文" * 1000,
                    status="indexed",
                ),
            ]
        )

    def database():
        with factory() as db:
            yield db

    old_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="member", username="member")
    client = TestClient(app)
    case = SimpleNamespace(client=client, engine=engine)
    try:
        yield case
    finally:
        app.dependency_overrides = old_overrides


def test_kb_doc_list_projects_metadata_only(kb_docs_case):
    """返回元信息且不查询正文列。"""
    statements: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(kb_docs_case.engine, "before_cursor_execute", capture)
    try:
        response = kb_docs_case.client.get("/api/kb/kb-1/documents")
    finally:
        event.remove(kb_docs_case.engine, "before_cursor_execute", capture)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 2
    assert [item["filename"] for item in data["items"]] == ["退款说明.md", "支付规则.md"]
    assert all("text" not in item for item in data["items"])
    assert data["items"][0]["size"] == "2.0 KB"

    doc_selects = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("SELECT") and "kb_documents" in statement
    ]
    assert doc_selects, "未捕获到文档列表查询"
    assert all("kb_documents.text" not in statement for statement in doc_selects), doc_selects


def test_kb_list_counts_documents_without_loading_text(kb_docs_case):
    """知识库列表用聚合计数，不把文档正文带出来。"""
    statements: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(kb_docs_case.engine, "before_cursor_execute", capture)
    try:
        response = kb_docs_case.client.get("/api/kb")
    finally:
        event.remove(kb_docs_case.engine, "before_cursor_execute", capture)

    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["id"] == "kb-1"
    assert item["doc_count"] == 2
    assert all("kb_documents.text" not in statement for statement in statements)


def test_kb_delete_document_skips_text(kb_docs_case, monkeypatch):
    """删除文档只读元信息。"""
    monkeypatch.setattr("app.routers.kb.delete_documents", lambda kb_id, doc_ids: True)
    statements: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(kb_docs_case.engine, "before_cursor_execute", capture)
    try:
        response = kb_docs_case.client.delete("/api/kb/kb-1/documents/doc-1")
    finally:
        event.remove(kb_docs_case.engine, "before_cursor_execute", capture)

    assert response.status_code == 200, response.text
    selects = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("SELECT") and "kb_documents" in statement
    ]
    assert selects, "未捕获到删除前的文档查询"
    assert all("kb_documents.text" not in statement for statement in selects), selects
