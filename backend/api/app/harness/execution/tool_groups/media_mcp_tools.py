"""工具分组注册。

由 ``build_default_registry`` 统一装配；``ToolDef`` 延迟导入避免循环依赖。
"""

from __future__ import annotations

from typing import Any

from ..policy import ToolPermissionPolicy, ToolRecoveryPolicy
from ..registry_handlers import (
    _media_mcp_unavailable_handler,
)


def register_media_mcp_tools(registry: Any) -> None:
    """登记 Compose 私网媒体 MCP；上游凭据只保存在 media-mcp 服务。"""
    from ..registry import ToolDef

    common_output = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "status": {"type": "string"},
            "model": {"type": ["string", "null"]},
            "image_urls": {"type": "array", "items": {"type": "string"}},
            # 平台归档产物：api 侧下载进会话工作区的相对路径（原生 MCP 返回中无此字段）。
            "workspace_images": {"type": "array", "items": {"type": "string"}},
            "workspace_videos": {"type": "array", "items": {"type": "string"}},
            "upstream_task_id": {"type": ["string", "null"]},
            "video_url": {"type": ["string", "null"]},
            "code": {"type": ["string", "null"]},
            "message": {"type": ["string", "null"]},
            "error_code": {"type": ["string", "null"]},
        },
        "required": ["status"],
    }
    registry.register(
        ToolDef(
            name="image.generate",
            description=(
                "使用已配置的 Qwen 图片模型生成图片；可选传入至多三张 HTTPS 或 Data URI 参考图。"
                "生成结果自动归档到会话工作区，workspace_images 返回工作区相对路径，"
                "可直接用 read/read_image 等工具读取。"
            ),
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "prompt": {"type": "string", "minLength": 1, "maxLength": 5000},
                    "reference_images": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1, "maxLength": 29_360_128},
                        "maxItems": 3,
                    },
                    "size": {"type": "string", "minLength": 3, "maxLength": 32},
                    "count": {"type": "integer", "minimum": 1, "maximum": 6},
                    "prompt_extend": {"type": "boolean"},
                },
                "required": ["prompt"],
            },
            permission="media.generate",
            timeout_s=180.0,
            handler=_media_mcp_unavailable_handler,
            output_schema=common_output,
            permission_policy=ToolPermissionPolicy(network="public_only"),
            recovery_policy=ToolRecoveryPolicy(
                retryable_codes=frozenset({"UPSTREAM", "TIMEOUT"}),
                suggested_action="retry_after_check",
                default_hint="请确认媒体服务可用和提示词参数后重试。",
                max_auto_repairs=0,
            ),
            transport="mcp",
            server_id="media.generation",
            display_name="生成图片",
            risk_level="network",
            concurrency_class="exclusive",
        )
    )
    registry.register(
        ToolDef(
            name="video.create",
            description="使用已配置的 HappyHorse 首帧图生视频模型创建异步任务；必须提供一张首帧图片。",
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "prompt": {"type": "string", "minLength": 1, "maxLength": 5000},
                    "first_frame": {"type": "string", "minLength": 1, "maxLength": 29_360_128},
                    "resolution": {"type": "string", "enum": ["480P", "720P", "1080P"]},
                    "duration": {"type": "integer", "minimum": 3, "maximum": 15},
                    "watermark": {"type": "boolean"},
                },
                "required": ["prompt", "first_frame"],
            },
            permission="media.generate",
            timeout_s=45.0,
            handler=_media_mcp_unavailable_handler,
            output_schema=common_output,
            permission_policy=ToolPermissionPolicy(network="public_only"),
            recovery_policy=ToolRecoveryPolicy(
                retryable_codes=frozenset({"UPSTREAM", "TIMEOUT"}),
                suggested_action="retry_after_check",
                default_hint="请确认媒体服务可用和首帧图片格式后重试。",
                max_auto_repairs=0,
            ),
            transport="mcp",
            server_id="media.generation",
            display_name="创建图生视频",
            risk_level="network",
            concurrency_class="exclusive",
        )
    )
    registry.register(
        ToolDef(
            name="video.status",
            description=(
                "查询 HappyHorse 图生视频异步任务状态；成功时返回临时视频地址。"
                "成功的视频自动归档到会话工作区，workspace_videos 返回工作区相对路径。"
            ),
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "upstream_task_id": {"type": "string", "minLength": 1, "maxLength": 200},
                },
                "required": ["upstream_task_id"],
            },
            permission="media.read",
            timeout_s=30.0,
            handler=_media_mcp_unavailable_handler,
            output_schema=common_output,
            permission_policy=ToolPermissionPolicy(network="public_only"),
            recovery_policy=ToolRecoveryPolicy(
                retryable_codes=frozenset({"UPSTREAM", "TIMEOUT"}),
                suggested_action="retry_after_check",
                default_hint="请确认视频任务标识和媒体服务状态后重试。",
                max_auto_repairs=0,
            ),
            transport="mcp",
            server_id="media.generation",
            display_name="查询视频状态",
            risk_level="read",
            concurrency_class="read_only",
        )
    )
