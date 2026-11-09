"""历史轨迹查询回归（SQLite 功能验证）。"""

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
from app.models import AgentEvent, Session, User

_NEEDED_MODELS = (User, Session, AgentEvent)


@pytest.fixture
def trace_case():
    """建立最小 SQLite 表集合并写入两个回合的事件。"""
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
        db.add(User(id="member", username="member", password_hash="test"))
        db.add(User(id="other", username="other", password_hash="test"))
        db.add(
            Session(
                id="session-1",
                user_id="member",
                title="轨迹会话",
                visibility="private",
                engine_version="agent_loop_v2",
            )
        )
        envelopes = [
            {
                "seq": 1,
                "ts": 100.0,
                "type": "turn/start",
                "data": {"turn": 1},
                "correlation": {"turn": 1},
            },
            {
                "seq": 2,
                "ts": 101.0,
                "type": "tool/call",
                "data": {"turn": 1, "name": "read", "call_id": "c1"},
                "correlation": {"turn": 1},
            },
            {
                "seq": 3,
                "ts": 102.0,
                "type": "tool/result",
                "data": {"turn": 1, "name": "read", "status": "succeeded", "duration_ms": 120},
                "correlation": {"turn": 1},
            },
            {
                "seq": 4,
                "ts": 103.0,
                "type": "assistant/message",
                "data": {
                    "turn": 1,
                    "turn_stats": {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}},
                },
                "correlation": {"turn": 1},
            },
            {
                "seq": 5,
                "ts": 104.0,
                "type": "turn/end",
                "data": {"turn": 1, "reason": "completed"},
                "correlation": {"turn": 1},
            },
            {
                "seq": 6,
                "ts": 200.0,
                "type": "turn/start",
                "data": {"turn": 2},
                "correlation": {"turn": 2},
            },
            {
                "seq": 7,
                "ts": 201.0,
                "type": "runtime/error",
                "data": {"turn": 2, "code": "UPSTREAM"},
                "correlation": {"turn": 2},
            },
        ]
        for envelope in envelopes:
            db.add(
                AgentEvent(
                    session_id="session-1",
                    seq=envelope["seq"],
                    type=envelope["type"],
                    envelope=envelope,
                )
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


def test_trace_turns_summary_and_detail(trace_case):
    """摘要按回合倒序；详情只包含脱敏元数据。"""
    client = trace_case.client
    turns = client.get("/api/sessions/session-1/trace/turns")
    assert turns.status_code == 200, turns.text
    body = turns.json()
    assert [item["turn"] for item in body] == [2, 1]
    first = body[1]
    assert first["status"] == "completed"
    assert first["tool_calls"] == 1
    assert first["event_count"] == 5
    assert first["prompt_tokens"] == 10
    assert first["completion_tokens"] == 5
    assert first["total_tokens"] == 15
    assert body[0]["status"] == "failed"

    detail = client.get("/api/sessions/session-1/trace/turns/1")
    assert detail.status_code == 200, detail.text
    data = detail.json()
    assert data["summary"]["turn"] == 1
    assert [event["type"] for event in data["events"]] == [
        "turn/start",
        "tool/call",
        "tool/result",
        "assistant/message",
        "turn/end",
    ]
    tool = next(event for event in data["events"] if event["type"] == "tool/result")
    assert tool["name"] == "read"
    assert tool["status"] == "succeeded"
    assert tool["duration_ms"] == 120
    # 脱敏：不返回消息正文、工具参数或结果字段；token 统计允许出现。
    serialized = str(data)
    assert "content" not in serialized
    assert "arguments" not in serialized


def test_trace_private_session_not_visible(trace_case):
    """他人私有会话统一返回 404。"""
    def other_user():
        with trace_case.factory() as db:
            return db.get(User, "other")

    app.dependency_overrides[get_current_user] = other_user
    try:
        response = trace_case.client.get("/api/sessions/session-1/trace/turns")
        assert response.status_code == 404
    finally:
        def current_user():
            with trace_case.factory() as db:
                return db.get(User, "member")
        app.dependency_overrides[get_current_user] = current_user


def test_trace_turn_validation(trace_case):
    """limit 越界按统一 VALIDATION 返回 400。"""
    response = trace_case.client.get(
        "/api/sessions/session-1/trace/turns", params={"limit": 0}
    )
    assert response.status_code == 400
