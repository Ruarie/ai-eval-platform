"""工作区文件工具注册（read / read_image / glob / grep / write / edit）。

从 registry.py 拆出后仍由 ``build_default_registry`` 统一装配；``ToolDef`` 延迟
导入避免与 registry 形成模块级循环。
"""

from __future__ import annotations

from typing import Any

from ..policy import ToolPermissionPolicy, ToolRecoveryPolicy
from ..registry_handlers import (
    _edit_handler,
    _glob_handler,
    _grep_handler,
    _read_handler,
    _read_image_handler,
    _write_handler,
)


def register_file_tools(registry: Any) -> None:
    """工作区文件工具：read / read_image / glob / grep / write / edit。"""
    from ..registry import ToolDef

    registry.register(
        ToolDef(
            name="read",
            description=(
                "按行读取沙箱目录内的文本文件（相对路径）。"
                "适用：查看附件、工作区文件、确认 edit 前的原文。"
                "不适用：创建文件（用 write）、改文件（用 edit）、执行命令（用 bash）。"
                "前置：path 必须是沙箱相对路径。offset/limit 均为 0-based 行。"
                "推荐用法：除非只需要局部行段，否则省略 limit 一次读完——单次最多 "
                "2000 行和 600000 字符，1000 行量级的文件一次即可读完，禁止人为拆成"
                "多个小窗口连续多次读取。未读完时把返回的 "
                "next_offset 填到下一次 offset，不要用相同 offset 重复读取。大文件只解码当前窗口。"
            ),
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "file_path": {"type": "string", "description": "会话工作区相对路径"},
                    "offset": {"type": "integer", "description": "起始行号，0-based，默认 0", "minimum": 0},
                    "limit": {
                        "type": "integer",
                        "description": "最多读取行数；建议省略以一次读完，默认/上限 2000",
                        "minimum": 1,
                        "maximum": 2000,
                    },
                },
                "required": ["file_path"],
            },
            permission="sandbox.read",
            timeout_s=20.0,
            handler=_read_handler,
            output_schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "status": {"type": "string"},
                    "content": {"type": "string"},
                    "metadata": {"type": "object"},
                    "read": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "total_lines": {"type": "integer"},
                            "start_line": {"type": "integer"},
                            "end_line": {"type": "integer"},
                            "next_offset": {"type": ["integer", "null"]},
                            "preview": {"type": "string"},
                        },
                    },
                },
            },
            permission_policy=ToolPermissionPolicy(workspace="read"),
            recovery_policy=ToolRecoveryPolicy(
                retryable_codes=frozenset({"TIMEOUT"}),
                suggested_action="read_next_page",
                default_hint="请检查相对路径，或使用 next_offset 读取下一页。",
            ),
            transport="native",
            display_name="读取文件",
            risk_level="read",
            supports_streaming=True,
            contextual=True,
            concurrency_class="path_scoped",
        )
    )
    registry.register(
        ToolDef(
            name="read_image",
            description=(
                "读取会话工作区内的 PNG、JPEG、GIF 或 WebP 图片。"
                "适用：用户要求分析工作区图片，或先用 glob 定位图片后查看。"
                "前置：file_path 必须是沙箱相对路径；单张图片不得超过 4MB。"
                "图片只在当前模型回合以图文块传递，持久日志和 ToolCard 仅保存元数据摘要。"
            ),
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {"file_path": {"type": "string", "description": "会话工作区相对图片路径"}},
                "required": ["file_path"],
            },
            permission="sandbox.read",
            timeout_s=20.0,
            handler=_read_image_handler,
            output_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "summary": {"type": "string"},
                    "status": {"type": "string"},
                    "read_image": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "path": {"type": "string"}, "media_type": {"type": "string"},
                            "size_bytes": {"type": "integer"}, "width": {"type": ["integer", "null"]},
                            "height": {"type": ["integer", "null"]},
                        },
                        "required": ["path", "media_type", "size_bytes", "width", "height"],
                    },
                },
                "required": ["summary", "status", "read_image"],
            },
            permission_policy=ToolPermissionPolicy(workspace="read"),
            recovery_policy=ToolRecoveryPolicy(
                suggested_action="choose_supported_image",
                default_hint="请确认路径指向不超过 4MB 的 PNG、JPEG、GIF 或 WebP 图片。",
            ),
            transport="native",
            display_name="读取图片",
            risk_level="read",
            contextual=True,
            concurrency_class="path_scoped",
        )
    )
    registry.register(
        ToolDef(
            name="glob",
            description=(
                "按 glob 模式查找会话工作区内的普通文件。"
                "pattern 不含斜杠时匹配任意目录层级的文件名；可选 path 限定起始目录。"
                "结果只返回相对路径，自动排除版本库、依赖缓存和符号链接。"
            ),
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "pattern": {"type": "string", "minLength": 1, "maxLength": 500, "description": "文件 glob 模式"},
                    "path": {"type": "string", "description": "可选的工作区相对起始目录"},
                },
                "required": ["pattern"],
            },
            permission="sandbox.read",
            timeout_s=20.0,
            handler=_glob_handler,
            output_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "summary": {"type": "string"}, "status": {"type": "string"}, "content": {"type": "string"},
                    "glob": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "query": {"type": "string"}, "count": {"type": "integer"},
                            "truncated": {"type": "boolean"}, "preview": {"type": "string"},
                        },
                        "required": ["query", "count", "truncated", "preview"],
                    },
                },
                "required": ["summary", "status", "content", "glob"],
            },
            permission_policy=ToolPermissionPolicy(workspace="read"),
            recovery_policy=ToolRecoveryPolicy(
                suggested_action="narrow_glob",
                default_hint="请缩小 path 或使用更具体的 pattern。",
            ),
            transport="native",
            display_name="查找文件",
            risk_level="read",
            contextual=True,
            concurrency_class="path_scoped",
        )
    )
    registry.register(
        ToolDef(
            name="grep",
            description=(
                "在会话工作区文本文件中按 Python 正则搜索内容，返回 path:line:text。"
                "可选 path 限定搜索目录，include 用 glob 过滤文件；自动跳过二进制文件、"
                "版本库、依赖缓存和符号链接。"
            ),
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "pattern": {"type": "string", "minLength": 1, "maxLength": 500, "description": "Python 正则表达式"},
                    "path": {"type": "string", "description": "可选的工作区相对起始目录"},
                    "include": {"type": "string", "maxLength": 500, "description": "可选的文件 glob 过滤模式"},
                },
                "required": ["pattern"],
            },
            permission="sandbox.read",
            timeout_s=20.0,
            handler=_grep_handler,
            output_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "summary": {"type": "string"}, "status": {"type": "string"}, "content": {"type": "string"},
                    "grep": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "query": {"type": "string"}, "count": {"type": "integer"},
                            "truncated": {"type": "boolean"}, "preview": {"type": "string"},
                        },
                        "required": ["query", "count", "truncated", "preview"],
                    },
                },
                "required": ["summary", "status", "content", "grep"],
            },
            permission_policy=ToolPermissionPolicy(workspace="read"),
            recovery_policy=ToolRecoveryPolicy(
                suggested_action="narrow_grep",
                default_hint="请缩小 path、include 或正则表达式的匹配范围。",
            ),
            transport="native",
            display_name="搜索文件内容",
            risk_level="read",
            contextual=True,
            concurrency_class="path_scoped",
        )
    )
    registry.register(
        ToolDef(
            name="write",
            description="在沙箱目录内新建文本文件（相对路径）",
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "file_path": {"type": "string", "description": "目标文件相对路径，不存在则新建"},
                    "content": {"type": "string", "description": "完整文本内容"},
                    "description": {"type": "string", "description": "简短操作描述"},
                    "reviewComment": {"type": "string", "description": "写操作动机，仅供审查展示"},
                },
                "required": ["file_path", "content"],
            },
            permission="sandbox.write",
            timeout_s=10.0,
            handler=_write_handler,
            output_schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "status": {"type": "string"},
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "write": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "bytes_written": {"type": "integer"},
                            "lines_written": {"type": "integer"},
                            "preview": {"type": "string"},
                        },
                    },
                },
            },
            permission_policy=ToolPermissionPolicy(workspace="write"),
            recovery_policy=ToolRecoveryPolicy(
                suggested_action="choose_new_path",
                default_hint="文件不会被覆盖；请改用新路径，或先 read 后使用 edit。",
                max_auto_repairs=0,
            ),
            transport="native",
            display_name="写入文件",
            risk_level="modify",
            supports_streaming=True,
            contextual=True,
            concurrency_class="path_scoped",
        )
    )
    registry.register(
        ToolDef(
            name="edit",
            description=(
                "在沙箱目录内对已有文本文件做精确字符串替换。"
                "适用：修改已存在文件的一小段原文。"
                "不适用：新建文件（用 write）、查看内容（用 read）。"
                "前置：必须先 read 确认 old 与文件中的文本完全一致（含空白）；"
                "old 在文件中必须能唯一匹配，否则会失败并返回邻近行修复建议。"
            ),
            parameters_schema={
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "file_path": {"type": "string", "description": "目标文件相对路径"},
                    "old_string": {"type": "string", "description": "需唯一精确匹配的原文"},
                    "new_string": {"type": "string", "description": "替换后的新文本，空串表示删除"},
                    "replace_all": {
                        "type": "boolean",
                        "description": "为 true 时替换全部匹配，否则多处匹配会失败",
                    },
                },
                "required": ["file_path", "old_string", "new_string"],
            },
            permission="sandbox.write",
            timeout_s=10.0,
            handler=_edit_handler,
            output_schema={
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "status": {"type": "string"},
                    "modified_lines": {"type": "integer"},
                    "diff": {"type": "string"},
                    "edit": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "replacements": {"type": "integer"},
                            "old_length": {"type": "integer"},
                            "new_length": {"type": "integer"},
                        },
                    },
                },
            },
            permission_policy=ToolPermissionPolicy(workspace="write"),
            recovery_policy=ToolRecoveryPolicy(
                suggested_action="read_then_edit",
                default_hint="请先 read 确认 old 与文件原文完全一致后再编辑。",
                max_auto_repairs=1,
            ),
            transport="native",
            display_name="编辑文件",
            risk_level="modify",
            contextual=True,
            concurrency_class="path_scoped",
        )
    )
