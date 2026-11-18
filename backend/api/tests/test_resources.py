"""能力中心资源路由回归（SQLite 功能验证）。

覆盖：创建/列表可见性、私有资源隔离、写权限、使用计数与事件、克隆血缘、
非法类型与超大内容校验、资源广场三榜口径（无事件时飙升榜为空）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import JSON, BigInteger, ForeignKeyConstraint, Integer, MetaData, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import AuditLog, Resource, ResourceUsageEvent, User

_NEEDED_MODELS = (User, Resource, ResourceUsageEvent, AuditLog)


@pytest.fixture
def center():
    """最小 SQLite 表集合 + 三个账号（成员 / 另一位成员 / 管理员）。"""
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

    with factory.begin() as db:
        db.add_all(
            [
                User(id="u-1", username="alice", display_name="Alice", password_hash="x"),
                User(id="u-2", username="bob", display_name="Bob", password_hash="x"),
                User(id="u-3", username="root", display_name="Root", password_hash="x", role="admin"),
            ]
        )

    state = {"current": "u-1"}

    def current_user():
        with factory() as db:
            return db.get(User, state["current"])

    def database():
        with factory() as db:
            yield db

    old = dict(app.dependency_overrides)
    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_db] = database
    client = TestClient(app)
    case = SimpleNamespace(factory=factory, client=client, as_user=lambda uid: state.update(current=uid))
    try:
        yield case
    finally:
        app.dependency_overrides = old


def _create(client: TestClient, **over):
    """创建资源的最小请求体。"""
    payload = {
        "kind": "agent",
        "name": "日志分析助手",
        "summary": "按错误聚合分析日志",
        "content": {"system_prompt": "你是日志分析助手", "tools": ["read"]},
        "visibility": "team",
    }
    payload.update(over)
    return client.post("/api/resources", json=payload)


def test_create_and_list_team_resource(center):
    """团队资源对全员可见，属主可编辑，初始计数为 0。"""
    client = center.client
    created = _create(client)
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["kind"] == "agent" and body["usage_count"] == 0
    assert body["editable"] is True and body["owner_name"] == "Alice"

    center.as_user("u-2")
    listed = client.get("/api/resources", params={"kind": "agent"})
    assert listed.status_code == 200
    data = listed.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == body["id"]
    assert data["items"][0]["editable"] is False  # 他人只读


def test_private_resource_hidden_from_others(center):
    """私有资源只对属主与管理员可见，其他成员拿到 DENIED。"""
    client = center.client
    created = _create(client, visibility="private").json()

    center.as_user("u-2")
    assert client.get("/api/resources").json()["total"] == 0
    denied = client.get(f"/api/resources/{created['id']}")
    assert denied.status_code == 403 and denied.json()["code"] == "DENIED"

    center.as_user("u-3")
    assert client.get("/api/resources").json()["total"] == 1
    assert client.get(f"/api/resources/{created['id']}").status_code == 200


def test_update_and_delete_require_owner(center):
    """非属主不能改删；属主可以改，删除后不可再读。"""
    client = center.client
    created = _create(client).json()

    center.as_user("u-2")
    assert client.patch(f"/api/resources/{created['id']}", json={"name": "改个名"}).status_code == 403
    assert client.delete(f"/api/resources/{created['id']}").status_code == 403

    center.as_user("u-1")
    patched = client.patch(f"/api/resources/{created['id']}", json={"name": "日志分析助手 v2"})
    assert patched.status_code == 200 and patched.json()["name"] == "日志分析助手 v2"
    assert client.delete(f"/api/resources/{created['id']}").json() == {"deleted": True}
    assert client.get(f"/api/resources/{created['id']}").status_code == 404


def test_use_increments_counter_and_writes_event(center):
    """使用一次计数 +1 并落事件；事件用于广场飙升榜。"""
    client = center.client
    created = _create(client).json()
    assert client.post(f"/api/resources/{created['id']}/use").json()["usage_count"] == 1
    assert client.post(f"/api/resources/{created['id']}/use").json()["usage_count"] == 2
    with center.factory() as db:
        assert db.query(ResourceUsageEvent).filter_by(resource_id=created["id"]).count() == 2


def test_clone_keeps_lineage_and_is_private(center):
    """「基于此创建」生成私有副本并记录来源。"""
    client = center.client
    source = _create(client).json()
    center.as_user("u-2")
    cloned = client.post(f"/api/resources/{source['id']}/clone", json={})
    assert cloned.status_code == 200, cloned.text
    body = cloned.json()
    assert body["source_id"] == source["id"]
    assert body["visibility"] == "private"
    assert body["owner_name"] == "Bob"
    assert body["name"].endswith("副本")


def test_invalid_kind_and_oversize_content_rejected(center):
    """未知类型 400；内容超过 100KB 也 400。"""
    client = center.client
    assert _create(client, kind="workflow").status_code == 400
    big = {"system_prompt": "x" * 120_000}
    assert _create(client, content=big).status_code == 400


def test_plaza_boards(center):
    """广场：热门按累计、新品按创建时间、飙升只统计近 7 日事件。"""
    client = center.client
    first = _create(client, name="热门资源").json()
    second = _create(client, name="冷门资源", kind="skill", content={"markdown": "# 技能"}).json()
    client.post(f"/api/resources/{first['id']}/use")
    client.post(f"/api/resources/{first['id']}/use")

    # 构造一条 30 天前的历史事件：只应计入累计榜单，不进飙升榜。
    old_time = datetime.now(UTC) - timedelta(days=30)
    with center.factory.begin() as db:
        db.add(ResourceUsageEvent(resource_id=second["id"], user_id="u-2", created_at=old_time))

    plaza = client.get("/api/resources/plaza").json()
    assert plaza["total"] == 2
    assert plaza["popular"][0]["name"] == "热门资源"
    assert plaza["popular"][0]["usage_count"] == 2
    assert plaza["newest"][0]["name"] == "冷门资源"  # 后建的在最前
    assert [row["name"] for row in plaza["rising"]] == ["热门资源"]  # 30 天前的事件不算
    assert plaza["rising"][0]["weekly_uses"] == 2
