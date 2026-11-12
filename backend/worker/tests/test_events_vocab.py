"""dsh 改进 #4：worker push_ws 写库带词汇版本断言（D5 测试清单）。"""

from __future__ import annotations

from shared.event_vocab import EVENT_VERSION

from app.events import push_ws


def test_push_ws_injects_event_version_and_does_not_mutate_caller_payload(monkeypatch) -> None:
    """写库 payload 内嵌版本保留字段；调用方 payload 不被污染（拷贝语义）。"""
    added: list[object] = []

    class _FakeWsEvent:
        """只保留构造参数，断言由测试读取。"""

        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class _Db:
        def add(self, row) -> None:
            added.append(row)

        def commit(self) -> None:
            pass

        def rollback(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr("app.events.WsEvent", _FakeWsEvent)
    monkeypatch.setattr("app.events.SessionLocal", _Db)
    # 事件号统一由 shared.event_seq 分配，这里只验证写库载荷。
    monkeypatch.setattr("app.events.next_event_id", lambda _db, _sid: 1)

    payload = {"percent": 10, "message": "进度"}
    push_ws("s-1", "progress", payload, task_id="t-1")

    assert len(added) == 1
    stored = added[0].kwargs
    assert stored["session_id"] == "s-1"
    assert stored["event_id"] == 1
    assert stored["event"] == "progress"
    assert stored["payload"]["percent"] == 10
    assert stored["payload"]["event_version"] == EVENT_VERSION
    # 调用方 payload 不得被注入保留字段
    assert "event_version" not in payload


def test_push_ws_skips_when_session_missing(monkeypatch) -> None:
    """会话不存在（取号返回 None）时不写事件、不抛错。"""
    added: list[object] = []

    class _Db:
        def add(self, row) -> None:
            added.append(row)

        def commit(self) -> None:
            pass

        def rollback(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr("app.events.SessionLocal", _Db)
    monkeypatch.setattr("app.events.next_event_id", lambda _db, _sid: None)

    push_ws("gone", "progress", {"percent": 1})

    assert added == []


def test_push_ws_skips_without_session() -> None:
    """无会话 ID 时静默跳过，不触碰数据库。"""
    assert push_ws(None, "progress", {"percent": 1}) is None
