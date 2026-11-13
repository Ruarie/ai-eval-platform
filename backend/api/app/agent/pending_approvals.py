"""待处理卡的时效判定与审批超时清理。

卡本身由 ``pending_cards`` 落库；这里负责「卡活了多久、是否该失效、过期后怎么
广播终态」——TTL 语义只在配置里定义一次，扫描路径与 ack 路径共用同一判龄函数，
天然幂等。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session, load_only

from ..config import settings
from ..db import SessionLocal
from ..models import Session as AgentSession

logger = logging.getLogger("ai-eval.ws")

# 审批卡 TTL 扫描节拍：30s 足够覆盖「5 分钟未处理即失效」的粒度。
APPROVAL_EXPIRY_POLL_S = 30.0


def card_age_seconds(card: Mapping[str, Any] | None) -> float | None:
    """解析卡 meta.created_at（UTC ISO）相对当前时间的年龄秒数。

    卡无 meta / created_at 缺失或不可解析时返回 None（调用方按不判龄处理——
    旧版无时间戳卡保持原语义，由扫描或重启后自然消费/清理）。
    """
    if not isinstance(card, Mapping):
        return None
    meta = card.get("meta")
    if not isinstance(meta, Mapping):
        return None
    raw = meta.get("created_at")
    try:
        parsed = datetime.fromisoformat(str(raw or "").replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return (datetime.now(UTC) - parsed).total_seconds()


def approval_overdue(card: Mapping[str, Any] | None) -> bool:
    """审批卡是否已超 TTL 失效（TTL ≤ 0 表示不启用过期，config 可关）。

    判龄以卡创建时间为锚，任何进程（扫描或 ack 路径）都可独立得出同一结论，
    天然幂等；扫描缺席时 ack 路径仍拒绝过期卡，不会绕过失效语义恢复回合。
    """
    ttl = settings.agent_approval_ttl_seconds
    if ttl <= 0:
        return False
    age = card_age_seconds(card)
    return age is not None and age > ttl


def clear_pending_confirm(db: Session, session_id: str) -> None:
    """清空待确认卡（与回执同事务提交，避免入队成功而卡标残留）。"""
    db.execute(
        text(
            "UPDATE sessions SET pending_confirm = NULL, pending_confirm_author_id = NULL "
            "WHERE id = :session_id"
        ),
        {"session_id": session_id},
    )


async def expire_overdue_approvals_once() -> int:
    """单轮 TTL 扫描：行锁清过期 tool_approval 卡并广播 expired 终态。

    只处理 ``meta.confirm_type=tool_approval`` 的卡（task_confirm / clarify
    不受审批 TTL 约束，保持各自生命周期）；锁内二次判龄与清卡同事务，
    与 ack/stop 并发竞争时后到者行锁读空自然跳过，幂等不重复广播。
    返回本轮过期清卡数。
    """
    # 广播依赖 ws 模块的帧构造与连接态；延迟导入避免循环依赖。
    from ..routers import ws as ws_router

    expired: list[tuple[str, str]] = []
    db = SessionLocal()
    try:
        # 只加载标识与卡片，其余会话大字段延迟读取（不产生额外查询）。
        rows = (
            db.query(AgentSession)
            .options(load_only(AgentSession.id, AgentSession.pending_confirm))
            .filter(AgentSession.pending_confirm.isnot(None))
            .all()
        )
        for session in rows:
            session_id = session.id
            card = session.pending_confirm or {}
            meta = card.get("meta") if isinstance(card.get("meta"), dict) else {}
            approval_id = str(card.get("id") or "")
            if meta.get("confirm_type") != "tool_approval" or not approval_id:
                continue
            if not approval_overdue(card):
                continue
            # 锁内二次判定：与 ack 清卡并发时，卡已消费/被刷新则跳过
            locked = (
                db.query(AgentSession)
                .filter(AgentSession.id == session_id)
                .with_for_update()
                .first()
            )
            if locked is None or locked.pending_confirm is None:
                continue
            locked_card = dict(locked.pending_confirm)
            if (
                not approval_overdue(locked_card)
                or str(locked_card.get("id") or "") != approval_id
            ):
                continue
            clear_pending_confirm(db, session_id)
            db.commit()
            expired.append((session_id, approval_id))
        state = ws_router._ConnectionState()
        for session_id, approval_id in expired:
            # 无在线连接时仅落库（websocket=None）；在线者经 Hub 广播收到，
            # 离线者断线重连按 last_event_id 回放补齐终态。
            await ws_router._emit_persistent(
                db,
                None,
                state,
                session_id,
                "approval_terminal",
                {
                    "approval_id": approval_id,
                    "outcome": "expired",
                    "card_type": "approval",
                    "reason": "审批超时已失效",
                },
                task_id=None,
            )
        return len(expired)
    except Exception as exc:  # noqa: BLE001 - 扫描失败不应终止后台循环
        db.rollback()
        logger.info("Agent 审批 TTL 扫描失败 type=%s", type(exc).__name__)
        return 0
    finally:
        db.close()


async def approval_expiry_loop() -> None:
    """后台审批卡 TTL 扫描循环（api lifespan 注册，参照 checkpoint_ttl_loop）。"""
    while True:
        await asyncio.sleep(APPROVAL_EXPIRY_POLL_S)
        await expire_overdue_approvals_once()
