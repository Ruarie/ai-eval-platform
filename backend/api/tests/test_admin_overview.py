"""后台总览聚合接口回归（SQLite 功能验证）。

覆盖：成员/会话/任务/资源/存储/审计六组口径，以及软删除会话不计入、
任务只统计近 7 天、审计 Top 动作按次数排序。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import (
    JSON,
    BigInteger,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import (
    AuditLog,
    KbDocument,
    KnowledgeBase,
    Resource,
    StoredFile,
    Task,
    User,
)
from app.models import (
    Session as ChatSession,
)

_NEEDED_MODELS = (
    User,
    ChatSession,
    Task,
    Resource,
    StoredFile,
    KnowledgeBase,
    KbDocument,
    AuditLog,
)


@pytest.fixture
def overview_case():
    """最小表集合 + 一批可预期的样本数据。"""
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
            constraint
            for constraint in table.constraints
            if not isinstance(constraint, ForeignKeyConstraint)
        }
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    for table in metadata.tables.values():
        table.create(engine, checkfirst=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    old = now - timedelta(days=30)

    with factory.begin() as db:
        db.add_all(
            [
                User(
                    id="u-1", username="alice", display_name="Alice", password_hash="x",
                    role="admin", disabled=False, last_login_at=now, created_at=now,
                ),
                User(
                    id="u-2", username="bob", display_name="Bob", password_hash="x",
                    role="member", disabled=True, last_login_at=old, created_at=old,
                ),
            ]
        )
        db.add_all(
            [
                ChatSession(
                    id="s-1", user_id="u-1", title="在用会话", visibility="team",
                    created_at=now, deleted_at=None,
                ),
                ChatSession(
                    id="s-2", user_id="u-1", title="私有会话", visibility="private",
                    created_at=old, deleted_at=None,
                ),
                ChatSession(
                    id="s-3", user_id="u-2", title="已删会话", visibility="private",
                    created_at=now, deleted_at=now,
                ),
            ]
        )
        db.add_all(
            [
                Task(id="t-1", kind="testcase", status="succeeded", created_by="u-1", created_at=now),
                Task(id="t-2", kind="testcase", status="running", created_by="u-1", created_at=now),
                Task(id="t-3", kind="testcase", status="succeeded", created_by="u-1", created_at=old),
            ]
        )
        db.add_all(
            [
                Resource(
                    id="r-1", kind="agent", name="A", visibility="team",
                    usage_count=5, created_at=now, content={},
                ),
                Resource(
                    id="r-2", kind="rag", name="R", visibility="private",
                    usage_count=2, created_at=old, content={},
                ),
            ]
        )
        db.add(StoredFile(
            id="f-1", filename="a.log", size_bytes=1024, sha256="a" * 64,
            storage_path="/tmp/a.log", uploaded_by="u-1", created_at=now,
        ))
        db.add(KnowledgeBase(id="kb-1", name="退款库", kind="lightrag", created_by="u-1"))
        db.add_all([
            KbDocument(id="d-1", kb_id="kb-1", filename="a.md"),
            KbDocument(id="d-2", kb_id="kb-1", filename="b.md"),
        ])
        db.add_all(
            [
                AuditLog(user_id="u-1", action="resource_create", target_type="resource",
                         target_id="r-1", detail={}, ip="10.0.0.1", ts=now),
                AuditLog(user_id="u-1", action="resource_create", target_type="resource",
                         target_id="r-2", detail={}, ip="10.0.0.1", ts=now),
                AuditLog(user_id="u-2", action="resource_delete", target_type="resource",
                         target_id="r-9", detail={}, ip="10.0.0.2", ts=now),
                AuditLog(user_id="u-1", action="workspace_remote_exec", target_type="workspace",
                         target_id="w-1", detail={}, ip="10.0.0.1", ts=old),
            ]
        )

    def current_user():
        with factory() as db:
            return db.get(User, "u-1")

    def database():
        with factory() as db:
            yield db

    old_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_db] = database
    client = TestClient(app)
    try:
        yield SimpleNamespace(client=client, factory=factory)
    finally:
        app.dependency_overrides = old_overrides


def test_overview_counts(overview_case):
    """六组数字与样本一致，且软删除会话、30 天前任务被排除。"""
    resp = overview_case.client.get("/api/admin/overview")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["users"] == {"total": 2, "new_7d": 1, "active_7d": 1, "disabled": 1}
    # 3 条会话里 s-3 已软删除 → total=2；近 7 天新建且未删的只有 s-1
    assert data["sessions"] == {"total": 2, "new_7d": 1, "shared": 1}
    # 近 7 天只有 t-1/t-2；t-3 是 30 天前
    assert data["tasks"] == {"total_7d": 2, "by_status": {"succeeded": 1, "running": 1}}
    assert data["resources"] == {
        "total": 2, "new_7d": 1, "team": 1, "private": 1,
        "usage_total": 7, "by_kind": {"agent": 1, "rag": 1},
    }
    assert data["storage"] == {"files": 1, "bytes": 1024, "kb_count": 1, "kb_docs": 2}


def test_overview_audit_section(overview_case):
    """审计只算近 24h，Top 动作按次数降序，最近条目带操作人。"""
    data = overview_case.client.get("/api/admin/overview").json()
    assert data["audit_24h"] == 3  # 30 天前那条不计
    assert data["top_actions"]["resource_create"] == 2
    assert data["top_actions"]["resource_delete"] == 1
    assert len(data["recent_audit"]) == 4
    first = data["recent_audit"][0]
    assert set(first) == {"id", "action", "target_type", "target_id", "user_name", "ip", "ts"}
    assert first["ts"]
    assert data["generated_at"]


def test_audit_logs_filter_by_action_and_target(overview_case):
    """动作与对象 ID 在服务端过滤，且分页总数随筛选变化、条目带 IP。"""
    client = overview_case.client
    resp = client.get("/api/admin/audit-logs", params={"action": "resource_create"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 2
    assert {item["action"] for item in data["items"]} == {"resource_create"}
    assert data["items"][0]["ip"] == "10.0.0.1"

    resp = client.get("/api/admin/audit-logs", params={"target_id": "r-9"})
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["action"] == "resource_delete"


def test_audit_action_options_come_from_real_rows(overview_case):
    """动作下拉取自真实审计行，次数按动作聚合。"""
    resp = overview_case.client.get("/api/admin/audit-actions")
    assert resp.status_code == 200, resp.text
    counts = {item["action"]: item["count"] for item in resp.json()["items"]}
    assert counts["resource_create"] == 2
    assert counts["resource_delete"] == 1
    assert counts["workspace_remote_exec"] == 1


def test_resource_list_supports_visibility_filter(overview_case):
    """资源治理可按可见性在服务端筛选，并返回筛选后的 total。"""
    resp = overview_case.client.get("/api/resources", params={"visibility": "private"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 1
    assert [item["id"] for item in data["items"]] == ["r-2"]
