"""会话内 WS 事件号的统一取号（api 与 worker 共用）。

事件号必须按会话单调且不重复，历史实现是「锁会话行 → SELECT MAX(event_id) → 插入」，
每个事件三次往返。现在 ``sessions.last_event_id`` 保存计数器，一条
``UPDATE ... RETURNING`` 同时完成加锁与取号，并发下不会撞号，也不再扫索引。

计数器可能落后于历史（迁移窗口内旧版进程仍在写、或人工导入历史事件），
:func:`realign_event_seq` 提供一次性对齐：插入撞唯一键时调用它再重试。
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

# 加一并返回新值；会话不存在时无行返回（调用方按业务语义处理）。
_NEXT_SQL = text(
    "UPDATE sessions SET last_event_id = last_event_id + 1 "
    "WHERE id = :session_id RETURNING last_event_id"
)
# 对齐到「计数器」与「历史最大事件号」的较大值：只增不减，避免回退。
# 用 CASE 而不是 GREATEST：后者是 PostgreSQL 方言，SQLite（单测）没有该函数。
_REALIGN_SQL = text(
    "UPDATE sessions SET last_event_id = CASE"
    "  WHEN last_event_id > COALESCE("
    "    (SELECT MAX(event_id) FROM ws_events WHERE session_id = :session_id), 0)"
    "  THEN last_event_id"
    "  ELSE COALESCE("
    "    (SELECT MAX(event_id) FROM ws_events WHERE session_id = :session_id), 0)"
    "END WHERE id = :session_id"
)


def next_event_id(db: Session, session_id: str) -> int | None:
    """取下一个会话内事件号；会话不存在返回 ``None``。"""
    row = db.execute(_NEXT_SQL, {"session_id": session_id}).first()
    return int(row[0]) if row else None


def realign_event_seq(db: Session, session_id: str) -> None:
    """把计数器对齐到历史最大值（撞唯一键后的修复路径，需在回滚后调用）。"""
    db.execute(_REALIGN_SQL, {"session_id": session_id})
