"""用例资产库服务与路由回归（SQLite 功能验证）。"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import JSON, BigInteger, ForeignKeyConstraint, Integer, MetaData, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.case_asset_service import materialize_case_set, similar_assets
from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import AuditLog, CaseAsset, CaseItem, CaseSet, User
from app.schemas import CaseAssetSimilarIn

_NEEDED_MODELS = (User, CaseSet, CaseItem, CaseAsset, AuditLog)


@pytest.fixture
def asset_case():
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
                status="confirmed",
                generated_count=3,
                confirmed_count=3,
                revision=2,
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
                    precondition="已注册用户",
                    steps="1. 输入手机号\n2. 输入密码\n3. 点击登录",
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
                    steps="1. 留空手机号\n2. 点击登录",
                    expected="提示请输入手机号",
                    sort_order=1,
                ),
                CaseItem(
                    id="case-3",
                    case_set_id="set-1",
                    strategy="边界",
                    priority="BJ",
                    module="支付",
                    name="支付金额上限",
                    steps="1. 输入最大金额\n2. 提交",
                    expected="提示金额超限",
                    sort_order=2,
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


def _materialize(asset_case):
    """确认用例集物化资产；重复调用应幂等。"""
    with asset_case.factory.begin() as db:
        case_set = db.get(CaseSet, "set-1")
        first = materialize_case_set(db, case_set, user_id="member")
        second = materialize_case_set(db, case_set, user_id="member")
    assert first == 3
    assert second == 0


def test_asset_search_stats_and_tags(asset_case):
    """物化、检索、统计与标签更新。"""
    _materialize(asset_case)
    client = asset_case.client

    listed = client.get("/api/case-assets")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["total"] == 3
    assert {item["name"] for item in body["items"]} == {"手机号登录成功", "手机号为空提示", "支付金额上限"}
    assert all(item["source_set_name"] == "登录用例集" for item in body["items"])

    filtered = client.get("/api/case-assets", params={"q": "手机号", "module": "登录"})
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 2

    modules = client.get("/api/case-assets", params={"module": "支付"})
    assert modules.json()["total"] == 1

    stats = client.get("/api/case-assets/stats")
    assert stats.status_code == 200
    assert stats.json()["total"] == 3
    assert stats.json()["source_sets"] == 1
    assert {row["module"] for row in stats.json()["modules"]} == {"登录", "支付"}

    asset_id = body["items"][0]["id"]
    tagged = client.put(
        f"/api/case-assets/{asset_id}/tags",
        json={"tags": ["冒烟", "登录", "冒烟", "  ", "这是一个超过二十个字符的标签需要被截断处理"]},
    )
    assert tagged.status_code == 200, tagged.text
    tags = tagged.json()["tags"]
    assert tags[:2] == ["冒烟", "登录"]
    assert len(tags) == 3
    assert len(tags[-1]) <= 20

    detail = client.get(f"/api/case-assets/{asset_id}")
    assert detail.status_code == 200
    assert detail.json()["tags"] == tags


def test_asset_similarity_candidates(asset_case):
    """相似度只返回候选，中文文本也能命中。"""
    _materialize(asset_case)
    client = asset_case.client
    response = client.post(
        "/api/case-assets/similar",
        json={"name": "手机号登录成功", "expected": "进入首页", "limit": 5},
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items
    assert items[0]["name"] == "手机号登录成功"
    assert items[0]["score"] >= 0.9

    with asset_case.factory() as db:
        candidates = similar_assets(
            db, CaseAssetSimilarIn(name="支付金额上限", expected="提示金额超限", limit=3)
        )
    assert candidates
    assert candidates[0].name == "支付金额上限"


def test_asset_backfill_and_missing(asset_case):
    """历史回填幂等；不存在的资产返回 404。"""
    client = asset_case.client
    first = client.post("/api/case-assets/backfill")
    assert first.status_code == 200, first.text
    assert first.json()["scanned_sets"] == 1
    assert first.json()["created_assets"] == 3

    second = client.post("/api/case-assets/backfill")
    assert second.status_code == 200
    assert second.json()["created_assets"] == 0

    missing = client.get("/api/case-assets/not-found")
    assert missing.status_code == 404
