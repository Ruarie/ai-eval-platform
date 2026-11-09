"""用例评审与版本历史路由回归（SQLite 功能验证）。

SQLite 只验证路由、ORM 映射与事务流程，不覆盖 PostgreSQL 行锁与并发语义。
"""

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
from app.models import (
    AuditLog,
    CaseItem,
    CaseReviewComment,
    CaseReviewRequest,
    CaseReviewRun,
    CaseSet,
    CaseSetVersion,
    Notification,
    User,
)

_NEEDED_MODELS = (
    User,
    CaseSet,
    CaseItem,
    CaseReviewRequest,
    CaseReviewComment,
    CaseReviewRun,
    CaseSetVersion,
    Notification,
    AuditLog,
)


@pytest.fixture
def review_case():
    """建立最小 SQLite 表集合并注入登录用户与数据库会话。"""
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
        db.add(
            CaseSet(
                id="set-1",
                name="登录用例集",
                status="generated",
                generated_count=2,
                confirmed_count=0,
                revision=0,
                created_by="member",
            )
        )
        db.add_all(
            [
                CaseItem(
                    id="case-1",
                    case_set_id="set-1",
                    strategy="正向",
                    priority="HX",
                    module="登录",
                    name="手机号登录成功",
                    expected="进入首页",
                    sort_order=0,
                ),
                CaseItem(
                    id="case-2",
                    case_set_id="set-1",
                    strategy="反向",
                    priority="YC",
                    module="登录",
                    name="手机号为空提示",
                    expected="提示请输入手机号",
                    sort_order=1,
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


def test_review_request_comment_and_approve(review_case):
    """发起评审 → 评论 → 通过；通过后自动生成版本快照。"""
    client = review_case.client
    initial = client.get("/api/case-sets/set-1/review")
    assert initial.status_code == 200
    assert initial.json()["review_state"] == "draft"
    assert initial.json()["active_request"] is None

    created = client.post(
        "/api/case-sets/set-1/review-requests",
        json={"assignee_id": "member", "note": "请检查边界", "due_at": "2026-11-12T10:00:00Z"},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["review_state"] == "reviewing"
    assert body["active_request"]["status"] == "pending"
    request_id = body["active_request"]["id"]

    duplicate = client.post("/api/case-sets/set-1/review-requests", json={})
    assert duplicate.status_code == 409

    comment = client.post(
        "/api/case-sets/set-1/comments",
        json={"body": "第二条用例预期不明确", "case_item_id": "case-2"},
    )
    assert comment.status_code == 200, comment.text
    assert len(comment.json()["comments"]) == 1
    assert comment.json()["comments"][0]["case_item_id"] == "case-2"

    approved = client.post(
        f"/api/case-sets/set-1/review-requests/{request_id}/decision",
        json={"decision": "approved", "note": "可以入库"},
    )
    assert approved.status_code == 200, approved.text
    data = approved.json()
    assert data["review_state"] == "approved"
    assert data["active_request"] is None
    assert data["latest_request"]["status"] == "approved"
    assert data["versions"][0]["reason"] == "review_approved"
    assert data["versions"][0]["case_count"] == 2


def test_changes_requested_requires_note(review_case):
    """要求修改必须填写原因；填写后状态变为 changes_requested。"""
    client = review_case.client
    created = client.post("/api/case-sets/set-1/review-requests", json={})
    request_id = created.json()["active_request"]["id"]

    missing = client.post(
        f"/api/case-sets/set-1/review-requests/{request_id}/decision",
        json={"decision": "changes_requested", "note": ""},
    )
    assert missing.status_code == 400

    changed = client.post(
        f"/api/case-sets/set-1/review-requests/{request_id}/decision",
        json={"decision": "changes_requested", "note": "补充异常路径"},
    )
    assert changed.status_code == 200
    assert changed.json()["review_state"] == "changes_requested"


def test_version_create_diff_and_restore(review_case):
    """手动存版、字段级 diff 与回滚为新草稿。"""
    client = review_case.client

    first = client.post("/api/case-sets/set-1/versions", json={"reason": "评审前"})
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 1

    # 修改一条用例后再存版，第二版应能对比出字段变化。
    with review_case.factory.begin() as db:
        item = db.get(CaseItem, "case-1")
        item.priority = "FHX"
        item.expected = "进入工作台"

    second = client.post("/api/case-sets/set-1/versions", json={"reason": "评审后"})
    assert second.status_code == 200
    assert second.json()["version"] == 2

    diff = client.get("/api/case-sets/set-1/versions/2/diff")
    assert diff.status_code == 200, diff.text
    payload = diff.json()
    assert payload["base_version"] == 1
    assert payload["changed_count"] == 1
    fields = {entry["field"] for entry in payload["changed"][0]["fields"]}
    assert fields == {"priority", "expected"}

    restored = client.post("/api/case-sets/set-1/versions/1/restore")
    assert restored.status_code == 200, restored.text
    new_id = restored.json()["case_set_id"]
    assert new_id != "set-1"

    detail = client.get(f"/api/case-sets/{new_id}")
    assert detail.status_code == 200
    assert len(detail.json()["cases"]) == 2
    assert detail.json()["cases"][0]["priority"] == "HX"


def test_confirmed_set_is_read_only_for_review(review_case):
    """已确认用例集不再接受新的评审请求，但历史仍可查看。"""
    with review_case.factory.begin() as db:
        db.get(CaseSet, "set-1").status = "confirmed"

    created = review_case.client.post("/api/case-sets/set-1/review-requests", json={})
    assert created.status_code == 400

    version = review_case.client.post("/api/case-sets/set-1/versions", json={"reason": "确认后"})
    assert version.status_code == 400

    workspace = review_case.client.get("/api/case-sets/set-1/review")
    assert workspace.status_code == 200
    assert workspace.json()["case_set_id"] == "set-1"
