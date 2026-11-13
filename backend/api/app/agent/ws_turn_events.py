"""图节点事件 → WS 持久化事件的翻译层（回合执行的出口）。

节点只产出纯数据；这里负责落库 ``assistant_message``、落确认卡，并把最终帧交给
``ws._emit_persistent``（延迟导入复用，避免循环依赖）。
"""

from __future__ import annotations

import logging
from typing import Any

from shared.event_vocab import EVENT_VERSION, PERSISTENT_KINDS
from sqlalchemy.orm import Session

from ..models import Message

logger = logging.getLogger("ai-eval.ws")


async def translate_event(
    db: Session,
    websocket: Any,
    state: Any,
    session_id: str,
    profile: Any,
    event: dict,
    *,
    turn_id: str | None = None,
    thread_id: str | None = None,
    user_id: str | None = None,
) -> None:
    """把图节点产出的 NodeEvent 翻译为 ws event（落库 + 统一 emit）。

    事件桥接契约（§2.5）：节点只返回纯数据，持久化事件全部经本函数落
    ``ws_events`` 并广播；``assistant_message`` 需先落库 Message 再构造对外
    payload（对齐 REST 历史回放格式）；``confirm``（V1.67 恢复）落
    ``sessions.pending_confirm`` 行锁并补 ``confirm_author`` 元数据。

    #4 D3 词汇表护栏：事件 ``event_version`` 与当前版本不符 → 按当前词汇表
    翻译 + 日志告警（图内事件与 ws.py 同版本部署，仅作漂移哨兵）；kind 不在
    注册表（PERSISTENT_KINDS）→ fail-closed：告警并跳过，绝不静默落库广播。
    """
    from ..routers import ws as ws_router

    kind = event["kind"]
    node_version = event.get("event_version")
    if not isinstance(kind, str) or kind not in PERSISTENT_KINDS:
        logger.error(
            "Agent 图产出未契约事件 kind=%s version=%s，已拒绝翻译落库",
            kind,
            node_version,
        )
        return
    if node_version is not None and node_version != EVENT_VERSION:
        logger.warning(
            "Agent 事件版本漂移 kind=%s version=%s current=%s，按当前词汇表翻译",
            kind,
            node_version,
            EVENT_VERSION,
        )
    payload = event.get("payload") or {}
    task_id = event.get("task_id")
    if kind == "response.completed" and not ws_router._claim_terminal(session_id, turn_id):
        return
    if kind == "assistant_message":
        assistant = Message(
            session_id=session_id,
            role="assistant",
            content=str(payload.get("text") or ""),
            attachments=[],
            author_id=None,
            client_message_id=None,
            latency_ms=int(payload.get("latency_ms") or 0),
            turn_stats=payload.get("turn_stats") or None,
            model_name=profile.model or profile.name if profile else None,
            profile_id=profile.id if profile else None,
            profile_name=profile.name if profile else None,
            provider=ws_router._infer_provider(profile),
            source_id="pending",
            source_version=1,
        )
        db.add(assistant)
        db.flush()
        assistant.source_id = f"message:{assistant.id}"
        db.commit()
        await ws_router._emit_persistent(
            db,
            websocket,
            state,
            session_id,
            "assistant_message",
            ws_router._assistant_message_payload(assistant),
            task_id=task_id,
        )
        return
    if kind == "error":
        await ws_router._emit_persistent(
            db,
            websocket,
            state,
            session_id,
            "error",
            {
                "code": str(payload.get("code") or "validation"),
                "message": str(payload.get("message") or "操作失败"),
            },
            task_id=task_id,
        )
        return
    if kind == "confirm":
        # V1.67 恢复：确认卡落 pending_confirm（行锁）+ 作者元数据；同一会话
        # 同一时刻至多一张卡，回执由收包循环 confirm_ack 处理（重放经 W6 入队）。
        # H5：卡 JSONB 附 meta 恢复协议（schema_version/thread_id/created_at）。
        outgoing = dict(payload)
        author = ws_router._confirm_author_payload(db, user_id)
        if author and "confirm_author" not in outgoing:
            outgoing["confirm_author"] = author
        ws_router._persist_pending_confirm(
            db,
            session_id,
            outgoing,
            thread_id=thread_id,
            user_id=user_id,
        )
        payload = outgoing
    await ws_router._emit_persistent(
        db,
        websocket,
        state,
        session_id,
        kind,
        dict(payload),
        task_id=task_id,
    )
