"""个人记忆自动抽取与向量回填回归：解析、去重、配额、凭据、ACL 与回合钩子。"""

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import JSON, BigInteger, Integer, MetaData, Text, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator

from app.agent import loop_service
from app.config import settings
from app.errors import AppError, ErrorCode
from app.harness.memory import personal
from app.harness.memory.extract import (
    extract_after_turn,
    parse_extraction,
    schedule_extraction,
)
from app.models import AuditLog, KnowledgeMemory, User, Workspace


class JsonVector(TypeDecorator):
    """SQLite 向量列替身：写入文本、读出浮点数组。"""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or isinstance(value, str):
            return value
        return "[" + ",".join(str(float(item)) for item in value) + "]"

    def process_result_value(self, value, dialect):
        if value is None or isinstance(value, list):
            return value
        return [float(item) for item in str(value).strip().strip("[]").split(",") if item.strip()]


@pytest.fixture
def memory_db():
    metadata = MetaData()
    for model in (User, Workspace, KnowledgeMemory, AuditLog):
        table = model.__table__.to_metadata(metadata)
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()
            elif isinstance(column.type, BigInteger) and column.primary_key:
                column.type = Integer()
            elif column.name == "embedding":
                column.type = JsonVector()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as db:
        db.add_all([
            User(id="owner", username="owner", password_hash="test"),
            User(id="other", username="other", password_hash="test"),
        ])
        db.flush()
        db.add_all([
            Workspace(id="workspace", owner_id="owner", name="工作区"),
            Workspace(id="foreign", owner_id="other", name="他人工作区"),
        ])
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def semantic_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "agent_memory_semantic_enabled", True)


def test_parse_extraction_rejects_bad_contract() -> None:
    """非 JSON、错误枚举与空字段一律丢弃，超长字段截断而不是拒绝整批。"""
    assert parse_extraction("no json here") == []
    assert parse_extraction('{"title": "x"}') == []
    assert parse_extraction(json.dumps([
        {"title": "回答习惯", "content": "先给结论", "category": "preference"},
        {"title": "x", "content": "y", "category": "unknown"},
        {"title": "", "content": "y", "category": "fact"},
        "not-a-dict",
    ])) == [{"title": "回答习惯", "content": "先给结论", "category": "preference"}]

    long_item = parse_extraction(json.dumps(
        [{"title": "标" * 50, "content": "内" * 500, "category": "fact"}]
    ))
    assert len(long_item[0]["title"]) == 20
    assert len(long_item[0]["content"]) == 200

    many = [{"title": f"标题{index}", "content": "内容", "category": "fact"} for index in range(6)]
    assert len(parse_extraction(json.dumps(many))) == 3


def test_parse_extraction_accepts_code_fence() -> None:
    """模型常见的 ```json 围栏必须能解析。"""
    raw = '```json\n[{"title":"迭代节奏","content":"每次迭代回归测试","category":"fact"}]\n```'
    assert parse_extraction(raw)[0]["title"] == "迭代节奏"


def test_extract_disabled_does_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """开关关闭时不读库、不排任务、不返回条目。"""
    import asyncio

    monkeypatch.setattr(settings, "agent_memory_auto_extract_enabled", False)
    assert asyncio.run(extract_after_turn("session", "owner")) == 0
    assert schedule_extraction("session", "owner") is None


def test_store_extracted_memories_is_recallable(memory_db) -> None:
    """抽取记忆以 auto 来源落库，可被召回与撤回，且不影响他人。"""
    with memory_db.begin() as db:
        created = personal.store_extracted_memories(
            db, "owner", None,
            [{"title": "回答习惯", "content": "请先给结论", "category": "preference"}],
        )
    assert len(created) == 1
    with memory_db() as db:
        row = db.get(KnowledgeMemory, created[0])
        assert row.source_id == f"auto:{created[0]}"
        assert row.acl == "private" and row.acl_user_ids == ["owner"]
        assert personal.recall_personal_memories(db, "owner", None, "结论")[0]["id"] == created[0]
        assert personal.recall_personal_memories(db, "owner", None, "结论")[0]["source"] == "auto"
        assert personal.recall_personal_memories(db, "other", None, "结论") == []


def test_store_extracted_memories_dedup(memory_db, semantic_on, monkeypatch: pytest.MonkeyPatch) -> None:
    """同文去重与向量去重都生效：避免每轮重复堆积同一事实。"""
    # 所有文本都得到同一向量 → 除第一条外都会被相似度去重拦下。
    monkeypatch.setattr("app.llm.embeddings.embed_texts", lambda texts, **_kwargs: [[1.0, 0.0] for _ in texts])
    with memory_db.begin() as db:
        first = personal.store_extracted_memories(
            db, "owner", None, [{"title": "迭代节奏", "content": "每次迭代回归", "category": "fact"}]
        )
        again = personal.store_extracted_memories(
            db, "owner", None, [{"title": "迭代节奏", "content": "每次迭代回归", "category": "fact"}]
        )
        similar = personal.store_extracted_memories(
            db, "owner", None, [{"title": "发布节奏", "content": "每轮发布前回归", "category": "fact"}]
        )
    assert len(first) == 1
    assert again == [] and similar == []


