"""待处理卡片（任务确认 / 工具审批 / 澄清）的单行互斥持久化。

会话只有一列 ``pending_confirm``：三类卡共用这一行，语义是「同一时刻只能有一张
待处理卡」。此前 ws 层三处实现各写一遍行锁 + 判空 + 白名单，任何一处漏判都会
让两张卡互相覆盖；这里收敛成单一入口：

- :func:`lock_idle_session` 行锁会话并确认当前没有待处理卡（有卡即 CONCURRENCY）；
- :func:`store_card` 按类型白名单裁剪字段、附加 meta 后写入并提交。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.errors import AppError, ErrorCode
from app.models import Session as AgentSession

# 每类卡片允许落库的字段白名单；None 表示任务确认卡按 TaskSpec 原样保存
# （TaskSpec 本身就是白名单校验过的结构，只是额外带一个 confirm_author 需剥离）。
CARD_FIELDS: dict[str, frozenset[str] | None] = {
    "task_confirm": None,
    "tool_approval": frozenset(
        {"id", "call_id", "name", "command", "reason", "risk_level", "sandbox_scope"}
    ),
    "clarify": frozenset({"id", "questions"}),
}


def lock_idle_session(db: Session, session_id: str) -> AgentSession:
    """行锁会话并确认没有待处理卡。

    已有任何种类的卡（确认/审批/澄清）都拒绝写入：团队协作下不能抢占别人正在
    处理的卡，调用方据此返回 CONCURRENCY。
    """
    session = (
        db.query(AgentSession)
        .filter(AgentSession.id == session_id)
        .with_for_update()
        .first()
    )
    if not session:
        raise AppError(ErrorCode.NOT_FOUND, "会话不存在")
    if session.pending_confirm is not None:
        raise AppError(ErrorCode.CONCURRENCY, "会话存在待处理任务卡，请先确认或取消")
    return session


def store_card(
    db: Session,
    session: AgentSession,
    *,
    kind: str,
    payload: dict[str, Any],
    meta: dict[str, Any],
    author_id: str,
) -> dict[str, Any]:
    """按类型裁剪字段并写入 ``pending_confirm``；返回实际落库的卡（含 meta）。"""
    fields = CARD_FIELDS[kind]
    card = (
        dict(payload)
        if fields is None
        else {key: value for key, value in payload.items() if key in fields}
    )
    card["meta"] = meta
    session.pending_confirm = card
    session.pending_confirm_author_id = author_id
    db.commit()
    return card


def card_meta(
    *,
    schema_version: int,
    owner_id: str,
    thread_id: str | None,
    confirm_type: str,
    resume_nonce: str | None = None,
) -> dict[str, Any]:
    """H5 恢复协议元数据（写入卡 JSONB 的 ``meta`` 键）。

    字段：schema_version / confirm_type / thread_id / owner_id / created_at；
    工具审批与澄清卡另带一次性 resume_nonce（消费即失效——并发/重复恢复由行锁
    与清卡保证至多一次）。
    """
    meta: dict[str, Any] = {
        "schema_version": schema_version,
        "confirm_type": confirm_type,
        "thread_id": thread_id or "",
        "owner_id": owner_id,
        "created_at": datetime.now(UTC).isoformat(),
    }
    if resume_nonce:
        meta["resume_nonce"] = resume_nonce
    return meta
