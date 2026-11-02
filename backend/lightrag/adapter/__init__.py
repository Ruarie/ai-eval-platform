"""平台侧 LightRAG 适配层：配置快照、内部契约映射与引擎封装。

只有本包依赖 ``lightrag-hku``；``app.py`` 仅负责 HTTP 契约，便于在缺少引擎
依赖时仍能启动并如实报告未就绪。
"""

from __future__ import annotations

from .config import EngineConfig, ensure_data_dir, load_config
from .contract import (
    STATUS_FAILED,
    STATUS_INDEXED,
    STATUS_INDEXING,
    build_file_source,
    map_chunks,
    parse_file_source,
)
from .engine import EngineBusy, EngineUnavailable, LightRAGEngine

__all__ = [
    "EngineBusy",
    "EngineConfig",
    "EngineUnavailable",
    "LightRAGEngine",
    "STATUS_FAILED",
    "STATUS_INDEXED",
    "STATUS_INDEXING",
    "build_file_source",
    "ensure_data_dir",
    "load_config",
    "map_chunks",
    "parse_file_source",
]
