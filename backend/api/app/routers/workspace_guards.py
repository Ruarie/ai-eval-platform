"""隔离中的工作区执行记录：查询与人工解除通道（P0-1）。

背景：Runner 崩溃、断连或旧执行器返回失败时，`workspace_execution_guards` 会停在
``quarantined``。`SessionLog.reconcile_execution`` 只接受 Runner 提供的可信停止收据
（``process_tree_terminated`` 等），崩溃场景拿不到该收据 → 该会话工作区的 read/write/
bash 全部被 409 拒绝，且没有任何解除入口，会话被永久砖化。

本接口只做**有审计的人工解除**，不伪造 Runner 证据：
- 仅 ``quarantined`` 可解除（``active`` 说明执行仍在跑，拒绝；已 ``released`` 幂等冲突）；
- 必须提供原因（便于事后追责），写 ``AuditLog``；
- guard.evidence 保留原派发证据，追加 ``manual_release`` 记录操作人与原因；
- 不写 ``execution/reconciled`` 事实：该事实是「可信对账」语义，只由 Runner 收据产生，
  人工解除不改变历史 ``tool/result`` 结论。

注意：人工解除意味着操作者确认该工作区已无边界外的进程在写。解除后同一 scope 的
新执行会立即放行，因此只在确认远端进程已随实例退出后使用。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..errors import AppError, ErrorCode
from ..models import AuditLog, User, WorkspaceExecutionGuard
from ..schemas import ApiModel, OrmOut

router = APIRouter(prefix="/api/admin/workspace-guards", tags=["admin"])

# 与 SessionLog._append 的 guard 注册表锁一致：解除与新派发在同一把锁下串行。
_GUARD_LOCK_SQL = "SELECT pg_advisory_xact_lock(721904)"


class WorkspaceGuardOut(OrmOut):
    execution_id: str
    session_id: str
    scope_path: str
    access: str
    status: str
    attempt_id: str
    call_id: str
    owner_id: str
    evidence: dict
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorkspaceGuardReleaseIn(ApiModel):
    """人工解除输入：原因必填，作为审计证据的一部分持久化。"""

    reason: str = Field(min_length=4, max_length=500)


def release_quarantined_guard(
    db: Session, execution_id: str, *, actor_id: str, reason: str
) -> WorkspaceExecutionGuard:
    """在调用方事务内解除隔离；不提交，由路由与审计同事务提交。"""
    db.execute(text(_GUARD_LOCK_SQL))
    guard = db.execute(
        select(WorkspaceExecutionGuard)
        .where(WorkspaceExecutionGuard.execution_id == execution_id)
        .with_for_update()
    ).scalar_one_or_none()
    if guard is None:
        raise AppError(ErrorCode.NOT_FOUND, "执行记录不存在")
    if guard.status == "released":
        raise AppError(ErrorCode.CONCURRENCY, "该执行已解除隔离")
    if guard.status != "quarantined":
        raise AppError(ErrorCode.CONCURRENCY, "执行仍在进行中，不能人工解除")
    guard.status = "released"
    guard.evidence = {
        **guard.evidence,
        "manual_release": {
            "actor_id": actor_id,
            "reason": reason,
            "released_at": datetime.now(UTC).isoformat(),
        },
    }
    return guard


@router.get("", response_model=list[WorkspaceGuardOut])
def list_workspace_guards(
    status: Literal["active", "quarantined", "released"] | None = Query(default=None),
    session_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """按状态/会话查询执行隔离记录；默认返回最近更新的记录。"""
    query = select(WorkspaceExecutionGuard)
    if status is not None:
        query = query.where(WorkspaceExecutionGuard.status == status)
    if session_id is not None:
        query = query.where(WorkspaceExecutionGuard.session_id == session_id)
    query = query.order_by(WorkspaceExecutionGuard.updated_at.desc()).limit(limit)
    return list(db.scalars(query))


@router.post("/{execution_id}/release", response_model=WorkspaceGuardOut)
def release_workspace_guard(
    execution_id: str,
    body: WorkspaceGuardReleaseIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """人工解除结果未知的执行隔离，并写入审计日志。"""
    reason = body.reason.strip()
    if len(reason) < 4:
        raise AppError(ErrorCode.VALIDATION, "请填写至少 4 个字符的解除原因")
    guard = release_quarantined_guard(db, execution_id, actor_id=user.id, reason=reason)
    db.add(
        AuditLog(
            user_id=user.id,
            action="workspace_guard_release",
            target_type="workspace_execution_guard",
            target_id=execution_id,
            detail={
                "session_id": guard.session_id,
                "scope_path": guard.scope_path,
                "access": guard.access,
                "reason": reason,
            },
            ip=request.client.host if request.client else None,
        )
    )
    db.commit()
    db.refresh(guard)
    return guard
