"""Embedding 调用（OpenAI 兼容 ``/embeddings``）。

仅供记忆语义检索使用：端点、模型与密钥取自管理端「全局 RAG 模型」
（`AI_EMBEDDING_*`），不新增协议档字段，也不复用对话模型凭据。失败统一抛
``AppError(VALIDATION)``，由调用方决定是否降级为关键词召回——记忆召回不得
因向量不可用而阻塞整个回合。
"""

from __future__ import annotations

import logging

import httpx

from app.errors import AppError, ErrorCode

logger = logging.getLogger("llm.embeddings")

_ENDPOINT_SUFFIX = "/embeddings"


def resolve_config() -> tuple[str, str, str]:
    """读取全局 Embedding 配置；未配置字段返回空串，不读密钥以外的任何环境。"""
    from app.profile_env import read_global_rag_env

    values = read_global_rag_env()
    return (
        (values.embedding_base_url or "").rstrip("/"),
        (values.embedding_model or "").strip(),
        values.embedding_api_key or "",
    )


def embed_texts(texts: list[str], *, timeout_s: float = 3.0) -> list[list[float]]:
    """批量取向量：返回顺序与入参一致，维度不一致视为上游异常而非部分成功。"""
    if not texts:
        return []
    base_url, model, api_key = resolve_config()
    if not base_url or not model:
        raise AppError(ErrorCode.VALIDATION, "Embedding 端点或模型未配置")

    # 部分供应商拒绝空字符串；用单空格占位但不改变调用方传入的条数。
    payload_texts = [str(text) if str(text).strip() else " " for text in texts]
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    url = base_url if base_url.endswith(_ENDPOINT_SUFFIX) else f"{base_url}{_ENDPOINT_SUFFIX}"

    try:
        with httpx.Client(timeout=timeout_s) as client:
            response = client.post(
                url, json={"model": model, "input": payload_texts}, headers=headers
            )
    except httpx.TimeoutException as exc:
        raise AppError(ErrorCode.VALIDATION, "Embedding 请求超时") from exc
    except httpx.HTTPError as exc:
        raise AppError(
            ErrorCode.VALIDATION, f"Embedding 请求失败: {type(exc).__name__}"
        ) from exc

    if response.status_code >= 400:
        # 只回状态码：上游正文可能回显请求头或内部错误页。
        raise AppError(
            ErrorCode.VALIDATION, f"Embedding 上游返回 HTTP {response.status_code}"
        )

    try:
        body = response.json()
        items = body.get("data") if isinstance(body, dict) else None
        if not isinstance(items, list) or len(items) != len(payload_texts):
            raise ValueError("data 长度不匹配")
        vectors: list[list[float]] = []
        for item in items:
            raw = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(raw, list) or not raw:
                raise ValueError("embedding 缺失")
            vectors.append([float(value) for value in raw])
    except (ValueError, TypeError) as exc:
        raise AppError(ErrorCode.VALIDATION, "Embedding 响应格式不受支持") from exc

    dimensions = {len(vector) for vector in vectors}
    if len(dimensions) != 1 or 0 in dimensions:
        raise AppError(ErrorCode.VALIDATION, "Embedding 返回维度不一致")
    return vectors
