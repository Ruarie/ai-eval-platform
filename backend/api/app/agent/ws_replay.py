"""断线回放与消息窗口投影。

回放只做两件事：把客户端游标接上、把 ``event_id`` 之后的事件按序补发；窗口投影
负责把会话消息裁成模型可用的最近窗口（CX-1/CX-2）。两者都是只读逻辑，不持有
任何连接状态。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from ..agent.attachments import model_content_for_message
from ..harness.context import window_trim_stats
from ..models import Message, WsEvent
from ..models import Session as AgentSession

if TYPE_CHECKING:  # 仅类型引用，避免运行时循环导入
    from ..routers.ws import _ConnectionState


async def replay_events(
    db: Session,
    websocket: Any,
    state: _ConnectionState,
    session_id: str,
    last_event_id: int,
) -> None:
    """按 last_event_id 补发持久化事件，并先推进游标避免 Worker 旧事件重发。"""
    # 延迟导入：帧构造与发送节流都在 ws 模块，避免模块级循环依赖。
    from ..routers import ws as ws_router

    # 即使没有待补发事件，也必须承接客户端游标；否则转发会从 0 重扫。
    state.cursor = max(state.cursor, last_event_id)
    rows = (
        db.query(WsEvent)
        .filter(WsEvent.session_id == session_id, WsEvent.event_id > last_event_id)
        .order_by(WsEvent.event_id)
        .all()
    )
    # 回放与当前连接的广播共用同一把锁；Hub 会在锁外登记/排队新事件。
    async with state.lock:
        for row in rows:
            if row.event_id <= state.cursor:
                continue
            # #4：剥离词汇版本保留字段再回放；历史无版本行（V1.71 前）宽容兼容
            payload, _row_version = ws_router._split_event_version(row.payload or {})
            frame = ws_router._frame(
                session_id,
                row.event,
                row.event_id,
                payload,
                task_id=row.task_id,
                ts=row.ts,
            )
            if not await ws_router._send_unlocked(websocket, frame):
                return
            state.cursor = row.event_id


def window_messages(db: Session, session_id: str) -> tuple[list[dict], dict[str, object]]:
    """读取会话消息，经 Harness 窗口算法（CX-1）投影（含 source_id）。

    ``compact_keep_from`` 指定保留起点时截断更早消息；思考/工具/确认/进度
    事件不进窗口（CX-2）。窗口算法唯一来源为
    ``app.harness.context.window.recent_window``（#2 起经 window_trim_stats
    同源实现返回裁剪元信息，供 context_trim 留痕事件使用）。
    返回 ``(窗口消息, trim_meta)``；trim_meta.dropped>0 即本回合发生了窗口裁剪。
    """
    session = db.query(AgentSession).filter(AgentSession.id == session_id).first()
    # getattr 容错：会话行缺少该列（测试桩/旧快照）时按未压缩处理
    keep_from = getattr(session, "compact_keep_from", None) if session else None
    rows = (
        db.query(Message)
        .filter(Message.session_id == session_id, Message.role.in_(("user", "assistant")))
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(200)
        .all()
    )
    ordered = [
        {
            "role": row.role,
            # 附件装配（staging）在 model_content_for_message 内按会话绑定自行
            # 解析（resolve_session_sandbox_db，与回合注入同源同态——BLK-1）
            "content": model_content_for_message(db, row) if row.role == "user" else row.content,
            "source_id": row.source_id,
        }
        for row in reversed(rows)
    ]
    return window_trim_stats(ordered, limit=20, keep_from=keep_from)


def history_with_trim(
    db: Session, session_id: str
) -> tuple[list[dict[str, str]], dict[str, object]]:
    """窗口投影消息 + 裁剪元信息（#2 留痕用，与 window_messages 同一次查询）。"""
    windowed, meta = window_messages(db, session_id)
    return [{"role": item["role"], "content": item["content"]} for item in windowed], meta