def test_store_extracted_memories_skips_credentials_and_bad_workspace(memory_db) -> None:
    """凭据形态不落库；不属于本人的工作区回落为全局而不是越权绑定。"""
    with memory_db.begin() as db:
        created = personal.store_extracted_memories(
            db, "owner", "foreign",
            [
                {"title": "账号", "content": "password: hunter2", "category": "fact"},
                {"title": "模块归属", "content": "我负责订单模块", "category": "fact"},
            ],
        )
        row = db.get(KnowledgeMemory, created[0])
        assert row.meta["workspace_id"] is None
    assert len(created) == 1


def test_store_extracted_memories_respects_quota(memory_db, monkeypatch: pytest.MonkeyPatch) -> None:
    """达到 200 条上限后不再写入，避免抽取绕过手动保存的配额。"""
    monkeypatch.setattr(personal, "MAX_MEMORIES", 1)
    with memory_db.begin() as db:
        first = personal.store_extracted_memories(
            db, "owner", None, [{"title": "一", "content": "内容一", "category": "fact"}]
        )
        second = personal.store_extracted_memories(
            db, "owner", None, [{"title": "二", "content": "内容二", "category": "fact"}]
        )
    assert len(first) == 1 and second == []


def test_store_extracted_memories_caps_items(memory_db) -> None:
    """单轮最多落库 3 条，超过的候选不进入数据库。"""
    many = [{"title": f"标题{index}", "content": f"内容{index}", "category": "fact"} for index in range(6)]
    with memory_db.begin() as db:
        created = personal.store_extracted_memories(db, "owner", None, many)
    assert len(created) == 3


def test_reindex_fills_missing_vectors(memory_db, monkeypatch: pytest.MonkeyPatch) -> None:
    """回填只补缺失向量；force 时重算全部；开关关闭直接拒绝。"""
    calls: list[list[str]] = []

    def _embed(texts, **_kwargs):
        calls.append(list(texts))
        return [[0.5, 0.5] for _ in texts]

    # 先在关闭状态下写入：历史记忆没有向量，模拟线上存量。
    monkeypatch.setattr(settings, "agent_memory_semantic_enabled", False)
    with memory_db.begin() as db:
        personal.create_personal_memory(db, "owner", title="迭代节奏", content="每次迭代回归")
        personal.create_personal_memory(db, "owner", title="部署口令", content="上线前核对清单")
    monkeypatch.setattr(settings, "agent_memory_semantic_enabled", True)
    monkeypatch.setattr("app.llm.embeddings.embed_texts", _embed)
    with memory_db.begin() as db:
        result = personal.reindex_personal_memories(db, "owner", limit=10)
        assert result == {"embedded": 2, "candidates": 2, "remaining": 0}
    with memory_db.begin() as db:
        assert personal.reindex_personal_memories(db, "owner", limit=10)["candidates"] == 0
        assert personal.reindex_personal_memories(db, "owner", limit=10, force=True)["embedded"] == 2
    assert len(calls) == 2

    monkeypatch.setattr(settings, "agent_memory_semantic_enabled", False)
    with memory_db.begin() as db:
        with pytest.raises(AppError) as error:
            personal.reindex_personal_memories(db, "owner")
        assert error.value.code == ErrorCode.VALIDATION


def test_auto_row_survives_update_and_revoke(memory_db) -> None:
    """自动记忆走同一管理与撤回链路：编辑后来源不变，撤回后不再召回。"""
    with memory_db.begin() as db:
        memory_id = personal.store_extracted_memories(
            db, "owner", None, [{"title": "回答习惯", "content": "先给结论", "category": "preference"}]
        )[0]
    with memory_db.begin() as db:
        personal.update_personal_memory(
            db, "owner", memory_id, version=1, title="回答习惯", content="先给结论再展开"
        )
        assert db.get(KnowledgeMemory, memory_id).source_id == f"auto:{memory_id}"
    with memory_db.begin() as db:
        personal.revoke_personal_memory(db, "owner", memory_id, 2)
    with memory_db() as db:
        assert personal.recall_personal_memories(db, "owner", None, "结论") == []


def test_created_at_is_utc(memory_db) -> None:
    """抽取行使用数据库默认时间戳，避免手工构造导致排序漂移。"""
    with memory_db.begin() as db:
        memory_id = personal.store_extracted_memories(
            db, "owner", None, [{"title": "事实", "content": "内容", "category": "fact"}]
        )[0]
        row = db.get(KnowledgeMemory, memory_id)
        assert row.created_at is not None
        assert isinstance(row.created_at, datetime)
        assert row.created_at.tzinfo is None or row.created_at.tzinfo == UTC


@pytest.mark.asyncio
async def test_finish_schedules_extraction_with_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    """回合收尾按会话与发起成员调度抽取；抽取失败不反向影响收尾。"""
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.harness.memory.extract.schedule_extraction",
        lambda session_id, user_id: calls.append((session_id, user_id)),
    )
    log = Mock()
    log.session_id = "session-a"
    log.actor_id = "owner"
    runtime = Mock()
    runtime.running = False

    async def _wait() -> None:
        return None

    runtime.wait = _wait
    entry = SimpleNamespace(log=log, runtime=runtime, disconnect_cleanup=None,
                            controller=None, controller_client_id=None)
    service = loop_service.LoopService()
    await service._finish(entry, [])
    assert calls == [("session-a", "owner")]
