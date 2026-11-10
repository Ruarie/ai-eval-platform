"""报告列表批量投影回归（SQLite 功能验证）。

覆盖两件事：
1. 标题里的数据集版本与「先评后压」子报告仍按原语义解析；
2. 列表查询次数保持常数级，避免回退成逐行 N+1。
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import JSON, MetaData, create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import Dataset, Report, Task

_NEEDED_MODELS = (Dataset, Task, Report)


@pytest.fixture
def reports_case():
    """建立最小 SQLite 表集合：1 个数据集、1 个质量任务与 1 个派生压测任务。"""
    metadata = MetaData()
    for model in _NEEDED_MODELS:
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            column.foreign_keys.clear()
        table.constraints = {
            constraint for constraint in table.constraints if constraint.__class__.__name__ != "ForeignKeyConstraint"
        }
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    for table in metadata.tables.values():
        table.create(engine, checkfirst=True)
    factory = sessionmaker(engine, expire_on_commit=False)

    with factory.begin() as db:
        db.add(Dataset(id="ds-1", name="支付数据集", version=2, status="active"))
        db.add_all(
            [
                Task(
                    id="task-1",
                    kind="benchmark",
                    status="succeeded",
                    config={"dataset_id": "ds-1"},
                    progress={},
                    result={},
                    created_by="member",
                ),
                Task(
                    id="task-2",
                    kind="stress",
                    status="succeeded",
                    parent_task_id="task-1",
                    config={},
                    progress={},
                    result={},
                    created_by="member",
                ),
            ]
        )
        db.add_all(
            [
                Report(id="report-1", task_id="task-1", kind="benchmark", metrics={}),
                Report(id="report-2", task_id="task-2", kind="stress", metrics={}),
            ]
        )

    def database():
        with factory() as db:
            yield db

    old_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="member", username="member")
    client = TestClient(app)
    case = SimpleNamespace(client=client, engine=engine)
    try:
        yield case
    finally:
        app.dependency_overrides = old_overrides


def test_report_list_batches_relations(reports_case):
    """标题、派生压测报告与 total 正确，且单页查询次数为常数级。"""
    statements: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(reports_case.engine, "before_cursor_execute", capture)
    try:
        response = reports_case.client.get("/api/reports", params={"limit": 20})
    finally:
        event.remove(reports_case.engine, "before_cursor_execute", capture)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 2

    benchmark = next(item for item in data["items"] if item["id"] == "report-1")
    assert benchmark["title"] == "Benchmark 报告 · 支付数据集 v2"
    assert benchmark["child_stress_report_id"] == "report-2"

    stress = next(item for item in data["items"] if item["id"] == "report-2")
    assert stress["title"] == "共享压测报告 · 任务 task-2"
    assert stress["child_stress_report_id"] is None

    # 2 条报告：count + 列表 + 任务 + 数据集 + 子任务 + 子报告 ≈ 6 条；
    # 若回退 N+1，这里会随行数线性增长（每条 +2~3）。
    assert len(statements) <= 8, f"报告列表查询数异常: {len(statements)}"
    # 列表不读指标、分享令牌，也不读任务结果/进度。
    joined = "\n".join(statements)
    assert "metrics" not in joined
    assert "share_token" not in joined
    assert "tasks.result" not in joined and ".result" not in joined
    assert "progress" not in joined
