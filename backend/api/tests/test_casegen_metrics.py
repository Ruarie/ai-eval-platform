"""用例生成质量看板聚合回归（SQLite 功能验证）。"""

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
    event,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import CaseItem, CaseReviewRun, CaseSet, Task, User

_NEEDED_MODELS = (User, Task, CaseSet, CaseItem, CaseReviewRun)


@pytest.fixture
def metrics_case():
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

    now = datetime.now(UTC)
    with factory.begin() as db:
        db.add(User(id="member", username="member", password_hash="test"))
        db.add_all(
            [
                Task(
                    id="task-1",
                    kind="testcase",
                    status="succeeded",
                    config={"max_count": 10},
                    result={
                        "case_set_id": "set-1",
                        "generated_count": 8,
                        "profile_id": "profile-a",
                        "profile_name": "主力模型",
                        "model_name": "model-a",
                    },
                    created_by="member",
                    created_at=now,
                    started_at=now,
                    finished_at=now,
                ),
                Task(
                    id="task-2",
                    kind="testcase",
                    status="failed",
                    config={"max_count": 5},
                    result={"error_code": "UPSTREAM"},
                    created_by="member",
                    created_at=now,
                ),
            ]
        )
        db.add(
            CaseSet(
                id="set-1",
                task_id="task-1",
                name="支付用例集",
                status="generated",
                generated_count=8,
                confirmed_count=6,
                review_state="approved",
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
                    module="支付",
                    name="支付成功",
                ),
                CaseItem(
                    id="case-2",
                    case_set_id="set-1",
                    strategy="反向",
                    priority="YC",
                    module="支付",
                    name="支付失败",
                ),
                CaseItem(
                    id="case-3",
                    case_set_id="set-1",
                    strategy="边界",
                    priority="BJ",
                    module="退款",
                    name="退款边界",
                ),
                CaseReviewRun(
                    id="run-1",
                    case_set_id="set-1",
                    score=70,
                    verdict="needs_fix",
                    summary="旧评审",
                    case_count=8,
                    created_at=datetime(2026, 11, 8, tzinfo=UTC),
                ),
                CaseReviewRun(
                    id="run-2",
                    case_set_id="set-1",
                    score=90,
                    verdict="pass",
                    summary="新评审",
                    case_count=8,
                    created_at=datetime(2026, 11, 9, tzinfo=UTC),
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
    case = SimpleNamespace(factory=factory, client=client, now=now, engine=engine)
    try:
        yield case
    finally:
        app.dependency_overrides = old_overrides


def test_casegen_metrics_aggregates(metrics_case):
    """运行数、生成/确认、采纳率、最新 AI 分与模型聚合。"""
    response = metrics_case.client.get("/api/metrics/casegen", params={"days": 30})
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["total_runs"] == 2
    # 未超过聚合上限：truncated=false，且 matched_runs 与参与聚合的运行数一致
    assert data["truncated"] is False
    assert data["matched_runs"] == 2
    assert data["sample_limit"] == 1000
    assert data["succeeded_runs"] == 1
    assert data["failed_runs"] == 1
    assert data["total_generated"] == 8
    assert data["total_confirmed"] == 6
    assert data["adoption_rate"] == 0.75
    assert data["ai_scored_runs"] == 1
    assert data["avg_ai_score"] == 90.0
    assert data["review_approved"] == 1

    assert len(data["series"]) == 30
    today = data["series"][-1]
    assert today["runs"] == 2
    assert today["generated"] == 8
    assert today["confirmed"] == 6

    assert data["by_model"][0]["model_name"] == "model-a"
    assert data["by_model"][0]["runs"] == 1
    assert data["by_model"][0]["adoption_rate"] == 0.75

    modules = {item["module"]: item["case_count"] for item in data["modules"]}
    assert modules == {"支付": 2, "退款": 1}

    recent = {item["task_id"]: item for item in data["recent"]}
    assert recent["task-1"]["ai_score"] == 90
    assert recent["task-1"]["adoption_rate"] == 0.75
    assert recent["task-2"]["error_code"] == "UPSTREAM"


def test_casegen_metrics_skips_review_body_and_task_progress(metrics_case):
    """聚合不读取评审正文和任务进度快照。"""
    statements: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(metrics_case.engine, "before_cursor_execute", capture)
    try:
        response = metrics_case.client.get("/api/metrics/casegen", params={"days": 30})
    finally:
        event.remove(metrics_case.engine, "before_cursor_execute", capture)

    assert response.status_code == 200, response.text
    joined = "\n".join(statements)
    assert "summary" not in joined
    assert "dimensions" not in joined
    assert "issues" not in joined
    assert "progress" not in joined
    assert "column_schema" not in joined
    assert "checks" not in joined


def test_casegen_metrics_one_day(metrics_case):
    """单日窗口仍返回完整聚合，趋势长度与 days 一致。"""
    response = metrics_case.client.get("/api/metrics/casegen", params={"days": 1})
    assert response.status_code == 200
    data = response.json()
    assert data["total_runs"] == 2
    assert data["avg_ai_score"] == 90.0
    assert len(data["series"]) == 1


def test_casegen_metrics_marks_truncated_sample(metrics_case, monkeypatch):
    """超过聚合上限时回传 truncated/matched_runs，成功率分母只代表样本。"""
    from app.routers import metrics as metrics_router

    monkeypatch.setattr(metrics_router, "MAX_RUNS", 1)
    response = metrics_case.client.get("/api/metrics/casegen", params={"days": 30})
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["truncated"] is True
    assert data["matched_runs"] == 2
    assert data["sample_limit"] == 1
    assert data["total_runs"] == 1
    assert data["success_rate"] in (0.0, 1.0)


def test_casegen_metrics_validates_days(metrics_case):
    """days 超出 1–365 按统一 VALIDATION 返回 400，不静默截断。"""
    assert metrics_case.client.get("/api/metrics/casegen", params={"days": 0}).status_code == 400
    assert metrics_case.client.get("/api/metrics/casegen", params={"days": 366}).status_code == 400
