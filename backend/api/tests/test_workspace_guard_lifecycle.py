"""工作区隔离端口的生命周期语义：撤销注入 ≠ 关闭退场。

历史事故：``configure(None)`` 曾被当成「应用关闭」，导致 `test_loop_legacy_guard`
收尾时置位关闭标记，同进程后续所有原生工具用例都 fail-closed（CI 才暴露，因为
该文件依赖 PostgreSQL，本地会 skip）。这里固化两条语义，防止再退化。
"""

from types import SimpleNamespace

import pytest

from app.errors import AppError, ErrorCode
from app.harness.execution.context import ToolExecutionContext
from app.harness.execution.workspace_guard import configure, guarded_call, shutdown


def _context() -> ToolExecutionContext:
    return ToolExecutionContext(session_id="s-1", user_id="u-1", sandbox_dir="/tmp/ws")


def _write_definition() -> SimpleNamespace:
    return SimpleNamespace(name="write", permission_policy=SimpleNamespace(workspace="write"))


def test_configure_none_stays_passthrough_and_shutdown_fails_closed() -> None:
    """撤销注入保持直通；只有显式 shutdown 才 fail-closed。"""
    try:
        configure(None)
        assert guarded_call(_write_definition(), _context(), lambda: "executed") == "executed"

        shutdown()
        with pytest.raises(AppError) as caught:
            guarded_call(_write_definition(), _context(), lambda: "should-not-run")
        assert caught.value.code == ErrorCode.INTERNAL
    finally:
        configure(None)
    # 收尾后必须恢复直通，否则同进程后续用例会被污染。
    assert guarded_call(_write_definition(), _context(), lambda: "executed") == "executed"


def test_shutdown_still_allows_workspace_none_tools() -> None:
    """不碰文件系统的工具在关闭期也应放行。"""
    try:
        shutdown()
        definition = SimpleNamespace(name="search", permission_policy=SimpleNamespace(workspace="none"))
        assert guarded_call(definition, _context(), lambda: "ok") == "ok"
    finally:
        configure(None)
