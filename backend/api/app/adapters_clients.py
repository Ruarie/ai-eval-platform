"""上游 SDK 客户端与 SSE 适配（从 adapters 拆出）。

只负责「怎么把请求发给上游、怎么判断响应类型」，协议字段拼装仍在 adapters。
"""

from __future__ import annotations

from collections.abc import Mapping

from anthropic import Anthropic
from openai import OpenAI

from .errors import AppError, ErrorCode


def _close_quietly(response: object) -> None:
    """取消或超时时关掉上游连接，忽略二次 close 异常。"""
    closer = getattr(response, "close", None)
    if callable(closer):
        try:
            closer()
        except Exception:
            return


def _openai_client(*, base_url: str, api_key: str, timeout_s: float, full_url: bool = False) -> OpenAI:
    """创建单次 OpenAI SDK 客户端，显式关闭 SDK 默认重试以保持调用语义。"""
    from .llm.providers.common import full_url_client_options, normalize_base_url

    return OpenAI(
        **(full_url_client_options(base_url) if full_url else {}),
        api_key=api_key,
        # SDK 的资源路径本身不含版本段，因此在已规范化的服务根地址后补 /v1。
        base_url=normalize_base_url(base_url, "openai_chat", full_url=full_url),
        timeout=timeout_s,
        max_retries=0,
    )


def _anthropic_client(*, base_url: str, api_key: str, timeout_s: float, full_url: bool = False) -> Anthropic:
    """创建单次 Anthropic SDK 客户端，避免连接或限流时改变既有重试次数。"""
    from .llm.providers.common import full_url_client_options, normalize_base_url

    return Anthropic(
        **(full_url_client_options(base_url) if full_url else {}),
        api_key=api_key,
        # Anthropic SDK 自身会追加 /v1/messages，故这里只传服务根地址。
        base_url=normalize_base_url(base_url, "anthropic_messages", full_url=full_url),
        timeout=timeout_s,
        max_retries=0,
    )


def _sdk_response_dict(response: object) -> dict:
    """把 SDK 的 Pydantic 响应或流事件转换为既有归一化函数可消费的字典。"""
    model_dump = getattr(response, "model_dump", None)
    if callable(model_dump):
        payload = model_dump(mode="json")
    else:
        payload = response
    if not isinstance(payload, Mapping):
        raise TypeError("SDK 响应不是对象")
    return {str(key): value for key, value in payload.items()}


def _ensure_sse_stream(stream: object) -> None:
    """拒绝网关忽略 stream 参数时返回的完整 JSON，避免 SDK 静默产生空迭代。"""
    response = getattr(stream, "response", None)
    headers = getattr(response, "headers", None)
    content_type = headers.get("content-type") if isinstance(headers, Mapping) else None
    if content_type and "text/event-stream" not in str(content_type).lower():
        raise AppError(ErrorCode.UPSTREAM, "上游未返回流式响应")


def _openai_chat_create(client: object, body: dict, *, stream: bool = False) -> object:
    """调用 Chat Completions，并把兼容网关私有字段经 SDK 原样合入请求体。"""
    request = dict(body)
    if stream:
        # ``stream`` 是 SDK 的正式参数，不再作为手写 HTTP JSON 字段传递。
        request["stream"] = True
    vendor_body: dict[str, object] = {}
    if "thinking" in request:
        vendor_body["thinking"] = request.pop("thinking")
    if "extra_body" in request:
        # 当前 Gemini 兼容档要求请求 JSON 中存在字面 ``extra_body`` 字段；
        # SDK 的 extra_body 参数会合并请求体，故此处保留一层同名键。
        vendor_body["extra_body"] = request.pop("extra_body")
    create = client.chat.completions.create  # type: ignore[attr-defined]
    if vendor_body:
        return create(**request, extra_body=vendor_body)
    return create(**request)


def _anthropic_messages_create(
    client: object,
    body: dict,
    anthropic_version: str | None,
    *,
    stream: bool = False,
) -> object:
    """调用 Messages API，并保留协议档指定的 anthropic-version 请求头。"""
    request = dict(body)
    if stream:
        request["stream"] = True
    return client.messages.create(  # type: ignore[attr-defined]
        **request,
        extra_headers={"anthropic-version": anthropic_version or "2023-06-01"},
    )
