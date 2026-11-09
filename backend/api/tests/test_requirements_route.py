"""需求基线与覆盖率的真实路由回归（SQLite 功能验证）。

SQLite 只验证路由、ORM 映射与事务流程，不声称覆盖 PostgreSQL 行锁或
并发语义；生产迁移仍以 Alembic 为准。
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
    CaseRequirementLink,
    CaseSet,
    RequirementBaseline,
    RequirementItem,
    User,
)

_NEEDED_MODELS = (
    User,
    CaseSet,
    CaseItem,
    RequirementBaseline,
    RequirementItem,
    CaseRequirementLink,
    AuditLog,
)


@pytest.fixture
def requirement_case():
    """建立最小 SQLite 表集合并注入登录用户与数据库会话。"""
    metadata = MetaData()
    for model in _NEEDED_MODELS:
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            # SQLite 不支持 JSONB；测试只关心 JSON 结构，不改变共享 ORM。
            if isinstance(column.type, JSONB):
                column.type = JSON()
            elif isinstance(column.type, BigInteger) and column.primary_key:
                # SQLite 只有 INTEGER PRIMARY KEY 才自增。
                column.type = Integer()
            # 只建最小表集合；移除指向未复制表的外键，避免建表排序失败。
            column.foreign_keys.clear()
        table.constraints = {
            constraint
            for constraint in table.constraints
            if not isinstance(constraint, ForeignKeyConstraint)
        }
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    # 逐表建表，避免 SQLAlchemy 为未复制的外键目标做拓扑排序。
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
                    name="FR-101 手机号登录成功",
                    feature_point="FR-101",
                    expected="进入首页",
                ),
                CaseItem(
                    id="case-2",
                    case_set_id="set-1",
                    strategy="反向",
                    priority="YC",
                    module="登录",
                    name="手机号为空提示",
                    feature_point="手机号为空",
                    expected="提示请输入手机号",
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
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(old_overrides)
        engine.dispose()


def test_requirement_baseline_create_confirm_and_coverage(requirement_case):
    """创建 → 确认 → 绑定 → 自动候选 → 人工关联 → 覆盖率全链路。"""
    client = requirement_case.client

    created = client.post(
        "/api/requirement-baselines",
        json={
            "name": "登录需求 V1",
            "source_text": """
### 4.1 登录
| FR-101 | 支持手机号加密码登录 | P0 | 登录 |
| FR-102 | 手机号为空时提示 | P1 | 登录 |
""",
        },
    )
    assert created.status_code == 201, created.text
    baseline = created.json()
    assert baseline["status"] == "draft"
    assert baseline["requirement_count"] == 2
    assert [item["req_no"] for item in baseline["requirements"]] == ["FR-101", "FR-102"]
    baseline_id = baseline["id"]
    requirement_id = baseline["requirements"][0]["id"]

    # 草稿基线不能直接绑定。
    blocked = client.post(
        "/api/case-sets/set-1/requirement-baseline", json={"baseline_id": baseline_id}
    )
    assert blocked.status_code == 400
    assert blocked.json()["code"] == "VALIDATION"

    confirmed = client.post(f"/api/requirement-baselines/{baseline_id}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"

    bound = client.post(
        "/api/case-sets/set-1/requirement-baseline", json={"baseline_id": baseline_id}
    )
    assert bound.status_code == 200, bound.text
    assert bound.json()["coverage_percent"] == 0.0
    assert bound.json()["uncovered"][0]["req_no"] == "FR-101"

    auto = client.post(
        "/api/case-sets/set-1/requirements/auto-link",
        json={"baseline_id": baseline_id, "threshold": 0.3},
    )
    assert auto.status_code == 200, auto.text
    candidates = auto.json()["links"]
    assert any(link["case_item_id"] == "case-1" and link["confidence"] == 1.0 for link in candidates)

    linked = client.post(
        "/api/case-sets/set-1/requirements/link",
        json={
            "baseline_id": baseline_id,
            "links": [{"case_item_id": "case-1", "requirement_ids": [requirement_id]}],
        },
    )
    assert linked.status_code == 200, linked.text

    coverage = client.get("/api/case-sets/set-1/coverage")
    assert coverage.status_code == 200, coverage.text
    body = coverage.json()
    assert body["total"] == 2
    assert body["covered"] == 1
    assert body["coverage_percent"] == 50.0
    assert body["p0_total"] == 1
    assert body["p0_percent"] == 100.0
    assert body["linked_case_count"] == 1
    assert body["unlinked_case_count"] == 1


def test_requirement_baseline_rejects_text_without_numbers(requirement_case):
    """没有编号时不创建空基线，避免覆盖率分母为 0 的假象。"""
    response = requirement_case.client.post(
        "/api/requirement-baselines",
        json={"name": "无编号需求", "source_text": "用户应该可以登录。"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION"


def test_requirement_coverage_requires_binding(requirement_case):
    """未绑定基线时明确拒绝，不返回 0% 冒充无缺口。"""
    response = requirement_case.client.get("/api/case-sets/set-1/coverage")
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION"


def test_requirement_version_diff_and_impact(requirement_case):
    """从已确认基线派生新版本，分析差异与受影响用例。"""
    client = requirement_case.client
    created = client.post(
        "/api/requirement-baselines",
        json={
            "name": "登录需求 V1",
            "source_text": """
