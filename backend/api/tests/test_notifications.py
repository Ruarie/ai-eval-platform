"""通知中心服务与路由回归（SQLite 功能验证）。"""

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
from app.models import Notification, User
from app.notification_service import add_notification, unread_count

_NEEDED_MODELS = (User, Notification)


@pytest.fixture
def notification_case():
    """建立最小 SQLite 表集合并注入当前成员。"""
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
                User(id="member", username="member", password_hash="test"),
                User(id="other", username="other", password_hash="test"),
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


def _seed(case, user_id="member"):
    """写入三条通知，其中一条已读；重复去重键只保留一条。"""
    with case.factory.begin() as db:
        add_notification(
            db,
            user_id=user_id,
            type="task_ready",
            title="用例已生成",
            body="请确认",
            link="/cases?set_id=s1",
            dedupe_key="task:1:ready",
        )
        add_notification(
            db,
            user_id=user_id,
            type="task_ready",
            title="重复通知",
            dedupe_key="task:1:ready",
        )
        add_notification(
            db,
            user_id=user_id,
            type="task_failed",
            title="任务失败",
            body="UPSTREAM",
            link="/tasks?task_id=t2",
            dedupe_key="task:2:failed",
        )
        add_notification(
            db,
            user_id=user_id,
            type="review_requested",
            title="待评审",
            dedupe_key="review:1:requested",
        )
        # 不在此处 commit：factory.begin() 负责提交，提前关闭事务会导致后续 count 失败。
        assert unread_count(db, user_id) == 3


def test_notification_list_and_read(notification_case):
    """列表、未读数、单条已读与全部已读。"""
    _seed(notification_case)
    client = notification_case.client

    listed = client.get("/api/notifications")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] == 3
    assert body["unread"] == 3
    assert len(body["items"]) == 3

    unread = client.get("/api/notifications/unread-count")
    assert unread.json()["unread"] == 3

    first = body["items"][0]["id"]
    read = client.post(f"/api/notifications/{first}/read")
    assert read.status_code == 200
    assert read.json()["unread"] == 2

    unread_only = client.get("/api/notifications", params={"unread": True})
    assert unread_only.json()["total"] == 2

    all_read = client.post("/api/notifications/read-all")
    assert all_read.status_code == 200
    assert all_read.json()["unread"] == 0


def test_notification_isolation_and_missing(notification_case):
    """不能读取或标记其他人的通知。"""
    _seed(notification_case, user_id="other")
    client = notification_case.client

    listed = client.get("/api/notifications")
    assert listed.json()["total"] == 0

    with notification_case.factory() as db:
        other_id = db.query(Notification.id).filter(Notification.user_id == "other").first()[0]
    missing = client.post(f"/api/notifications/{other_id}/read")
    assert missing.status_code == 404
