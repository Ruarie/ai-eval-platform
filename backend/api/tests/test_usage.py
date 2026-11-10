"""Token 用量中心聚合回归（SQLite 功能验证）。"""

from datetime import UTC, datetime
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
from app.models import Message, User
from app.models import Session as AgentSession

_NEEDED_MODELS = (User, AgentSession, Message)


@pytest.fixture
def usage_case():
    """建立最小 SQLite 表集合与两条会话的用量消息。"""
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
    with factory.begin() as db:
        db.add_all(
            [
                User(id="member", username="member", password_hash="test"),
                User(id="other", username="other", password_hash="test"),
            ]
        )
        db.add_all(
            [
                AgentSession(
                    id="session-1",
                    user_id="member",
                    title="登录会话",
                    visibility="private",
                    engine_version="agent_loop_v2",
                ),
                AgentSession(
                    id="session-2",
                    user_id="other",
                    title="支付会话",
                    visibility="private",
                    engine_version="agent_loop_v2",
                ),
            ]
        )
        db.add_all(
            [
                Message(
                    id="msg-1",
                    session_id="session-1",
                    role="assistant",
                    content="好的",
                    source_id="source-1",
                    profile_id="profile-a",
                    model_name="model-a",
                    turn_stats={"usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}},
                    created_at=now,
                ),
                Message(
                    id="msg-2",
                    session_id="session-1",
                    role="assistant",
                    content="继续",
                    source_id="source-2",
                    profile_id="profile-a",
                    model_name="model-a",
                    turn_stats={"usage": {"prompt_tokens": 50, "completion_tokens": 10}},
                    created_at=now,
                ),
                Message(
                    id="msg-3",
                    session_id="session-2",
                    role="assistant",
                    content="支付完成",
                    source_id="source-3",
                    profile_id="profile-b",
                    model_name="model-b",
                    turn_stats={"usage": {"input_tokens": 80, "output_tokens": 20}},
                    created_at=now,
                ),
                Message(
                    id="msg-user",
                    session_id="session-1",
                    role="user",
                    content="问题",
                    source_id="source-u",
                    created_at=now,
                ),
            ]
        )

    def current_user():
        with factory() as db:
            return db.get(User, "member")

    def database():
        with factory() as db:
            yield db

    old_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_db] = database
    client = TestClient(app)
    case = SimpleNamespace(factory=factory, client=client)
    try:
        yield case
    finally:
        app.dependency_overrides = old_overrides


def test_usage_summary_aggregates(usage_case):
    """总用量、按模型/用户与趋势对账。"""
    response = usage_case.client.get("/api/usage/summary", params={"days": 30})
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["calls"] == 3
    assert data["sessions"] == 2
    assert data["users"] == 2
    assert data["prompt_tokens"] == 230
    assert data["completion_tokens"] == 50
    assert data["total_tokens"] == 280
    assert len(data["series"]) == 30
    assert data["series"][-1]["total_tokens"] == 280

    models = {item["model_name"]: item for item in data["by_model"]}
    assert models["model-a"]["calls"] == 2
    assert models["model-a"]["sessions"] == 1
    assert models["model-a"]["total_tokens"] == 180
    assert models["model-b"]["total_tokens"] == 100

    users = {item["username"]: item for item in data["by_user"]}
    assert users["member"]["total_tokens"] == 180
    assert users["other"]["total_tokens"] == 100

    assert len(data["recent"]) == 3
    assert all("content" not in item for item in data["recent"])
    # 未超过扫描上限：必须明确告知前端这是全量样本
    assert data["truncated"] is False
    assert data["scanned_messages"] == 3
    assert data["sample_limit"] == 5000


def test_usage_summary_marks_truncated_sample(usage_case, monkeypatch):
    """超过扫描上限时必须回传 truncated/scanned_messages，页面据此提示非全量。"""
    from app.routers import usage as usage_router

    monkeypatch.setattr(usage_router, "MAX_MESSAGES", 1)
    response = usage_case.client.get("/api/usage/summary", params={"days": 30})
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["truncated"] is True
    assert data["scanned_messages"] == 1
    assert data["sample_limit"] == 1
    # 只统计最近一条（created_at 相同，按 SQLite 返回顺序取一条），总量应小于全量 280
    assert data["total_tokens"] < 280


def test_usage_summary_days_validation(usage_case):
    """days 越界按统一 VALIDATION 返回 400。"""
    assert usage_case.client.get("/api/usage/summary", params={"days": 0}).status_code == 400
    assert usage_case.client.get("/api/usage/summary", params={"days": 366}).status_code == 400
