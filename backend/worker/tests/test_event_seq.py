"""会话事件号取号：单调递增、按会话隔离、计数器落后时对齐。"""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from shared.event_seq import next_event_id, realign_event_seq
from shared.models import Session as AgentSession
from shared.models import User, WsEvent


def _factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'seq.db'}")
    User.__table__.create(engine)
    AgentSession.__table__.create(engine)
    WsEvent.__table__.create(engine)
    return engine, sessionmaker(engine, autoflush=False)


def test_next_event_id_is_monotonic_and_per_session(tmp_path):
    """同一会话按 1、2、3 递增；不同会话互不影响；会话不存在返回 None。"""
    engine, factory = _factory(tmp_path)
    try:
        with factory() as db:
            db.add(User(id="u-1", username="u", password_hash="x"))
            db.add(AgentSession(id="s-1", user_id="u-1", title="t"))
            db.add(AgentSession(id="s-2", user_id="u-1", title="t"))
            db.commit()

            assert next_event_id(db, "s-1") == 1
            db.commit()
            assert next_event_id(db, "s-1") == 2
            db.commit()
            assert next_event_id(db, "s-2") == 1
            db.commit()
            assert next_event_id(db, "missing") is None
    finally:
        engine.dispose()


def test_realign_event_seq_moves_counter_to_history_max(tmp_path):
    """计数器落后于历史（迁移窗口/人工导入）时，对齐后从历史最大值继续发号。"""
    engine, factory = _factory(tmp_path)
    try:
        with factory() as db:
            db.add(User(id="u-1", username="u", password_hash="x"))
            db.add(AgentSession(id="s-1", user_id="u-1", title="t"))
            db.commit()
            db.add(WsEvent(session_id="s-1", event_id=9, event="progress", payload={}))
            db.commit()
            db.execute(text("UPDATE sessions SET last_event_id = 2 WHERE id = 's-1'"))
            db.commit()

            realign_event_seq(db, "s-1")
            db.commit()
            assert next_event_id(db, "s-1") == 10
            db.commit()

            # 已是最大值时只增不减，重复对齐不会让号回退
            db.execute(text("UPDATE sessions SET last_event_id = 4 WHERE id = 's-1'"))
            db.commit()
            realign_event_seq(db, "s-1")
            db.commit()
            assert next_event_id(db, "s-1") == 10
    finally:
        engine.dispose()
