"""用例集删除回归：软删标记、列表/详情隐藏、审计留痕、行数据保留。

删用例集是这轮 UI 回归里唯一的功能缺口——只能建不能删。实现选择软删除：
即使已入库，版本快照与评审记录也要能追溯，因此不物理删除行。
"""

from __future__ import annotations

from datetime import UTC, datetime
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
from app.models import AuditLog, CaseItem, CaseSet, User

_NEEDED_MODELS = (User, CaseSet, CaseItem, AuditLog)


@pytest.fixture
def case_set_case():
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
                id="u-1",
                username="admin",
                display_name="管理员",
                password_hash="x",
                role="admin",
                disabled=False,
            )
        )
        db.add(
            CaseSet(
                id="set-1",
                name="草稿用例集",
                status="generated",
                generated_count=1,
                created_by="u-1",
                created_at=datetime.now(UTC),
            )
        )
        db.add(
            CaseSet(
                id="set-2",
                name="已入库用例集",
                status="confirmed",
                generated_count=1,
                confirmed_count=1,
                created_by="u-1",
                created_at=datetime.now(UTC),
            )
        )
        db.add(
            CaseItem(
                id="item-1",
                case_set_id="set-1",
                strategy="positive",
                priority="P1",
                name="登录成功",
                steps="1. 输入正确账号密码",
                expected="进入工作台",
            )
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


def test_delete_hides_from_list_and_detail(case_set_case):
    resp = case_set_case.client.delete("/api/case-sets/set-1")
    assert resp.status_code == 204, resp.text

    assert case_set_case.client.get("/api/case-sets/set-1").status_code == 404
    listed = case_set_case.client.get("/api/case-sets").json()
    assert [row["id"] for row in listed["items"]] == ["set-2"]


def test_delete_keeps_rows_and_writes_audit(case_set_case):
    assert case_set_case.client.delete("/api/case-sets/set-1").status_code == 204

    with case_set_case.factory() as db:
        case_set = db.get(CaseSet, "set-1")
        assert case_set is not None and case_set.deleted_at is not None
        # 行数据保留：审计回溯要能看到当时的内容。
        assert db.get(CaseItem, "item-1") is not None
        audit = db.query(AuditLog).filter(AuditLog.action == "case_set_delete").one()
        assert audit.target_id == "set-1"
        assert audit.detail["name"] == "草稿用例集"


def test_delete_is_idempotent_for_confirmed_set(case_set_case):
    """已入库同样可删（软删），且第二次删除返回 404 而不是 500。"""
    assert case_set_case.client.delete("/api/case-sets/set-2").status_code == 204
    assert case_set_case.client.delete("/api/case-sets/set-2").status_code == 404
    with case_set_case.factory() as db:
        assert db.get(CaseSet, "set-2").deleted_at is not None
