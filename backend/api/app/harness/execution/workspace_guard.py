"""旧原生执行器也遵守新工作区隔离；生命周期注入数据库，不由灰度开关关闭。"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select, text

from app.errors import AppError, ErrorCode
from app.harness.memory.agent_events import canonical_scope, scopes_overlap
from app.models import Session, WorkspaceExecutionGuard

_session_factory = None
# 显式退场标记：只在 ``shutdown()`` 时置位。此时仍在跑的线程池工具必须
# fail-closed，不能因为拿不到工厂就绕过工作区互斥（关闭期间的静默直通）。
_shutdown = False


def configure(session_factory) -> None:
    """注入/撤销共享数据库；撤销后回到「未注入」状态（直通）。

    ``configure(None)`` 必须保持既有语义（离线执行器与单测直接执行），
    不能顺手当成「关闭」：应用寿命期结束要调用 ``shutdown()``。
    两者混用会让「撤销注入」变成永久 fail-closed，污染同进程内后续调用。
    """
    global _session_factory, _shutdown
    _session_factory = session_factory
    _shutdown = False


def shutdown() -> None:
    """应用关闭：此后旧执行器调用 fail-closed，不再接受未受控的工作区写入。"""
    global _session_factory, _shutdown
    _session_factory = None
    _shutdown = True


def guarded_call(definition, context, execute):
    """线程真实结束后才结算 guard；协程超时取消不会提前解除隔离。"""
    factory = _session_factory
    if definition.permission_policy.workspace == "none":
        return execute()
    if factory is None:
        if _shutdown:
            raise AppError(ErrorCode.INTERNAL, "执行隔离端口已关闭，拒绝未受控的旧执行器调用")
        return execute()
    if not context.session_id or not context.user_id or not context.sandbox_dir:
        raise AppError(ErrorCode.UNAUTHORIZED, "工作区执行缺少已认证上下文")
    scope = canonical_scope(context.sandbox_dir)
    access = definition.permission_policy.workspace
    execution_id = str(uuid4())
    with factory() as db, db.begin():
        db.execute(text("SELECT pg_advisory_xact_lock(721904)"))
        session = db.execute(select(Session).where(Session.id == context.session_id).with_for_update()).scalar_one_or_none()
        if session is None or session.deleted_at is not None:
            raise AppError(ErrorCode.NOT_FOUND, "会话不存在")
        guards = db.execute(select(WorkspaceExecutionGuard).where(WorkspaceExecutionGuard.status != "released")).scalars()
        for guard in guards:
            if scopes_overlap(scope, guard.scope_path) and (guard.status == "quarantined" or access != "read" or guard.access != "read"):
                raise AppError(ErrorCode.CONCURRENCY, "工作区存在运行中或结果未知的冲突执行")
        db.add(WorkspaceExecutionGuard(execution_id=execution_id, session_id=context.session_id,
                                      scope_path=scope, access=access, status="active",
                                      attempt_id="legacy", call_id=context.call_id or execution_id,
                                      owner_id=context.user_id, evidence={"engine": "legacy", "tool": definition.name}))
    result = None
    try:
        result = execute()
        return result
    finally:
        # 旧 Runner 错误不含可靠停止证据，保留未知状态。API 崩溃则 active 行仍拦截。
        unknown = result is None or (definition.name == "bash" and not result.ok)
        with factory() as db, db.begin():
            db.execute(text("SELECT pg_advisory_xact_lock(721904)"))
            guard = db.get(WorkspaceExecutionGuard, execution_id)
            guard.status = "quarantined" if unknown else "released"
            guard.evidence = {**guard.evidence, "thread_finished": True, "outcome_unknown": unknown}
