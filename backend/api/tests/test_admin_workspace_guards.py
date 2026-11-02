"""结果未知的工作区执行隔离必须存在可审计的人工解除通道。"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.errors import AppError, ErrorCode
from app.main import app
from app.models import WorkspaceExecutionGuard
from app.routers.workspace_guards import release_quarantined_guard

pytest_plugins = ["tests.test_loop_tools_pg"]


def test_guard_endpoints_require_authentication() -> None:
    """隔离记录含工作区绝对路径，未登录不得读取或解除。"""
    client = TestClient(app)
    assert client.get("/api/admin/workspace-guards").status_code == 401
    response = client.post(
        "/api/admin/workspace-guards/exec-1/release",
        json={"reason": "确认远端进程已退出"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def _dispatch(log, tmp_path, *, execution_id: str, call_id: str = "remote-call") -> dict:
    """写入一条仍处于 active 的派发事实。"""
    identity = {"turn": 1, "step": 1, "attempt_id": "attempt-guard", "call_id": call_id}
    log.append(
        "tool/dispatch",
        {**identity, "execution_id": execution_id, "scope_path": str(tmp_path), "access": "write"},
    )
    return identity


def test_release_rejects_running_execution(pg_logs, tmp_path) -> None:
    """active 表示执行仍可能在写，必须拒绝人工解除。"""
    logs, factory = pg_logs
    execution_id = str(uuid4())
    _dispatch(logs[0], tmp_path, execution_id=execution_id)
    with factory() as db:
        with pytest.raises(AppError) as caught:
            release_quarantined_guard(db, execution_id, actor_id="test-user", reason="确认已退出")
        assert caught.value.code == ErrorCode.CONCURRENCY
        db.rollback()


def test_release_quarantined_execution_keeps_evidence(pg_logs, tmp_path) -> None:
    """结果未知的隔离可解除，原始派发证据保留并附人工解除记录。"""
    logs, factory = pg_logs
    execution_id = str(uuid4())
    identity = _dispatch(logs[0], tmp_path, execution_id=execution_id)
    logs[0].append("tool/result", {**identity, "status": "outcome_unknown", "content": "unknown"})

    with factory() as db:
        guard = release_quarantined_guard(
            db, execution_id, actor_id="test-user", reason="实例已重启，确认无残留进程"
        )
        db.commit()
        assert guard.status == "released"
        assert guard.evidence["manual_release"]["reason"] == "实例已重启，确认无残留进程"
        assert guard.evidence["manual_release"]["actor_id"] == "test-user"

    with factory() as db:
        stored = db.execute(
            select(WorkspaceExecutionGuard).where(
                WorkspaceExecutionGuard.execution_id == execution_id
            )
        ).scalar_one()
        assert stored.status == "released"
        assert stored.evidence["manual_release"]["actor_id"] == "test-user"

    # 重复解除返回冲突，不再产生第二条审计语义。
    with factory() as db:
        with pytest.raises(AppError) as caught:
            release_quarantined_guard(db, execution_id, actor_id="test-user", reason="重复操作")
        assert caught.value.code == ErrorCode.CONCURRENCY
        db.rollback()


def test_release_unknown_execution_is_not_found(pg_logs) -> None:
    """不存在的执行 ID 不得静默成功。"""
    _logs, factory = pg_logs
    with factory() as db:
        with pytest.raises(AppError) as caught:
            release_quarantined_guard(db, "missing-execution", actor_id="test-user", reason="确认已退出")
        assert caught.value.code == ErrorCode.NOT_FOUND
        db.rollback()
