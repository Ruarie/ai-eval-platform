"""`/stop` 中止当前回合并处理悬挂审批卡。

与回合取消的竞态约定：有活跃后台任务时只置取消位，由回合任务自己发唯一
``response.completed``；没有活跃回合时才在这里清卡并补发 cancelled 终态。
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.orm import Session

from ..errors import AppError, ErrorCode


async def handle_stop(
    db: Session,
    websocket: Any,
    state: Any,
    session_id: str,
    active_turn: asyncio.Task[None] | None,
    user_id: str | None = None,
) -> None:
    """/stop 中止当前 Harness 回合，并限制为本轮发起成员执行。

    骨架版无人工中断（澄清/危险工具确认），/stop 仅取消活跃图回合；活跃
    回合由后台任务统一发送唯一 ``response.completed``，避免 stop 与任务竞态重复收尾。
    """
    from ..routers import ws as ws_router

    with ws_router._TURN_LOCK:
        turn = ws_router._SESSION_TURNS.get(session_id)
    owner = turn.user_id if turn else None
    if user_id and owner and str(user_id) != str(owner):
        raise AppError(ErrorCode.UNAUTHORIZED, "仅本轮发起成员可以执行 /stop")

    abort = turn.abort if turn else ws_router._SESSION_ABORTS.get(session_id)
    active = False
    if turn and (turn.task is None or not turn.task.done()):
        active = True
        turn.abort.set()
        if turn.task is not None and turn.started:
            turn.task.cancel()
    elif active_turn and not active_turn.done():
        active = True
        if abort:
            abort.set()
        active_turn.cancel()
    # 有活跃后台任务时不在收包循环抢发 completed，由 _run_turn 的取消分支收尾。
    if active:
        return
    # #3（V1.73）：无活跃回合时若存在本成员悬挂的审批卡，/stop 视为放弃本轮
    # 交互——清卡并广播 cancelled 终态（与用户 reject 语义区分），避免卡无限
    # 期悬挂阻塞后续回合；非本成员卡不动（团队协作不越权）。
    try:
        pending = ws_router.lock_pending_confirm(db, session_id)
    except AppError:
        pending = None
    if pending is not None and pending.pending is not None:
        card = dict(pending.pending)
        meta = card.get("meta") if isinstance(card.get("meta"), dict) else {}
        approval_id = str(card.get("id") or "")
        if (
            meta.get("confirm_type") == "tool_approval"
            and approval_id
            and pending.author_id
            and (user_id is None or str(pending.author_id) == str(user_id))
        ):
            ws_router._clear_pending_confirm(db, session_id)
            db.commit()
            try:
                await ws_router._emit_persistent(
                    db,
                    websocket,
                    state,
                    session_id,
                    "approval_terminal",
                    {
                        "approval_id": approval_id,
                        "outcome": "cancelled",
                        "card_type": "approval",
                        "reason": "/stop 已放弃本轮审批",
                    },
                    task_id=None,
                )
            except Exception as exc:  # noqa: BLE001 —— 终态广播尽力而为（已清卡，
                # 记录失败即可）；completed 收尾绝不能被吞（每轮恰一终态铁律）
                db.rollback()
                ws_router.agent_trace(f"/stop 终态广播失败 type={type(exc).__name__}")
    await ws_router._emit_turn_completed(
        db,
        websocket,
        state,
        session_id,
        finish_reason="cancelled",
        turn_id=turn.turn_id if turn else None,
    )
