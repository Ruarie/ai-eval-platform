"""Harness 执行层：工具注册表（M5 阶段 2，EX-1/EX-5）。

工具元数据、白名单与执行分派的**唯一来源**：新增工具必须登记并走统一执行
入口；未注册工具调用一律拒绝（VALIDATION），禁止假成功。``ToolDef.handler``
为运行时执行函数（不入 GraphState，仅注册表持有）。基础文件、网络、沙箱与
任务拆解工具固定为 ``transport=native``；只有评测/RAG 等后续扩展工具才允许
显式标记为 ``transport=mcp`` 并投影到内部 MCP 目录。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Literal

from app.config import settings
from app.errors import AppError, ErrorCode
from app.harness.contracts import ToolDescriptor

from .policy import DEFAULT_RECOVERY_POLICY, ToolPermissionPolicy, ToolRecoveryPolicy
from .registry_handlers import (  # noqa: F401
    _ask_user_question_handler,
    _bash_handler,
    _board_from_context,
    _edit_handler,
    _glob_handler,
    _grep_handler,
    _media_mcp_unavailable_handler,
    _platform_kb_list_handler,
    _platform_task_list_handler,
    _read_handler,
    _read_image_handler,
    _session_task_create_handler,
    _session_task_get_handler,
    _session_task_list_handler,
    _session_task_update_handler,
    _task_cancel_handler,
    _task_create_handler,
    _task_handler,
    _task_status_handler,
    _web_fetch_handler,
    _web_search_handler,
    _write_handler,
)
from .registry_schema import (  # noqa: F401  （对外兼容导出；schema 校验实现见 registry_schema）
    required_parameter_names,
    validate_tool_arguments,
    validate_tool_output,
    validate_tool_schema,
)
from .tool_groups.bash_tool import register_bash_tool as _register_bash_tool
from .tool_groups.file_tools import register_file_tools as _register_file_tools
from .tool_groups.media_mcp_tools import register_media_mcp_tools as _register_media_mcp_tools
from .tool_groups.platform_task_tools import (
    register_platform_task_tools as _register_platform_task_tools,
)
from .tool_groups.task_tools import register_task_tools as _register_task_tools
from .tool_groups.web_tools import register_web_tools as _register_web_tools


@dataclass(frozen=True, slots=True)
class ToolDef:
    """工具元数据（注册表唯一源）。

    ``transport`` 决定执行边界：原生工具由 ``NativeToolExecutor`` 直连 handler；
    MCP 工具才由 ``MCPClientManager`` 通过受控目录调用。``server_id`` 与
    ``tool_id`` 仅对 MCP 工具有路由含义，模型参数中不得携带。
    """

    name: str  # 如 "read"/"web_search"
    description: str
    parameters_schema: Mapping[str, object]  # JSON schema
    permission: str  # 权限标识
    timeout_s: float  # 执行超时
    handler: Callable[..., object]  # 执行函数（不入 GraphState，仅运行时）
    # 输出、权限与恢复策略与输入 Schema 同属工具契约，禁止在前端或 handler
    # 分别维护第二份规则。``output_schema`` 为 ``None`` 表示未声明（注册期拒绝）；
    # 显式传 ``{}`` 表示「无结构化展示投影」（合法，运行期跳过比对）。
    output_schema: Mapping[str, object] | None = None  # 浏览器安全投影 Schema
    permission_policy: ToolPermissionPolicy = ToolPermissionPolicy()
    recovery_policy: ToolRecoveryPolicy = DEFAULT_RECOVERY_POLICY
    # 为既有内部扩展保持 MCP 默认值；基础工具在 build_default_registry 中显式
    # 标为 native，避免因默认值变化误入 MCP。
    transport: Literal["native", "mcp"] = "mcp"  # 执行通道
    server_id: str = ""  # 如 "platform.files"（空则目录按名称推断归属）
    display_name: str = ""  # 如 "读取文件"
    risk_level: Literal["read", "modify", "network", "code", "long"] = "read"
    execution_mode: Literal["short", "long"] = "short"
    requires_confirmation: bool = False
    supports_streaming: bool = False
    contextual: bool = False  # True 时 handler 接收 (arguments, sandbox_dir, ToolExecutionContext)
    # 仅执行层调度使用，不投影到模型 tools、MCP 目录或浏览器。
    concurrency_class: Literal["read_only", "path_scoped", "exclusive", "session_exclusive"] = (
        "exclusive"
    )
    requires_prior_result: bool = False

    @property
    def tool_id(self) -> str:
        """内部目录唯一 ID：``{server_id}.{name}``；空 server 回退短名。"""
        return f"{self.server_id}.{self.name}" if self.server_id else self.name

    def to_descriptor(self) -> ToolDescriptor:
        """投影为可序列化描述符（MCP 目录 / 风险 / 策略唯一源，不含 handler）。"""
        return ToolDescriptor(
            tool_id=self.tool_id,
            server_id=self.server_id,
            name=self.name,
            display_name=self.display_name or self.name,
            description=self.description,
            input_schema=dict(self.parameters_schema),
            output_schema=dict(self.output_schema or {}),  # None 与 {} 均投影为 {}
            permission=self.permission,
            permission_policy=self.permission_policy.to_payload(),
            recovery_policy={
                "retryable_codes": sorted(self.recovery_policy.retryable_codes),
                "suggested_action": self.recovery_policy.suggested_action,
                "default_hint": self.recovery_policy.default_hint,
                "max_auto_repairs": self.recovery_policy.max_auto_repairs,
            },
            risk_level=self.risk_level,
            execution_mode=self.execution_mode,
            timeout_s=float(self.timeout_s),
            requires_confirmation=self.requires_confirmation,
            supports_streaming=self.supports_streaming,
        )


class ToolRegistry:
    """工具注册表；白名单与分派唯一源。"""

    def __init__(self) -> None:
        self._defs: dict[str, ToolDef] = {}

    def register(self, def_: ToolDef) -> None:
        """登记工具；重名登记抛 VALIDATION（防止覆盖导致分派漂移）。"""
        if def_.name in self._defs:
            raise AppError(ErrorCode.VALIDATION, f"工具已登记：{def_.name}")
        schema_error = validate_tool_schema(def_.parameters_schema)
        if schema_error:
            raise AppError(ErrorCode.VALIDATION, f"工具参数 Schema 无效：{schema_error}")
        # output_schema 是浏览器展示投影的契约，必须显式声明且自身合法。
        # None（未声明）拒绝；显式 {} 表示无结构化投影，合法但运行期不做比对。
        if def_.output_schema is None:
            raise AppError(ErrorCode.VALIDATION, f"工具必须声明 output_schema：{def_.name}")
        output_schema_error = validate_tool_schema(def_.output_schema)
        if output_schema_error:
            raise AppError(ErrorCode.VALIDATION, f"工具输出 Schema 无效：{output_schema_error}")
        self._defs[def_.name] = def_

    def get(self, name: str) -> ToolDef:
        """取定义；未注册抛 AppError(VALIDATION)。"""
        definition = self.find(name)
        if definition is None:
            raise AppError(ErrorCode.VALIDATION, f"工具未注册：{name}")
        return definition

    def find(self, name: str) -> ToolDef | None:
        """按名称查询运行时定义；未注册返回 ``None``。"""
        return self._defs.get(name)

    def names(self) -> tuple[str, ...]:
        """返回已登记工具名，供 Gate 构造白名单。"""
        return tuple(self._defs)

    def iter_defs(self, *, transport: Literal["native", "mcp"] | None = None) -> Iterator[ToolDef]:
        """返回底层 ``ToolDef`` 对象（含 handler，限执行层内部消费）。

        ``transport`` 非空时只返回指定执行通道，供 MCP 目录和 provider 排除
        原生基础工具；对外可序列化投影仍走 ``all_defs``/``get_def``，避免
        handler 泄漏到模型或前端。
        """
        definitions = self._defs.values()
        if transport is None:
            return iter(definitions)
        return (definition for definition in definitions if definition.transport == transport)

    def has_transport(self, transport: Literal["native", "mcp"]) -> bool:
        """判断是否存在指定执行通道的工具，避免空 MCP Host 的构建开销。"""
        return any(definition.transport == transport for definition in self._defs.values())

    def all_defs(self) -> list[Mapping[str, object]]:
        """返回全部工具定义（可序列化投影，供 M2 select_tool_defs 最小注入）。

        只含元数据，不含 handler（handler 为运行时 Callable，不可序列化）。
        """
        return [
            {
                "name": definition.name,
                "description": definition.description,
                "parameters_schema": dict(definition.parameters_schema),
                "output_schema": dict(definition.output_schema or {}),
                "permission": definition.permission,
                "permission_policy": definition.permission_policy.to_payload(),
                "recovery_policy": {
                    "retryable_codes": sorted(definition.recovery_policy.retryable_codes),
                    "suggested_action": definition.recovery_policy.suggested_action,
                    "default_hint": definition.recovery_policy.default_hint,
                    "max_auto_repairs": definition.recovery_policy.max_auto_repairs,
                },
                "timeout_s": definition.timeout_s,
            }
            for definition in self._defs.values()
        ]

    def get_def(self, name: str) -> Mapping[str, object] | None:
        """按名取可序列化定义（M2 select_tool_defs 消费）；未注册返回 None。"""
        definition = self.find(name)
        if definition is None:
            return None
        return {
            "name": definition.name,
            "description": definition.description,
            "parameters_schema": dict(definition.parameters_schema),
            "output_schema": dict(definition.output_schema or {}),
            "permission": definition.permission,
            "permission_policy": definition.permission_policy.to_payload(),
            "recovery_policy": {
                "retryable_codes": sorted(definition.recovery_policy.retryable_codes),
                "suggested_action": definition.recovery_policy.suggested_action,
                "default_hint": definition.recovery_policy.default_hint,
                "max_auto_repairs": definition.recovery_policy.max_auto_repairs,
            },
            "timeout_s": definition.timeout_s,
        }

    def is_registered(self, name: str) -> bool:
        """是否已登记。"""
        return name in self._defs


def build_default_registry() -> ToolRegistry:
    """注册原生基础工具与 ``platform.tasks`` MCP 评测任务桥。

    ``read/read_image/glob/grep/write/edit/web_search/web_fetch/bash/task`` 均经原生 ToolCall 直连；
    bash 由独立 Runner 的 bwrap 沙箱执行并 fail-closed。``task`` 只维护本回合
    的拆解清单。``task.create/status/cancel`` 则是显式 ``transport=mcp`` 的
    评测任务扩展：只入 PG 队列、查询或取消，不等待 Worker 终态。
    """
    registry = ToolRegistry()
    _register_file_tools(registry)
    _register_web_tools(registry)
    _register_bash_tool(registry)
    _register_task_tools(registry)
    _register_platform_task_tools(registry)
    if settings.media_mcp_enabled:
        _register_media_mcp_tools(registry)
    return registry


