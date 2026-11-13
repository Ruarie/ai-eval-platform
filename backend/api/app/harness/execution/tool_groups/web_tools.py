"""工具分组注册。

由 ``build_default_registry`` 统一装配；``ToolDef`` 延迟导入避免循环依赖。
"""

from __future__ import annotations

from typing import Any

from ..policy import ToolPermissionPolicy, ToolRecoveryPolicy
from ..registry_handlers import (
    _web_fetch_handler,
    _web_search_handler,
)


def register_web_tools(registry: Any) -> None:
    """网络工具：web_search / web_fetch。"""
    from ..registry import ToolDef

    registry.register(
        ToolDef(
            name="web_search",
            description="内部搜索引擎检索（平台自实现适配器，不走外部 MCP）",
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 500},
                    "max_results": {
                        "type": "integer",
                        "description": "返回结果数，默认 5，平台上限 10",
                        "minimum": 1,
                        "maximum": 10,
                    },
                    "topic": {"type": "string", "description": "主题，仅展示"},
                    "time_range": {"type": "string", "description": "时间筛选，仅展示"},
                    "include_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 20,
                        "description": "限定来源域名，本轮不改变检索实现",
                    },
                    "exclude_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 20,
                        "description": "排除域名，本轮不改变检索实现",
                    },
                    "engine": {"type": "string", "description": "仅 auto/native"},
                    "search_context_size": {"type": "string", "description": "上下文长度提示，仅展示"},
                },
                "required": ["query"],
            },
            permission="web.search",
            timeout_s=20.0,
            handler=_web_search_handler,
            output_schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "results": {"type": "array"},
                    "search": {"type": "object"},
                },
            },
            permission_policy=ToolPermissionPolicy(network="public_only"),
            recovery_policy=ToolRecoveryPolicy(
                retryable_codes=frozenset({"TIMEOUT", "UPSTREAM"}),
                suggested_action="retry_query",
                default_hint="请稍后重试，或缩短并调整搜索关键词。",
            ),
            transport="native",
            display_name="网页检索",
            risk_level="network",
            concurrency_class="read_only",
        )
    )
    registry.register(
        ToolDef(
            name="web_fetch",
            description="内部网页抓取（平台自实现适配器 + 脱敏，不走外部 MCP）",
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "url": {"type": "string", "minLength": 8, "maxLength": 2048},
                    "format": {"type": "string", "enum": ["markdown", "text"], "description": "优先返回 Markdown，默认 markdown"},
                    "allowed_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 20,
                        "description": "允许访问的域名白名单",
                    },
                    "blocked_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 20,
                        "description": "禁止访问的域名黑名单",
                    },
                    "max_content_tokens": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "映射到现有字符预算，不放宽 60000",
                    },
                    "engine": {"type": "string", "description": "仅 auto/native"},
                },
                "required": ["url"],
            },
            permission="web.fetch",
            timeout_s=20.0,
            handler=_web_fetch_handler,
            output_schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "content": {"type": "string"},
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "web": {"type": "object"},
                },
            },
            permission_policy=ToolPermissionPolicy(network="public_only"),
            recovery_policy=ToolRecoveryPolicy(
                retryable_codes=frozenset({"TIMEOUT", "UPSTREAM"}),
                suggested_action="retry_public_url",
                default_hint="请确认 URL 可公开访问；内网与回环地址不会重试。",
            ),
            transport="native",
            display_name="网页抓取",
            risk_level="network",
            supports_streaming=True,
            contextual=True,
            concurrency_class="read_only",
        )
    )
