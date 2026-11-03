"""LightRAG 适配服务的运行配置（纯环境变量读取，不含任何引擎依赖）。

平台侧只通过 ``LIGHTRAG_*`` 变量描述「用哪个模型做抽取 / 用哪个模型做向量化」，
本模块负责把这些外部配置归一成一个不可变配置对象；密钥只在容器内使用，
不进入日志、健康检查响应或异常消息。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_str(name: str, default: str = "") -> str:
    """读取字符串环境变量并去除首尾空白。"""
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    """读取整型环境变量；非法值回退默认值，避免容器启动即崩溃。"""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    """读取浮点环境变量；非法值回退默认值。"""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class EngineConfig:
    """LightRAG 引擎配置快照。

    ``ready`` 为 False 表示缺少必要的上游配置（对话/向量网关地址），此时适配
    服务仍可提供 ``/health``，但索引与检索一律返回服务不可用，由平台侧标注降级，
    禁止伪装成成功（AGENTS.md：能力未启用不得 mock 成功）。
    """

    data_dir: str
    api_key: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_timeout_s: float
    embedding_base_url: str
    embedding_api_key: str
    embedding_model: str
    embedding_dim: int
    embedding_max_tokens: int
    chunk_token_size: int
    chunk_overlap_token_size: int
    entity_top_k: int
    max_parallel_insert: int
    # 单篇文档在 Top-K 中的最大占位数（0 表示不限制）：平台指标按文档计算，
    # 一篇长文档的多个相近切块占满结果会让其它文档永远进不了 Top-K。
    max_chunks_per_doc: int
    # 待索引队列上限：每篇排队文档的正文都驻留内存，无上限会在连续上传时 OOM。
    max_queue_documents: int
    # 停机时等待在建索引任务收尾的宽限期：直接取消会把 doc_status 留在 processing。
    shutdown_grace_s: float
    workspace: str

    @property
    def ready(self) -> bool:
        """引擎是否具备启动条件（对话与向量网关地址齐备）。

        密钥不参与就绪判定：本地 vLLM/Ollama 一类网关无需密钥，OpenAI SDK 只要求
        非空字符串，缺失时由引擎侧填 ``EMPTY`` 占位；真实网关缺密钥会在调用时
        返回 401，由索引失败状态如实暴露，不会静默成功。
        """
        return bool(self.llm_base_url and self.embedding_base_url)

    @property
    def missing(self) -> list[str]:
        """列出缺失的配置项名称，供健康检查如实说明不可用原因（不含密钥值）。"""
        missing: list[str] = []
        if not self.llm_base_url:
            missing.append("LIGHTRAG_LLM_BASE_URL")
        if not self.embedding_base_url:
            missing.append("LIGHTRAG_EMBEDDING_BASE_URL")
        return missing


def load_config() -> EngineConfig:
    """从环境变量构造配置快照。

    Embedding 默认复用 LLM 的地址与密钥（大多数 OpenAI 兼容网关同一入口同时
    提供对话与向量接口），需要分开配置时显式设置 ``LIGHTRAG_EMBEDDING_*``。
    """
    llm_base_url = _env_str("LIGHTRAG_LLM_BASE_URL")
    llm_api_key = _env_str("LIGHTRAG_LLM_API_KEY")
    embedding_base_url = _env_str("LIGHTRAG_EMBEDDING_BASE_URL") or llm_base_url
    embedding_api_key = _env_str("LIGHTRAG_EMBEDDING_API_KEY") or llm_api_key

    return EngineConfig(
        # 引擎存储目录：Compose 挂载 ./data/lightrag，容器重建不丢图与向量。
        data_dir=_env_str("LIGHTRAG_DATA_DIR", "/data/lightrag"),
        # 平台 → 适配服务的内部鉴权口令（仅内网使用，不对外发布）。
        api_key=_env_str("LIGHTRAG_API_KEY"),
        llm_base_url=llm_base_url.rstrip("/"),
        llm_api_key=llm_api_key,
        llm_model=_env_str("LIGHTRAG_LLM_MODEL", "gpt-4o-mini"),
        llm_timeout_s=_env_float("LIGHTRAG_LLM_TIMEOUT_SECONDS", 180.0),
        embedding_base_url=embedding_base_url.rstrip("/"),
        embedding_api_key=embedding_api_key,
        embedding_model=_env_str("LIGHTRAG_EMBEDDING_MODEL", "BAAI/bge-m3"),
        embedding_dim=_env_int("LIGHTRAG_EMBEDDING_DIM", 1024),
        embedding_max_tokens=_env_int("LIGHTRAG_EMBEDDING_MAX_TOKENS", 8192),
        chunk_token_size=_env_int("LIGHTRAG_CHUNK_TOKEN_SIZE", 1200),
        chunk_overlap_token_size=_env_int("LIGHTRAG_CHUNK_OVERLAP_TOKENS", 100),
        entity_top_k=_env_int("LIGHTRAG_ENTITY_TOP_K", 40),
        # LightRAG 实体抽取是重 IO 操作，默认串行以免打爆小规格上游配额。
        max_parallel_insert=_env_int("LIGHTRAG_MAX_PARALLEL_INSERT", 1),
        max_chunks_per_doc=_env_int("LIGHTRAG_MAX_CHUNKS_PER_DOC", 3),
        max_queue_documents=_env_int("LIGHTRAG_MAX_QUEUE_DOCUMENTS", 64),
        shutdown_grace_s=_env_float("LIGHTRAG_SHUTDOWN_GRACE_SECONDS", 30.0),
        workspace=_env_str("LIGHTRAG_WORKSPACE", "aieval"),
    )


def ensure_data_dir(config: EngineConfig) -> Path:
    """确保引擎存储目录存在并返回路径。"""
    path = Path(config.data_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path
