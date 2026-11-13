"""断线回放：游标承接、重复事件跳过（回放模块独立后可单独测）。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import app.routers.ws as ws
from app.agent import ws_replay


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_a, **_k):
        return self

    def order_by(self, *_a, **_k):
        return self

    def all(self):
        return self._rows


class _Db:
    def __init__(self, rows):
        self._rows = rows

    def query(self, *_a, **_k):
        return _Query(self._rows)


def _row(event_id: int, event: str = "progress"):
    return SimpleNamespace(event_id=event_id, event=event, payload={"n": event_id}, task_id=None, ts=None)


def test_replay_advances_cursor_and_skips_old_rows(monkeypatch) -> None:
    sent: list[dict] = []

    async def fake_send(_ws, frame):
        sent.append(frame)
        return True

    monkeypatch.setattr(ws, "_send_unlocked", fake_send)
    monkeypatch.setattr(ws, "_frame", lambda sid, event, eid, payload, **_k: {"id": eid, "event": event})
    monkeypatch.setattr(ws, "_split_event_version", lambda payload: (payload, None))

    state = SimpleNamespace(cursor=1, lock=asyncio.Lock())

    async def case() -> None:
        await ws_replay.replay_events(_Db([_row(2), _row(3)]), object(), state, "s-1", 1)

    asyncio.run(case())

    assert [frame["id"] for frame in sent] == [2, 3]
    assert state.cursor == 3


def test_replay_only_carries_cursor_when_no_rows(monkeypatch) -> None:
    monkeypatch.setattr(ws, "_send_unlocked", lambda *_a, **_k: None)
    state = SimpleNamespace(cursor=0, lock=asyncio.Lock())

    async def case() -> None:
        await ws_replay.replay_events(_Db([]), object(), state, "s-1", 7)

    asyncio.run(case())
    # 即使没有待补发事件，也要承接客户端游标，避免从 0 重扫
    assert state.cursor == 7
