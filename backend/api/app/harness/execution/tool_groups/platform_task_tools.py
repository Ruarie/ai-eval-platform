"""工具分组注册。

由 ``build_default_registry`` 统一装配；``ToolDef`` 延迟导入避免循环依赖。
"""

from __future__ import annotations

from typing import Any

from ..policy import ToolPermissionPolicy
from ..registry_handlers import (
    _platform_kb_list_handler,
    _platform_task_list_handler,
    _task_cancel_handler,
    _task_create_handler,
    _task_status_handler,
)


def register_platform_task_tools(registry: Any) -> None:
    """platform.tasks 长任务 MCP：只入队/查询/取消，不等待终态。"""
    from ..registry import ToolDef

    # ── platform.tasks 长任务 MCP：只入队/查询/取消，不等待终态 ──
    registry.register(
        ToolDef(
            name="task.create",
            description="创建测试用例生成任务并入队；Worker 将结果保存为 /cases 待确认草稿，返回 queued + task_id，不等待终态。",
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["testcase"],
                        "description": "任务类型",
                    },
                    "case_source": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "file_id": {"type": "string"},
                            "text": {"type": "string", "maxLength": 1000000},
                        },
                        "description": "用例生成来源；file_id/text 二选一",
                    },
                    "max_count": {
                        "type": "integer", "minimum": 1, "maximum": 80,
                        "description": "目标用例数；省略时默认 45 条",
                    },
                    "strategy_weights": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            key: {"type": "integer", "minimum": 0, "maximum": 100}
                            for key in ("positive", "negative", "boundary", "equivalence", "state", "scenario")
                        },
                        "description": "六策略整数百分比，合计 100；省略时使用默认配比",
                    },
                },
                "required": ["kind", "case_source"],
            },
            permission="task.create",
            timeout_s=10.0,
            handler=_task_create_handler,
            output_schema={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["queued"]},
                    "task_id": {"type": "string"},
                    "kind": {"type": "string"},
                },
                "required": ["status", "task_id", "kind"],
            },
            transport="mcp",
            server_id="platform.tasks",
            display_name="生成测试用例",
            risk_level="modify",
            contextual=True,
            concurrency_class="session_exclusive",
        )
    )
    registry.register(
        ToolDef(
            name="task.status",
            description="查询用例生成任务当前状态；草稿生成后返回 case_set_id，不等待完成",
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
            permission="task.status",
            timeout_s=10.0,
            handler=_task_status_handler,
            output_schema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "kind": {"type": "string"},
                    "status": {"type": "string"},
                    "progress": {"type": "object"},
                    "report_id": {"type": ["string", "null"]},
                    "case_set_id": {"type": ["string", "null"]},
                },
                "required": ["task_id", "kind", "status"],
            },
            transport="mcp",
            server_id="platform.tasks",
            display_name="查询任务状态",
            risk_level="read",
            contextual=True,
            concurrency_class="read_only",
        )
    )
    registry.register(
        ToolDef(
            name="kb.list",
            description=(
                "列出知识库及每个库的文档数（与 /kb 页面同源）。"
                "适用：用户问「我有几个知识库」「某库有多少篇文档」。"
                "不适用：查看文档正文或切块（请在 /kb 页面查看）；不返回正文与凭据。"
            ),
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "description": "最多返回多少个知识库，默认 20",
                    }
                },
            },
            permission="platform.kb.read",
            permission_policy=ToolPermissionPolicy(workspace="read"),
            output_schema={
                "type": "object",
                "properties": {
                    "items": {"type": "array", "items": {"type": "object"}},
                    "total": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "note": {"type": "string"},
                },
                "required": ["items", "total", "limit"],
            },

            timeout_s=10.0,
            handler=_platform_kb_list_handler,
            transport="native",
            display_name="列出知识库",
            risk_level="read",
            concurrency_class="read_only",
        )
    )
    registry.register(
        ToolDef(
            name="task.list",
            description=(
                "列出最近的平台任务与状态（可按 kind 过滤）。"
                "适用：用户问「我有哪些任务」「最近的用例生成任务」。"
                "不适用：任务细节或报告正文（用 task.status，或在 /tasks、/reports 查看）。"
            ),
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "description": "最多返回多少条，默认 10",
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["testcase", "benchmark", "rag", "stress"],
                        "description": "可选：按任务类型过滤",
                    },
                },
            },
            permission="platform.task.read",
            permission_policy=ToolPermissionPolicy(workspace="read"),
            output_schema={
                "type": "object",
                "properties": {
                    "items": {"type": "array", "items": {"type": "object"}},
                    "total": {"type": "integer"},
                    "limit": {"type": "integer"},
                    "note": {"type": "string"},
                },
                "required": ["items", "total", "limit"],
            },

            timeout_s=10.0,
            handler=_platform_task_list_handler,
            transport="native",
            display_name="列出任务",
            risk_level="read",
            concurrency_class="read_only",
        )
    )
    registry.register(
        ToolDef(
            name="task.cancel",
            description="取消非终态评测任务（终态任务幂等返回现状）",
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
            permission="task.cancel",
            timeout_s=10.0,
            handler=_task_cancel_handler,
            output_schema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "status": {"type": "string"},
                    "kind": {"type": "string"},
                },
                "required": ["task_id", "status", "kind"],
            },
            transport="mcp",
            server_id="platform.tasks",
            display_name="取消评测任务",
            risk_level="modify",
            contextual=True,
            concurrency_class="session_exclusive",
        )
    )
