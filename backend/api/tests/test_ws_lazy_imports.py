"""守卫：agent 子模块对 ws 路由的依赖只能以「函数内延迟导入」形式存在。

背景（改动前请先读完）：
agent 子模块（回合执行 / 停止 / 连接 / 事件翻译 / 回放 / 审批 TTL）需要 ws 模块的
会话表、广播原语与租约注册表。两种“清理”都会踩坑：

1. 改成模块级 import → routers.ws ↔ agent.* 形成真循环导入（启动即 ImportError）；
2. 把这些符号下沉到独立模块（如 ws_core）→ 现有 78 处
   ``monkeypatch.setattr(ws, ...)`` 全部失效（实测连带 4~7 个测试失败，
   因为 patch 重绑的是 ws 模块里的名字，而函数读的是新模块的全局）。

因此约定：只在函数体内 import，并保留「延迟导入」说明；``ws_event_poller`` 是
唯一例外（单向依赖，由 main.lifespan 在 ws 就绪后启动），已在源码注明。
"""

from __future__ import annotations

import ast
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1] / "app" / "agent"
# 允许模块级导入的单向依赖模块
MODULE_LEVEL_ALLOWED = {"ws_event_poller.py"}
# 期望存在延迟导入的模块（新增依赖时应同步更新此清单）
EXPECTED_MODULES = {
    "ws_turn.py",
    "ws_stop.py",
    "ws_connection.py",
    "ws_turn_events.py",
    "ws_replay.py",
    "pending_approvals.py",
}


def _ws_imports(path: Path) -> list[ast.ImportFrom]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.level == 2
        and node.module == "routers"
        and any(alias.name == "ws" for alias in node.names)
    ]


def test_only_expected_modules_depend_on_ws_router() -> None:
    found = {path.name for path in AGENT_DIR.glob("*.py") if _ws_imports(path)}
    assert found == EXPECTED_MODULES | MODULE_LEVEL_ALLOWED, (
        "依赖清单变化：如确需新增/移除，请同步更新本测试并说明原因"
    )


def test_lazy_imports_stay_inside_functions() -> None:
    for path in AGENT_DIR.glob("*.py"):
        if path.name in MODULE_LEVEL_ALLOWED:
            continue
        for node in _ws_imports(path):
            assert node.col_offset > 0, (
                f"{path.name}:{node.lineno} 必须写在函数体内（模块级会形成循环导入）"
            )


def test_lazy_imports_have_explanatory_comment() -> None:
    for path in AGENT_DIR.glob("*.py"):
        if path.name in MODULE_LEVEL_ALLOWED:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for node in _ws_imports(path):
            # 向上三行内出现「延迟导入」即视为已标注（说明块可能占多行）
            window = [line for line in lines[max(0, node.lineno - 4):node.lineno - 1] if line.strip()]
            assert any("延迟导入" in line for line in window), (
                f"{path.name}:{node.lineno} 缺少「延迟导入」说明（见模块 docstring）"
            )
