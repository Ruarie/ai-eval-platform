"""待处理卡片持久化：单行互斥与字段白名单的统一入口。"""

from types import SimpleNamespace

import pytest

from app.agent.pending_cards import CARD_FIELDS, card_meta, lock_idle_session, store_card
from app.errors import AppError, ErrorCode


class _Db:
    """只覆盖卡片写入所需的最小会话桩。"""

    def __init__(self, session):
        self._session = session
        self.commits = 0

    def query(self, *_args):
        return self

    def filter(self, *_args):
        return self

    def with_for_update(self):
        return self

    def first(self):
        return self._session

    def commit(self):
        self.commits += 1


def _session(pending=None):
    return SimpleNamespace(pending_confirm=pending, pending_confirm_author_id=None, user_id="u-1")


def test_lock_idle_session_rejects_when_any_card_pending():
    """三类卡共用一行：已有任意卡时不得覆盖，返回 CONCURRENCY。"""
    db = _Db(_session({"id": "card-1", "meta": {"confirm_type": "clarify"}}))

    with pytest.raises(AppError) as exc:
        lock_idle_session(db, "s-1")

    assert exc.value.code == ErrorCode.CONCURRENCY


def test_lock_idle_session_returns_session_when_idle():
    session = _session()
    assert lock_idle_session(_Db(session), "s-1") is session


def test_store_card_filters_whitelist_and_attaches_meta():
    """审批卡只落白名单字段，meta 由调用方传入，author 一并写入。"""
    session = _session()
    db = _Db(session)
    meta = card_meta(schema_version=2, owner_id="u-1", thread_id="t-1", confirm_type="tool_approval", resume_nonce="n-1")

    card = store_card(
        db,
        session,
        kind="tool_approval",
        payload={"id": "call-1", "name": "bash", "command": "ls", "raw": "不该落库"},
        meta=meta,
        author_id="u-1",
    )

    assert card == {"id": "call-1", "name": "bash", "command": "ls", "meta": meta}
    assert session.pending_confirm is card
    assert session.pending_confirm_author_id == "u-1"
    assert db.commits == 1
    assert "raw" not in CARD_FIELDS["tool_approval"]


def test_store_card_keeps_task_spec_fields_as_is():
    """任务确认卡按 TaskSpec 原样保存（白名单为 None），仅补 meta。"""
    session = _session()
    meta = card_meta(schema_version=2, owner_id="u-1", thread_id=None, confirm_type="task_confirm")

    card = store_card(
        _Db(session),
        session,
        kind="task_confirm",
        payload={"id": "spec-1", "kind": "testcase", "goal": "登录"},
        meta=meta,
        author_id="u-1",
    )

    assert card["kind"] == "testcase" and card["goal"] == "登录"
    assert card["meta"]["confirm_type"] == "task_confirm"
    assert card["meta"]["thread_id"] == ""
