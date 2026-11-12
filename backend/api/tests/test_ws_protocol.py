"""WebSocket 流式事件语义回归测试。"""

import asyncio

import pytest

from app.models import Session as AgentSession
from app.models import User
from app.routers import ws


class _MessageDb:
    """承载用户消息写入流程的最小数据库桩。"""

    def __init__(self) -> None:
        self.row = None

    def add(self, row) -> None:
        self.row = row

    def query(self, *_args):
        """模拟幂等键查询，默认没有重复消息。"""
        return self

    def filter(self, *_args):
        return self

    def first(self):
        return None

    def flush(self) -> None:
        self.row.id = "m-1"

    def commit(self) -> None:
        pass


@pytest.mark.asyncio
async def test_user_echo_uses_user_message_event(monkeypatch):
    """用户回显必须使用独立事件，不能再占用助手 message 语义。"""
    emitted: list[str] = []

    async def fake_emit(_db, _websocket, _state, _session_id, event, _payload):
        emitted.append(event)
        return True

    async def fake_run_turn(*_args, **_kwargs):
        return None

    monkeypatch.setattr(ws, "_emit_persistent", fake_emit)
    monkeypatch.setattr(ws, "_run_turn", fake_run_turn)

    task = await ws._handle_user_message(
        _MessageDb(),
        object(),
        ws._ConnectionState(),
        AgentSession(id="s-1", user_id="u-1", title="测试会话", visibility="private"),
        User(id="u-1", username="alice"),
        {"text": "你好", "attachments": [], "client_message_id": "browser-1"},
        None,
    )
    await task

    assert emitted == ["user_message"]


def test_response_completed_keeps_public_identifiers():
    """完成事件沿用公共头并携带 assistant 生命周期信息。"""
    frame = ws._frame(
        "s-1",
        "response.completed",
        8,
        {"finish_reason": "stop", "role": "assistant"},
        task_id="t-1",
    )

    assert frame["session_id"] == "s-1"
    assert frame["task_id"] == "t-1"
    assert frame["event_id"] == 8
    assert frame["payload"] == {"finish_reason": "stop", "role": "assistant"}


def test_next_event_id_uses_session_counter():
    """事件号来自会话计数器（UPDATE ... RETURNING），会话不存在时按 1 兜底。"""

    class _Result:
        def __init__(self, row) -> None:
            self._row = row

        def first(self):
            return self._row

    class _Db:
        def __init__(self) -> None:
            self.executed: list[str] = []

        def execute(self, _sql, params):
            self.executed.append(params["session_id"])
            return _Result((4,) if params["session_id"] == "s-1" else None)

    db = _Db()
    assert ws._next_event_id(db, "s-1") == 4
    assert ws._next_event_id(db, "missing") == 1
    assert db.executed == ["s-1", "missing"]


def test_should_forward_worker_event() -> None:
    """转发循环只推 Worker 直产：progress/report，以及带 task_id 的 error。"""
    assert ws._should_forward_worker_event("progress", None) is True
    assert ws._should_forward_worker_event("report", "t-1") is True
    assert ws._should_forward_worker_event("error", "t-1") is True
    assert ws._should_forward_worker_event("error", None) is False
    assert ws._should_forward_worker_event("assistant_message", None) is False


@pytest.mark.asyncio
async def test_forward_loop_pushes_worker_events_and_skips_agent_error(monkeypatch):
    """M9-D8：按游标增量推送 Worker 事件，对话内 error 只推进游标不重发。"""

    class _Row:
        def __init__(self, event_id: int, event: str, payload: dict, task_id: str | None):
            self.event_id = event_id
            self.event = event
            self.payload = payload
            self.task_id = task_id
            self.ts = None

    from app.agent import ws_event_poller as poller_mod

    sent: list[dict] = []

    async def fake_broadcast(_session_id: str, frame: dict) -> bool:
        sent.append(frame)
        return True

    monkeypatch.setattr(
        poller_mod.SESSION_CONNECTION_HUB, "broadcast_event", fake_broadcast
    )
    poller = poller_mod.WsEventPoller()

    await poller._dispatch(
        {"session_id": "s-1", "task_id": "t-1", "event_id": 5, "event": "progress", "payload": {"percent": 10}, "ts": None}
    )
    # error 无 task_id 属于对话内错误，已由 _emit_persistent 发出，不再转发
    await poller._dispatch(
        {"session_id": "s-1", "task_id": None, "event_id": 6, "event": "error", "payload": {"code": "INTERNAL"}, "ts": None}
    )
    await poller._dispatch(
        {"session_id": "s-1", "task_id": "t-1", "event_id": 7, "event": "report", "payload": {"report_id": "r-1"}, "ts": None}
    )

    assert [frame["event"] for frame in sent] == ["progress", "report"]
    assert [frame["event_id"] for frame in sent] == [5, 7]



