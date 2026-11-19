"""成员开通接口回归：契约外字段必须被拒，且错误要能定位到具体字段。

背景：前端曾提交 ``role``，后端 ``extra="forbid"`` 直接 422 → 归一为 400 后只剩
一句「请检查标红字段」，表单无法标红，表现为「开通新成员总是失败且没有原因」。
本文件同时锁定两件事：① 错误体带 ``fields``；② 不带 role 时能正常创建。
"""

from __future__ import annotations

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
from app.models import AuditLog, User

_NEEDED_MODELS = (User, AuditLog)


@pytest.fixture
def users_case():
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
        db.add(
            User(
                id="u-admin",
                username="admin",
                display_name="管理员",
                password_hash="x",
                role="admin",
                disabled=False,
            )
        )

    def current_user():
        with factory() as db:
            return db.get(User, "u-admin")

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


def test_extra_field_is_rejected_with_field_detail(users_case):
    """多带 role 必须失败，但错误体要告诉前端是哪个字段出的问题。"""
    resp = users_case.client.post(
        "/api/users",
        json={"username": "uitest01", "password": "UiTest2026x", "role": "member"},
    )
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body["code"] == "VALIDATION"
    assert body["message"] == "请检查标红字段"
    assert "role" in body["fields"], body
    assert body["fields"]["role"]


def test_create_member_without_role_succeeds(users_case):
    """正常契约：只传用户名/密码/显示名，角色由服务端恒写 member。"""
    resp = users_case.client.post(
        "/api/users",
        json={
            "username": "uitest02",
            "password": "UiTest2026x",
            "display_name": "测试成员",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["username"] == "uitest02"
    assert body["display_name"] == "测试成员"
    assert body["role"] == "member"

    with users_case.factory() as db:
        saved = db.query(User).filter(User.username == "uitest02").one()
        assert saved.role == "member"
        actions = [row.action for row in db.query(AuditLog).all()]
        assert "user_create" in actions
