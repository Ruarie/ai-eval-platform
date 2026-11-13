"""工具分组注册。

由 ``build_default_registry`` 统一装配；``ToolDef`` 延迟导入避免循环依赖。
"""

from __future__ import annotations

from typing import Any

from ..policy import ToolPermissionPolicy, ToolRecoveryPolicy
from ..registry_handlers import (
    _bash_handler,
)


def register_bash_tool(registry: Any) -> None:
    """沙箱执行工具：bash（独立 Runner bwrap 沙箱，fail-closed）。"""
    from ..registry import ToolDef

    registry.register(
        ToolDef(
            name="bash",
            description=("在受控沙箱容器内执行 shell 命令（工作区可写、受资源限制；网络按权限档位）。"
                "仅用于用户明确要求的命令执行；不要用它探索工作区目录或查询平台数据，"
                "无法从工具拿到的信息直接说明情况。"),
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "command": {"type": "string", "description": "完整 shell 命令，仅在沙箱容器内运行"},
                    "description": {"type": "string", "description": "命令简短描述"},
                    "timeout": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "超时毫秒，封顶现有沙箱墙钟 15000",
                    },
                    "run_in_background": {"type": "boolean", "description": "必须为 false；true 会被拒绝"},
                    "dangerouslyDisableSandbox": {
                        "type": "boolean",
                        "description": "必须为 false；true 会被拒绝",
                    },
                },
                "required": ["command"],
            },
            permission="sandbox.bash",
            timeout_s=15.0,
            handler=_bash_handler,
            output_schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "stdout": {"type": "string"},
                    "stderr": {"type": "string"},
                    "exit_code": {"type": "integer"},
                    "duration_ms": {"type": "integer"},
                    "is_background": {"type": "boolean"},
                    "bash": {
                        "type": "object",
                        "properties": {
                            "exit_code": {"type": "integer"},
                            "preview": {"type": "string"},
                            "preview_truncated": {"type": "boolean"},
                        },
                    },
                },
            },
            permission_policy=ToolPermissionPolicy(workspace="write"),
            recovery_policy=ToolRecoveryPolicy(
                retryable_codes=frozenset({"TIMEOUT"}),
                suggested_action="reduce_command_scope",
                default_hint="请缩小命令处理范围；沙箱或安全策略拒绝时不得绕过重试。",
                max_auto_repairs=0,
            ),
            transport="native",
            display_name="沙箱命令",
            risk_level="code",
            supports_streaming=True,
            contextual=True,
            concurrency_class="exclusive",
        )
    )