### 4.1 登录
| FR-101 | 支持手机号加密码登录 | P0 | 登录 |
| FR-102 | 手机号为空时提示 | P1 | 登录 |
""",
        },
    )
    assert created.status_code == 201, created.text
    base = created.json()
    base_id = base["id"]
    req_101 = base["requirements"][0]["id"]
    assert client.post(f"/api/requirement-baselines/{base_id}/confirm").status_code == 200
    assert client.post(
        "/api/case-sets/set-1/requirement-baseline", json={"baseline_id": base_id}
    ).status_code == 200
    assert client.post(
        "/api/case-sets/set-1/requirements/link",
        json={
            "baseline_id": base_id,
            "links": [{"case_item_id": "case-1", "requirement_ids": [req_101]}],
        },
    ).status_code == 200

    version = client.post(
        f"/api/requirement-baselines/{base_id}/versions",
        json={
            "name": "登录需求 V2",
            "source_text": """
### 4.1 登录
| FR-101 | 支持手机号加密码或验证码登录 | P0 | 登录 |
| FR-103 | 支持图形验证码 | P1 | 登录 |
""",
        },
    )
    assert version.status_code == 201, version.text
    target = version.json()
    target_id = target["id"]
    assert target["parent_id"] == base_id
    assert target["status"] == "draft"
    assert [item["req_no"] for item in target["requirements"]] == ["FR-101", "FR-103"]

    diff = client.get(f"/api/requirement-baselines/{target_id}/diff")
    assert diff.status_code == 200, diff.text
    body = diff.json()
    assert body["base_id"] == base_id
    assert body["added_count"] == 1
    assert body["removed_count"] == 1
    assert body["changed_count"] == 1
    assert body["removed"][0]["req_no"] == "FR-102"
    assert body["changed"][0]["req_no"] == "FR-101"

    impact = client.get(f"/api/requirement-baselines/{target_id}/impact")
    assert impact.status_code == 200, impact.text
    report = impact.json()
    assert report["affected_set_count"] == 1
    assert report["affected_case_count"] == 1
    assert report["sets"][0]["case_set_id"] == "set-1"
    assert report["cases"][0]["case_item_id"] == "case-1"
    assert report["cases"][0]["change_type"] == "changed"

    # 草稿版本不能作为新版本的父级；必须先确认。
    draft_child = client.post(
        f"/api/requirement-baselines/{target_id}/versions",
        json={"name": "V3", "source_text": "| FR-101 | 登录 | P0 | 登录 |"},
    )
    assert draft_child.status_code == 400

    assert client.post(f"/api/requirement-baselines/{target_id}/confirm").status_code == 200
    confirmed_child = client.post(
        f"/api/requirement-baselines/{target_id}/versions",
        json={"name": "V3", "source_text": "| FR-101 | 登录 | P0 | 登录 |"},
    )
    assert confirmed_child.status_code == 201
