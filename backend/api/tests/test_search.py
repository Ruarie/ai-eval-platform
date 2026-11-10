"""全局搜索真实路由回归：权限过滤、实体覆盖、类型筛选与空查询。

SQLite 只验证查询与权限投影，不声称覆盖 PostgreSQL 的 ILIKE 性能或索引计划。
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import (
    JSON,
    BigInteger,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    Text,
    create_engine,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import (
    CaseItem,
    CaseSet,
    Dataset,
    KnowledgeBase,
    KnowledgeMemory,
    Report,
    Task,
    User,
    Workspace,
)
from app.models import (
    Session as AgentSession,
)

_MODELS = (
    User,
    Workspace,
    AgentSession,
    KnowledgeMemory,
    Dataset,
    KnowledgeBase,
    CaseSet,
    CaseItem,
    Task,
    Report,
)


@pytest.fixture
def search_case():
    """建立最小 SQLite 表集合，并注入可切换的登录身份。"""
    metadata = MetaData()
    for model in _MODELS:
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            elif isinstance(column.type, BigInteger) and column.primary_key:
                column.type = Integer()
            elif column.name == "embedding":
                column.type = Text()
            # 只建最小表集合；移除指向未复制表的外键，避免 SQLite 建表排序失败。
            column.foreign_keys.clear()
        table.constraints = {
            constraint
            for constraint in table.constraints
            if not isinstance(constraint, ForeignKeyConstraint)
        }
        # 只复制到的表之间没有完整关系图；清空表级外键集合，SQLite 才能建表。
        table.foreign_keys.clear()
        # PostgreSQL 部分索引（pgvector/partial unique）在 SQLite 无对应语义。
        table.indexes = set()
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    with factory.begin() as db:
        db.add_all(
            [
                User(id="owner", username="owner", password_hash="test"),
                User(id="other", username="other", password_hash="test"),
            ]
        )
        db.flush()
        db.add_all(
            [
                Workspace(id="ws-pay", owner_id="owner", name="支付工作区", kind="local"),
                Workspace(id="ws-other", owner_id="other", name="支付他人工作区", kind="local"),
                CaseSet(
                    id="set-pay",
                    name="支付回归",
                    status="generated",
                    generated_count=1,
                    confirmed_count=0,
                    revision=0,
                    column_schema=[],
                    checks=[],
                ),
                CaseSet(
                    id="set-other",
                    name="其他模块",
                    status="generated",
                    generated_count=1,
                    confirmed_count=0,
                    revision=0,
                    column_schema=[],
                    checks=[],
                ),
                KnowledgeBase(id="kb-pay", name="支付知识库", kind="lightrag"),
                Dataset(id="ds-pay", name="支付数据集"),
                Task(
                    id="task-pay-1",
                    kind="testcase",
                    status="failed",
                    config={},
                    progress={},
                    result={},
                    created_by="owner",
                ),
                Task(
                    id="task-other",
                    kind="benchmark",
                    status="succeeded",
                    config={},
                    progress={},
                    result={},
                    created_by="other",
                ),
                Report(id="rep-pay", task_id="task-pay-1", kind="testcase", metrics={}),
                Report(id="rep-other", task_id="task-other", kind="benchmark", metrics={}),
                AgentSession(
                    id="sess-owner",
                    user_id="owner",
                    title="支付排查",
                    engine_version="agent_loop_v2",
                    visibility="private",
                ),
                AgentSession(
                    id="sess-other",
                    user_id="other",
                    title="支付私密",
                    engine_version="agent_loop_v2",
                    visibility="private",
                ),
                AgentSession(
                    id="sess-team",
                    user_id="other",
                    title="支付团队",
                    engine_version="agent_loop_v2",
                    visibility="team",
                ),
            ]
        )
        db.flush()
        db.add(
            CaseItem(
                id="case-pay",
                case_set_id="set-pay",
                strategy="正向",
                priority="P0",
                module="登录",
                name="手机号登录成功",
                steps="1. 输入手机号",
                expected="登录成功",
            )
        )
        memory_id = "mem-pay"
        db.add(
            KnowledgeMemory(
                id=memory_id,
                tenant_id="personal:owner",
                source_id="manual:" + memory_id,
                source_version=1,
                content="支付偏好：先给结论",
                meta={
                    "kind": "personal_memory",
                    "schema_version": 1,
                    "title": "支付偏好",
                    "category": "preference",
                    "workspace_id": None,
                },
                acl="private",
                acl_user_ids=["owner"],
                memory_revoked=False,
            )
        )

    case = SimpleNamespace(factory=factory, user_id="owner", engine=engine)

    def current_user():
        """每次请求重新读取用户，模拟真实 Cookie 解析后的身份。"""
        with factory() as db:
            return db.get(User, case.user_id)

    def database():
        """每个请求独立会话，避免测试间事务串扰。"""
        with factory() as db:
            yield db

    old_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_db] = database
    case.client = TestClient(app)
    try:
        yield case
    finally:
        case.client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(old_overrides)
        engine.dispose()


def _groups(payload):
    return {group["type"]: group for group in payload["groups"]}


def test_search_covers_assets_and_hides_private_sessions(search_case):
    response = search_case.client.get("/api/search", params={"q": "支付"})
    assert response.status_code == 200, response.text
    payload = response.json()
    groups = _groups(payload)

    assert "case" in groups and groups["case"]["items"][0]["title"] == "支付回归"
    assert "kb" in groups and groups["kb"]["items"][0]["title"] == "支付知识库"
    assert "dataset" in groups and groups["dataset"]["items"][0]["title"] == "支付数据集"
    assert "workspace" in groups and groups["workspace"]["items"][0]["title"] == "支付工作区"
    assert "memory" in groups and groups["memory"]["items"][0]["title"] == "支付偏好"

    session_titles = [item["title"] for item in groups["session"]["items"]]
    assert "支付排查" in session_titles
    assert "支付团队" in session_titles
    # 他人的私有会话不得出现在搜索结果中。
    assert "支付私密" not in session_titles
    # 他人的工作区同样不可见。
    assert all(item["title"] != "支付他人工作区" for item in groups["workspace"]["items"])


def test_search_matches_case_body_and_task_report_ids(search_case):
    case_body = search_case.client.get("/api/search", params={"q": "手机号"})
    assert case_body.status_code == 200
    assert _groups(case_body.json())["case"]["items"][0]["id"] == "set-pay"

    task = search_case.client.get("/api/search", params={"q": "task-pay"})
    assert task.status_code == 200
    task_items = _groups(task.json())["task"]["items"]
    assert task_items[0]["id"] == "task-pay-1"
    assert task_items[0]["url"] == "/tasks?id=task-pay-1"

    report = search_case.client.get("/api/search", params={"q": "rep-pay"})
    assert report.status_code == 200
    report_items = _groups(report.json())["report"]["items"]
    assert report_items[0]["id"] == "rep-pay"
    assert report_items[0]["url"] == "/reports/rep-pay"

    statements: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(search_case.engine, "before_cursor_execute", capture)
    try:
        probed = search_case.client.get("/api/search", params={"q": "task-pay"})
    finally:
        event.remove(search_case.engine, "before_cursor_execute", capture)
    assert probed.status_code == 200
    joined = "\n".join(statements)
    assert "tasks.config" not in joined and "tasks.result" not in joined and "tasks.progress" not in joined
    assert "reports.metrics" not in joined and "share_token" not in joined


def test_search_type_filter_limit_and_blank_query(search_case):
    only_case = search_case.client.get("/api/search", params={"q": "支付", "types": "case"})
    assert only_case.status_code == 200
    assert set(_groups(only_case.json())) == {"case"}

    limited = search_case.client.get("/api/search", params={"q": "支付", "limit": 1})
    assert limited.status_code == 200
    assert all(len(group["items"]) == 1 for group in limited.json()["groups"])

    blank = search_case.client.get("/api/search", params={"q": " "})
    assert blank.status_code == 200
    assert blank.json() == {"query": "", "groups": []}

    unknown_type = search_case.client.get("/api/search", params={"q": "支付", "types": "unknown"})
    assert unknown_type.status_code == 200
    assert unknown_type.json()["groups"] == []


def test_search_memory_is_scoped_to_current_user(search_case):
    search_case.user_id = "other"
    response = search_case.client.get("/api/search", params={"q": "支付偏好"})
    assert response.status_code == 200
    assert "memory" not in _groups(response.json())
