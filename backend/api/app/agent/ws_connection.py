"""WS 连接生命周期：短票鉴权、订阅登记、收包分派与清理。

所有 ws 模块级依赖统一经 ``ws_router.X`` 访问，保证既有测试对 ``ws.<name>``
的打桩继续生效（与回合执行同一约定）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import uuid4

logger = logging.getLogger("ai-eval.ws")


async def handle_connection(websocket: Any) -> None:
    """建立短票认证的 WS 会话，并保持 receive 循环不等待模型整轮完成。"""
    from ..routers import ws as ws_router

    db = ws_router.SessionLocal()
    user: ws_router.User | None = None
    session: ws_router.AgentSession | None = None
    state = ws_router._ConnectionState()
    connection_id = uuid4().hex
    heartbeat_stop = asyncio.Event()
    heartbeat_task: asyncio.Task[None] | None = None
    active_turn: asyncio.Task[None] | None = None
    try:
        try:
            user = ws_router._consume_ws_ticket(db, websocket.query_params.get("ticket"))
            session_id = websocket.query_params.get("session_id")
            if session_id:
                session = ws_router.require_visible_session(db, session_id, user.id)
                if getattr(session, "engine_version", "legacy") == "agent_loop_v2":
                    await websocket.close(code=4400, reason="该会话请使用 WS v2 协议")
                    return
            else:
                # 禁止旧入口隐式创建 legacy 会话，避免绕过 AgentLoop 的会话绑定。
                await websocket.close(code=4400, reason="新会话请使用 AgentLoop WS v2 协议")
                return
            raw_last_event_id = websocket.query_params.get("last_event_id", "0")
            last_event_id = max(0, int(raw_last_event_id))
        except ws_router.AppError as exc:
            close_code = 4404 if exc.code == ws_router.ErrorCode.NOT_FOUND else 4401
            await websocket.close(code=close_code, reason="会话不存在" if close_code == 4404 else "WebSocket 短票无效")
            return
        except ValueError:
            await websocket.close(code=4401, reason="WebSocket 连接参数无效")
            return
        except Exception as exc:
            db.rollback()
            logger.error("Agent WS 建连失败 type=%s", type(exc).__name__)
            await websocket.close(code=4401, reason="WebSocket 鉴权失败")
            return

        await websocket.accept()
        ws_router.SESSION_CONNECTION_HUB.register(
            connection_id,
            session.id,
            user.id,
            websocket,
            state,
            ready=False,
        )
        state.cursor = last_event_id
        await ws_router._send(
            websocket,
            state,
            ws_router._frame(session.id, "pong", state.cursor, {}),
        )
        await ws_router._replay_events(db, websocket, state, session.id, last_event_id)
        if not await ws_router.SESSION_CONNECTION_HUB.activate(session.id, connection_id):
            return
        heartbeat_task = asyncio.create_task(
            ws_router._heartbeat_loop(
                websocket,
                state,
                session.id,
                ws_router._heartbeat_interval(db),
                heartbeat_stop,
            ),
            name=f"agent-heartbeat-{session.id}",
        )

        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await ws_router._emit_error(
                    db,
                    websocket,
                    state,
                    session.id,
                    ws_router.AppError(ws_router.ErrorCode.VALIDATION, "WebSocket 消息不是有效 JSON"),
                )
                continue
            if not isinstance(message, dict):
                await ws_router._emit_error(
                    db,
                    websocket,
                    state,
                    session.id,
                    ws_router.AppError(ws_router.ErrorCode.VALIDATION, "WebSocket 消息必须是对象"),
                )
                continue

            event = message.get("event")
            try:
                if event == "user_message":
                    payload = message.get("payload")
                    if isinstance(payload, dict):
                        text = payload.get("text")
                        if isinstance(text, str):
                            stripped = text.strip()
                            if stripped.startswith("/stop"):
                                # /stop 即时中断：不进图，直接取消当前回合（§2.5）
                                await ws_router._handle_stop(
                                    db,
                                    websocket,
                                    state,
                                    session.id,
                                    active_turn,
                                    user.id,
                                )
                                continue
                    active_turn = await ws_router._handle_user_message(
                        db,
                        websocket,
                        state,
                        session,
                        user,
                        message.get("payload"),
                        active_turn,
                    )
                elif event == "cancel_task":
                    payload = (
                        message.get("payload")
                        if isinstance(message.get("payload"), dict)
                        else {}
                    )
                    result = ws_router.cancel_task_safe(
                        payload,
                        ws_router.ToolExecutionContext(
                            session_id=session.id,
                            user_id=user.id,
                            thread_id=session.id,
                            call_id="ws-cancel",
                        ),
                    )
                    await ws_router._emit_persistent(
                        db,
                        websocket,
                        state,
                        session.id,
                        "task_cancelled",
                        {
                            "status": result.get("status"),
                            "kind": result.get("kind"),
                        },
                        task_id=str(result.get("task_id") or "") or None,
                    )
                elif event == "confirm_ack":
                    # V1.67 恢复：确认卡回执——行锁事务校验 + 后台重放回合
                    # （入队唯一经 W6），收包循环只派生任务，不 await 整轮图。
                    await ws_router._handle_confirm_ack(
                        db,
                        websocket,
                        state,
                        session.id,
                        str(user.id),
                        message.get("payload")
                        if isinstance(message.get("payload"), dict)
                        else {},
                    )
                elif event == "tool_approval_ack":
                    # H5 HITL 审批回执：行锁校验（卡存在/种类/owner/id/action）
                    # → 清卡提交 → 以原 thread_id 恢复检查点回合（resume 至多一次）。
                    await ws_router._handle_approval_ack(
                        db,
                        websocket,
                        state,
                        session.id,
                        str(user.id),
                        message.get("payload")
                        if isinstance(message.get("payload"), dict)
                        else {},
                    )
                elif event == "clarify_reply":
                    # #1 澄清卡回执（V1.72 转正）：answers 校验 → 行锁清卡 →
                    # clarify_ack 回执 → 以原 thread_id 恢复回合（resume 至多一次）。
                    await ws_router._handle_clarify_reply(
                        db,
                        websocket,
                        state,
                        session.id,
                        str(user.id),
                        message.get("payload")
                        if isinstance(message.get("payload"), dict)
                        else {},
                    )
                else:
                    raise ws_router.AppError(ws_router.ErrorCode.VALIDATION, "不支持的 WebSocket 事件")
            except ws_router.AppError as exc:
                await ws_router._emit_error(db, websocket, state, session.id, exc)
    except ws_router.WebSocketDisconnect:
        logger.info("Agent WS 断开 session=%s", session.id if session else "unknown")
    finally:
        heartbeat_stop.set()
        cleanup_tasks = [task for task in (heartbeat_task,) if task is not None]
        for task in cleanup_tasks:
            task.cancel()
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        if session:
            ws_router.SESSION_CONNECTION_HUB.unregister(session.id, connection_id)
        db.close()
