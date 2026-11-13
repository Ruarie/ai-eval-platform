"""工具分组注册。

由 ``build_default_registry`` 统一装配；``ToolDef`` 延迟导入避免循环依赖。
"""

from __future__ import annotations

from typing import Any

from ..policy import ToolPermissionPolicy, ToolRecoveryPolicy
from ..registry_handlers import (
    _ask_user_question_handler,
    _session_task_create_handler,
    _session_task_get_handler,
    _session_task_list_handler,
    _session_task_update_handler,
    _task_handler,
)


def register_task_tools(registry: Any) -> None:
    """会话任务清单与澄清工具：task / TaskCreate / TaskGet / TaskUpdate / TaskList / ask_user_question。"""
    from ..registry import ToolDef

    registry.register(
        ToolDef(
            name="task",
            description=(
                "维护当前会话的执行清单：仅在复杂、多步骤、需要跟踪进度的工作开始前调用。"
                "适用：包含多个相互依赖步骤、需要调用多种工具、排查不确定问题，或需要向用户展示推进状态的任务。"
                "不适用：简单单步问答、一次读取或一次修改；这些任务直接执行，不要创建清单。"
                "每次必须提交完整 steps 列表，新列表整体替换上一份；开始执行后及时把对应步骤更新为 in_progress，"
                "完成后立即更新为 completed。"
                "不适用：真正创建评测任务（用确认卡或 platform.tasks.task.create）、"
                "查询/取消已入队任务（用 task.status / task.cancel）、启动子代理。"
                "前置：description 概括本轮目标，steps 是有限的具体步骤；不写 PG 任务表、不绕过确认卡或 Worker。"
            ),
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "description": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 80,
                        "description": "任务简短概括",
                    },
                    "prompt": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 2000,
                        "description": "兼容旧调用的完整目标；新调用以 description 为准",
                    },
                    "steps": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 12,
                        "description": "当前完整步骤清单；每次调用整体替换上一份清单",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "title": {"type": "string", "minLength": 1, "maxLength": 300},
                                "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                            },
                            "required": ["title", "status"],
                        },
                    },
                    "subagent_type": {"type": "string", "description": "仅展示，不启子代理"},
                    "model": {"type": "string", "description": "仅展示，不切换模型"},
                    "resume": {"type": "string", "description": "仅展示，不恢复子会话"},
                    "run_in_background": {"type": "boolean", "description": "必须为 false"},
                    "tools": {"type": "array", "items": {"type": "string"}, "maxItems": 20, "description": "仅展示"},
                    "max_turns": {"type": "integer", "minimum": 1, "description": "仅展示"},
                },
                "required": ["description", "steps"],
            },
            permission="task.plan",
            timeout_s=2.0,
            handler=_task_handler,
            output_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "summary": {"type": "string"},
                    "status": {"type": "string", "enum": ["success"]},
                    "result": {"type": "string"},
                    "task": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "goal": {"type": "string"},
                            "description": {"type": "string"},
                            "prompt": {"type": "string"},
                            "steps": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "title": {"type": "string"},
                                        "status": {"type": "string", "enum": ["pending", "in_progress", "completed"]},
                                    },
                                    "required": ["title", "status"],
                                },
                            },
                        },
                        "required": ["goal", "description", "prompt", "steps"],
                    },
                },
                "required": ["summary", "status", "result", "task"],
            },
            permission_policy=ToolPermissionPolicy(),
            recovery_policy=ToolRecoveryPolicy(
                suggested_action="adjust_plan",
                default_hint="请补充目标或将步骤缩减为可执行的有限清单。",
            ),
            transport="native",
            display_name="拆解任务",
            risk_level="read",
            contextual=True,
            concurrency_class="read_only",
        )
    )
    registry.register(
        ToolDef(
            name="TaskCreate",
            description=(
                "在当前会话看板创建一项拆解任务，返回 task.id。"
                "不创建评测入队任务（那是 task.create），不启子代理。"
            ),
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "subject": {"type": "string", "minLength": 1, "maxLength": 120},
                    "description": {"type": "string", "maxLength": 2000},
                    "activeForm": {"type": "string", "maxLength": 80},
                    "metadata": {"type": "object"},
                },
                "required": ["subject"],
            },
            permission="task.plan",
            timeout_s=2.0,
            handler=_session_task_create_handler,
            output_schema={"type": "object", "properties": {"task": {"type": "object"}, "status": {"type": "string"}}},
            permission_policy=ToolPermissionPolicy(),
            transport="native",
            display_name="TaskCreate",
            risk_level="read",
            contextual=True,
            concurrency_class="exclusive",
        )
    )
    registry.register(
        ToolDef(
            name="TaskGet",
            description="按 taskId 读取会话看板中的一项；找不到返回 null。不是评测任务详情。",
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {"taskId": {"type": "string", "minLength": 1}},
                "required": ["taskId"],
            },
            permission="task.plan",
            timeout_s=2.0,
            handler=_session_task_get_handler,
            output_schema={"type": "object"},
            permission_policy=ToolPermissionPolicy(),
            transport="native",
            display_name="TaskGet",
            risk_level="read",
            contextual=True,
            concurrency_class="read_only",
        )
    )
    registry.register(
        ToolDef(
            name="TaskUpdate",
            description=(
                "更新会话看板任务的状态或字段。status=deleted 表示删除。"
                "in_progress 且未指定 owner 时写入当前用户，避免重复认领。"
            ),
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "taskId": {"type": "string", "minLength": 1},
                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "deleted"]},
                    "subject": {"type": "string", "maxLength": 120},
                    "description": {"type": "string", "maxLength": 2000},
                    "activeForm": {"type": "string", "maxLength": 80},
                    "owner": {"type": "string", "maxLength": 64},
                    "addBlocks": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
                    "addBlockedBy": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
                    "metadata": {"type": "object"},
                },
                "required": ["taskId", "status"],
            },
            permission="task.plan",
            timeout_s=2.0,
            handler=_session_task_update_handler,
            output_schema={"type": "object"},
            permission_policy=ToolPermissionPolicy(),
            transport="native",
            display_name="TaskUpdate",
            risk_level="read",
            contextual=True,
            concurrency_class="exclusive",
        )
    )
    registry.register(
        ToolDef(
            name="TaskList",
            description="返回当前会话看板快照，用于读取整体拆解进度。无入参。",
            parameters_schema={"type": "object", "additionalProperties": False, "properties": {}},
            permission="task.plan",
            timeout_s=2.0,
            handler=_session_task_list_handler,
            output_schema={"type": "object"},
            permission_policy=ToolPermissionPolicy(),
            transport="native",
            display_name="TaskList",
            risk_level="read",
            contextual=True,
            concurrency_class="read_only",
        )
    )
    registry.register(
        ToolDef(
            name="ask_user_question",
            description=(
                "向用户提出一个或多个澄清问题，暂停图直到用户回复。"
                "复用 clarify / clarify_reply，不入队评测任务。"
            ),
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "questions": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 5,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "id": {"type": "string", "minLength": 1},
                                "question": {"type": "string", "minLength": 1},
                                "header": {"type": "string"},
                                "options": {
                                    "type": "array",
                                    "maxItems": 10,
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "properties": {
                                            "label": {"type": "string"},
                                            "description": {"type": "string"},
                                        },
                                        "required": ["label"],
                                    },
                                },
                                "multi_select": {"type": "boolean"},
                                "required": {"type": "boolean"},
                                "type": {"type": "string", "enum": ["radio", "checkbox", "text"]},
                            },
                            "required": ["id", "question"],
                        },
                    }
                },
                "required": ["questions"],
            },
            permission="task.plan",
            timeout_s=2.0,
            handler=_ask_user_question_handler,
            output_schema={"type": "object", "properties": {"answers": {"type": "array"}}},
            permission_policy=ToolPermissionPolicy(),
            transport="native",
            display_name="ask_user_question",
            risk_level="read",
            contextual=True,
            concurrency_class="exclusive",
        )
    )
