"""两类协议统一适配器（PRD 6.2 / 后端开发计划 M1 W3）。

统一入口 ``call_protocol``：入参为 ``messages`` 对话列表与采样参数，
出参统一为 ``AdapterResult(text, usage, raw, latency_ms)``。两类协议的
端点、鉴权头与响应结构差异全部在模块内消化：

- ``openai_chat``        POST ``{base}/v1/chat/completions``   ``Authorization: Bearer``
- ``anthropic_messages`` POST ``{base}/v1/messages``           ``x-api-key`` + ``anthropic-version``

失败语义统一归一为 ``AppError``：上游 4xx/5xx 与连接错误 → ``UPSTREAM``，
超时 → ``TIMEOUT``，响应结构异常 → ``UPSTREAM``；异常信息绝不携带 API Key。
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import anthropic
import openai
from anthropic import Anthropic
from openai import OpenAI

from .adapters_models import (  # noqa: F401
    _anthropic_model_list_roots,
    fetch_remote_models,  # noqa: F401  对外重导出
    service_base_url,
)
from .adapters_support import (  # noqa: F401  对外重导出（历史调用与测试直接引用）
    AdapterToolCall,
    _anthropic_system_param,
    _anthropic_thinking_budget,
    _apply_compatible_thinking,
    _apply_openai_reasoning,
    _complete_stream_tool_call,
    _finish_reason,
    _full_text,
    _full_tool_calls,
    _is_openai_reasoning_model,
    _new_call_id,
    _norm_usage,
    _openai_reasoning_effort,
    _prompt_cache_flag,
    _supports_anthropic_thinking,
    _tool_call_arguments,
)
from .errors import AppError, ErrorCode

# 兼容旧名：历史调用方与测试仍以 _service_base_url 引用
_service_base_url = service_base_url

if TYPE_CHECKING:
    # 仅类型检查可见：运行时导入会经 app.llm.__init__ → gateway → adapters
    # 形成循环，注解在 future annotations 下字符串化，无需运行时类型。
    from .llm.contracts import SystemSegment

# 契约支持的两类协议（与 protocol_profiles 的 CHECK 约束一致）
SUPPORTED_PROTOCOLS = ("openai_chat", "openai_responses", "anthropic_messages")

# 非流式调用被测 / Agent 模型的默认超时秒数
DEFAULT_TIMEOUT_S = 30.0
# 仅对已知支持 reasoning 控制的模型发送 OpenAI 专用字段，避免普通模型因未知字段报错。
_OPENAI_REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")

def _adapt_message_content(content: object, protocol: str) -> object:
    """把 Agent 内部内容块转换成目标协议的图文消息格式。"""
    if not isinstance(content, list):
        return content
    result: list[dict[str, object]] = []
    for part in content:
        if not isinstance(part, Mapping):
            continue
        kind = part.get("type")
        if kind == "text":
            result.append({"type": "text", "text": str(part.get("text") or "")})
            continue
        if kind != "image_url" or not isinstance(part.get("image_url"), Mapping):
            continue
        url = str(part["image_url"].get("url") or "")
        if not url:
            continue
        if protocol == "anthropic_messages" and url.startswith("data:"):
            header, encoded = url.split(",", 1)
            media_type = header[5:].split(";", 1)[0] or "image/jpeg"
            result.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": encoded,
                    },
                }
            )
        else:
            result.append({"type": "image_url", "image_url": {"url": url}})
    return result




def _internal_tool_calls(message: Mapping[str, object]) -> list[dict[str, object]]:
    """提取 Harness 规范的工具调用消息，过滤不完整项目。"""
    raw_calls = message.get("tool_calls")
    if not isinstance(raw_calls, list | tuple):
        return []
    calls: list[dict[str, object]] = []
    for raw in raw_calls:
        if not isinstance(raw, Mapping):
            continue
        call_id = str(raw.get("call_id") or raw.get("id") or "").strip()
        name = str(raw.get("name") or "").strip()
        arguments = raw.get("arguments")
        if not call_id or not name:
            continue
        try:
            calls.append(
                {
                    "call_id": call_id,
                    "name": name,
                    "arguments": _tool_call_arguments(arguments),
                }
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    return calls


def _adapt_messages(messages: list[dict], protocol: str) -> list[dict]:
    """把 Harness 消息映射为两类协议的图文与 ToolCall/ToolResult 结构。

    内部规范只使用 ``assistant.tool_calls`` 与 ``role=tool`` 两种表示；
    本函数在边界转换为各供应商的不同字段，调用方无需感知协议差异。
    """
    adapted: list[dict] = []
    anthropic_tool_results: list[dict[str, object]] = []

    def flush_anthropic_tool_results() -> None:
        """把同一 assistant 的多个 ToolResult 合并为一条 user 消息。"""
        if anthropic_tool_results:
            adapted.append({"role": "user", "content": list(anthropic_tool_results)})
            anthropic_tool_results.clear()

    for message in messages:
        role = str(message.get("role") or "user")
        calls = _internal_tool_calls(message)
        content = message.get("content")

        if role == "tool":
            call_id = str(message.get("tool_call_id") or "").strip()
            if not call_id:
                continue
            if protocol == "anthropic_messages":
                anthropic_tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call_id,
                        "content": str(content or ""),
                    }
                )
            else:
                adapted.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": str(content or ""),
                    }
                )
            continue

        if protocol == "anthropic_messages":
            flush_anthropic_tool_results()

        if calls and role == "assistant":
            if protocol == "anthropic_messages":
                blocks: list[object] = []
                if content:
                    blocks.append({"type": "text", "text": str(content)})
                blocks.extend(
                    {
                        "type": "tool_use",
                        "id": call["call_id"],
                        "name": call["name"],
                        "input": call["arguments"],
                    }
                    for call in calls
                )
                adapted.append({"role": "assistant", "content": blocks})
                continue
            adapted.append(
                {
                    "role": "assistant",
                    "content": _adapt_message_content(content, protocol),
                    "tool_calls": [
                        {
                            "id": call["call_id"],
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                            },
                        }
                        for call in calls
                    ],
                }
            )
            continue

        item = dict(message)
        item.pop("tool_calls", None)
        item["content"] = _adapt_message_content(content, protocol)
        adapted.append(item)
    if protocol == "anthropic_messages":
        flush_anthropic_tool_results()
    return adapted


def _adapt_tools(tools: list[dict] | None, protocol: str) -> list[dict]:
    """把内部 JSON Schema 工具定义映射为两类原生 ToolCall 描述。"""
    adapted: list[dict] = []
    for definition in tools or []:
        name = str(definition.get("name") or "").strip()
        if not name:
            continue
        description = str(definition.get("description") or "")
        schema = definition.get("parameters_schema") or definition.get("parameters") or {
            "type": "object",
            "properties": {},
        }
        if not isinstance(schema, Mapping):
            continue
        parameters = dict(schema)
        if protocol == "openai_chat":
            adapted.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": parameters,
                    },
                }
            )
        else:
            adapted.append(
                {
                    "name": name,
                    "description": description,
                    "input_schema": parameters,
                }
            )
    return adapted


class StreamAborted(Exception):
    """本地取消令牌在读上游时触发；由调用层转成 TurnCancelled，不发给浏览器。"""


@dataclass(frozen=True)
class AdapterStreamEvent:
    """流式适配器的内部事件；工具调用只在参数完整后发出。"""

    kind: str
    text: str = ""
    tool_call: AdapterToolCall | None = None


@dataclass(frozen=True)
class AdapterResult:
    """两类协议统一调用结果。

    ``usage`` 已归一为 ``prompt_tokens / completion_tokens / total_tokens``
    （上游缺失时按 0 计）；``raw`` 保留上游原始 JSON 对象，供报告与调试
    使用，消费方序列化落库时按契约截断到 32KB。
    """

    text: str
    usage: dict
    raw: dict
    latency_ms: int
    tool_calls: tuple[AdapterToolCall, ...] = field(default_factory=tuple)
    # 归一后的终止原因：stop / length / tool_calls / content_filter / None。
    # 生成类端点据此区分「模型乱写」与「输出被 max_tokens 截断」，前者换提示词，
    # 后者必须抬预算重试。
    finish_reason: str | None = None


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


def _build_request_body(
    *,
    protocol: str,
    base: str,
    model: str,
    messages: list[dict],
    system: str | None,
    temperature: float,
    max_tokens: int,
    reasoning_enabled: bool,
    reasoning_effort: str,
    tools: list[dict] | None,
    system_segments: tuple[SystemSegment, ...] | None,
    prompt_cache: bool | None,
) -> dict:
    """按协议拼装上游请求体；流式与非流式共用同一份逻辑，避免两处漂移。

    ``base`` 只用于识别 OpenAI 兼容端点（Mimo 等）是否需要额外思考字段。
    """
    native_tools = _adapt_tools(tools, protocol)
    if protocol == "openai_chat":
        chat: list[dict] = (
            ([{"role": "system", "content": system}] if system else [])
            + _adapt_messages(messages, protocol)
        )
        body: dict = {
            "model": model,
            "messages": chat,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if native_tools:
            body["tools"] = native_tools
        _apply_compatible_thinking(body, base, model, reasoning_enabled, reasoning_effort)
        _apply_openai_reasoning(
            body, model=model, enabled=reasoning_enabled, effort=reasoning_effort
        )
        return body

    body = {
        "model": model,
        "messages": _adapt_messages(messages, protocol),
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if native_tools:
        body["tools"] = native_tools
    if system:
        body["system"] = _anthropic_system_param(
            system,
            system_segments,
            cache_enabled=_prompt_cache_flag(prompt_cache),
        )
    if reasoning_enabled and _supports_anthropic_thinking(model):
        body["thinking"] = {
            "type": "enabled",
            "budget_tokens": _anthropic_thinking_budget(max_tokens, reasoning_effort),
        }
        # Anthropic extended thinking 要求 temperature 使用默认值 1。
        body["temperature"] = 1.0
    return body


def call_protocol(
    *,
    protocol: str,
    base_url: str,
    full_url: bool = False,
    model: str,
    api_key: str,
    messages: list[dict],
    system: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 8192,
    anthropic_version: str | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    reasoning_enabled: bool = False,
    reasoning_effort: str = "medium",
    tools: list[dict] | None = None,
    system_segments: tuple[SystemSegment, ...] | None = None,
    prompt_cache: bool | None = None,
) -> AdapterResult:
    """按协议适配调用上游模型并返回统一结构的结果对象。

    ``messages`` 为 ``[{"role": "user" | "assistant", "content": "..."}]``；
    系统提示词经 ``system`` 独立传入，由各协议以自身字段承载
    （chat 的 system 消息 / anthropic 的 system）。
    """
    if protocol not in SUPPORTED_PROTOCOLS:
        raise AppError(ErrorCode.VALIDATION, f"协议不受支持：{protocol}")

    if protocol == "openai_responses":
        from .responses_adapter import call_responses

        return call_responses(base_url=base_url, api_key=api_key, timeout_s=timeout_s, full_url=full_url,
            model=model, messages=messages, system=system, temperature=temperature, max_tokens=max_tokens,
            reasoning_enabled=reasoning_enabled, reasoning_effort=reasoning_effort, tools=tools)

    base = base_url.strip() if full_url else service_base_url(base_url)
    client: object | None = None

    body = _build_request_body(
        protocol=protocol,
        base=base,
        model=model,
        messages=messages,
        system=system,
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_enabled=reasoning_enabled,
        reasoning_effort=reasoning_effort,
        tools=tools,
        system_segments=system_segments,
        prompt_cache=prompt_cache,
    )
    started = time.perf_counter()
    try:
        if protocol == "openai_chat":
            client = _openai_client(base_url=base, api_key=api_key, timeout_s=timeout_s, **({"full_url": True} if full_url else {}))
            response = _openai_chat_create(client, body)
        else:
            client = _anthropic_client(base_url=base, api_key=api_key, timeout_s=timeout_s, **({"full_url": True} if full_url else {}))
            response = _anthropic_messages_create(client, body, anthropic_version)
        data = _sdk_response_dict(response)
    except (openai.APITimeoutError, anthropic.APITimeoutError) as exc:
        raise AppError(ErrorCode.TIMEOUT, "上游调用超时") from exc
    except (openai.APIStatusError, anthropic.APIStatusError) as exc:
        # 仅回显状态码，绝不把请求头（含 Key）或上游原文带给浏览器。
        raise AppError(ErrorCode.UPSTREAM, f"上游返回 {exc.status_code}") from exc
    except (openai.APIConnectionError, anthropic.APIConnectionError) as exc:
        raise AppError(ErrorCode.UPSTREAM, "上游连接失败") from exc
    except (openai.APIError, anthropic.APIError) as exc:
        raise AppError(ErrorCode.UPSTREAM, "上游调用失败") from exc
    finally:
        if client is not None:
            _close_quietly(client)

    latency_ms = round((time.perf_counter() - started) * 1000)
    try:
        text = _full_text(protocol, data)
        tool_calls = _full_tool_calls(protocol, data)
    except (KeyError, IndexError, TypeError, AttributeError, ValueError) as exc:
        raise AppError(ErrorCode.UPSTREAM, "上游响应结构异常") from exc

    return AdapterResult(
        text=text,
        usage=_norm_usage(data, anthropic=protocol == "anthropic_messages"),
        raw=data,
        latency_ms=latency_ms,
        tool_calls=tool_calls,
        finish_reason=_finish_reason(protocol, data),
    )


def stream_protocol(
    *,
    protocol: str,
    base_url: str,
    full_url: bool = False,
    model: str,
    api_key: str,
    messages: list[dict],
    system: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 8192,
    anthropic_version: str | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    should_abort: Callable[[], bool] | None = None,
    reasoning_enabled: bool = True,
    reasoning_effort: str = "medium",
    tools: list[dict] | None = None,
    system_segments: tuple[SystemSegment, ...] | None = None,
    prompt_cache: bool | None = None,
) -> Iterator[tuple[str, str] | AdapterStreamEvent]:
    """按协议流式调用上游模型，逐块 yield ``(kind, text)`` 增量。

    ``kind`` 为增量类别：``"content"`` 是正式回复正文，``"reasoning"``
    是推理模型的前置思考链（deepseek 风格 ``reasoning_content`` /
    anthropic ``thinking_delta``），
    供前端思考卡展示；上游未产生思考链时全程只 yield content。

    SDK 负责 SSE 建连、解帧与事件反序列化；适配器只消费 SDK 的事件对象，
    所以不再持有手写 ``urlopen``、逐行读取或非 SSE 重解析逻辑。``timeout_s``
    同时配置给 SDK 并约束本地事件循环的总时长；超时归一为 TIMEOUT，上游
    4xx/5xx 与流式解码失败归一为 UPSTREAM。原生工具参数会在适配器内累积，
    只有完整 JSON 才以 ``AdapterStreamEvent(tool_call)`` 发出。
    """
    if protocol not in SUPPORTED_PROTOCOLS:
        raise AppError(ErrorCode.VALIDATION, f"协议不受支持：{protocol}")

    if protocol == "openai_responses":
        from .responses_adapter import stream_responses

        yield from stream_responses(base_url=base_url, api_key=api_key, timeout_s=timeout_s, full_url=full_url,
            model=model, messages=messages, system=system, temperature=temperature, max_tokens=max_tokens,
            reasoning_enabled=reasoning_enabled, reasoning_effort=reasoning_effort, tools=tools, should_abort=should_abort)
        return

    base = base_url.strip() if full_url else service_base_url(base_url)
    def complete_stream_call(
        raw_id: object, raw_name: object, raw_arguments: object
    ) -> list[AdapterToolCall]:
        """把单项完成调用包装为列表，便于三个协议统一消费。"""
        call = _complete_stream_tool_call(raw_id, raw_name, raw_arguments)
        return [call] if call is not None else []

    def drain_tool_calls(states: dict[str, dict[str, object]]) -> list[AdapterToolCall]:
        """在完成信号或流结束时一次性输出所有已累计调用。"""
        completed: list[AdapterToolCall] = []
        for key in tuple(states):
            state = states.pop(key)
            parts = state.get("arguments")
            raw_arguments = (
                "".join(str(part) for part in parts)
                if isinstance(parts, list)
                else ""
            )
            raw_arguments = raw_arguments or state.get("input")
            completed.extend(
                complete_stream_call(
                    state.get("call_id"), state.get("name"), raw_arguments
                )
            )
        return completed

    if protocol == "openai_chat":
        body = _build_request_body(
            protocol=protocol,
            base=base,
            model=model,
            messages=messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_enabled=reasoning_enabled,
            reasoning_effort=reasoning_effort,
            tools=tools,
            system_segments=system_segments,
            prompt_cache=prompt_cache,
        )

        def delta_of(data: dict) -> tuple[str, str]:
            choices = data.get("choices") or [{}]
            delta = choices[0].get("delta") or {}
            reasoning = (
                delta.get("reasoning_content")
                or delta.get("reasoning")
                or delta.get("thought")
                or delta.get("thinking")
            )
            if reasoning:
                # 推理模型的思考链增量（deepseek/mimo/qwen 等风格）
                return ("reasoning", str(reasoning))
            return ("content", str(delta.get("content") or ""))

        chat_calls: dict[str, dict[str, object]] = {}

        def tool_events_of(data: dict) -> list[AdapterToolCall]:
            """累计 Chat Completions 的 indexed tool_calls，完成信号后再输出。"""
            choices = data.get("choices") or [{}]
            choice = choices[0] if isinstance(choices[0], Mapping) else {}
            delta = choice.get("delta") or {}
            raw_calls = delta.get("tool_calls") if isinstance(delta, Mapping) else None
            if isinstance(raw_calls, list):
                for index, raw_call in enumerate(raw_calls):
                    if not isinstance(raw_call, Mapping):
                        continue
                    key = str(raw_call.get("index", index))
                    state = chat_calls.setdefault(key, {"arguments": []})
                    if raw_call.get("id"):
                        state["call_id"] = raw_call["id"]
                    function = raw_call.get("function") or {}
                    if isinstance(function, Mapping):
                        if function.get("name"):
                            state["name"] = function["name"]
                        arguments = function.get("arguments")
                        if arguments:
                            state["arguments"].append(str(arguments))
            if choice.get("finish_reason") not in {"tool_calls", "function_call"}:
                return []
            return drain_tool_calls(chat_calls)

        def flush_tool_events() -> list[AdapterToolCall]:
            return drain_tool_calls(chat_calls)

    else:  # anthropic_messages
        body = _build_request_body(
            protocol=protocol,
            base=base,
            model=model,
            messages=messages,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_enabled=reasoning_enabled,
            reasoning_effort=reasoning_effort,
            tools=tools,
            system_segments=system_segments,
            prompt_cache=prompt_cache,
        )

        def delta_of(data: dict) -> tuple[str, str]:  # noqa: F811
            if data.get("type") == "content_block_delta":
                delta = data.get("delta") or {}
                if delta.get("type") == "thinking_delta":
                    return ("reasoning", str(delta.get("thinking") or ""))
                if delta.get("type") == "text_delta":
                    return ("content", str(delta.get("text") or ""))
            return ("content", "")

        anthropic_calls: dict[str, dict[str, object]] = {}

        def tool_events_of(data: dict) -> list[AdapterToolCall]:
            """累计 Anthropic input_json_delta，在 content_block_stop 时完成调用。"""
            event_type = str(data.get("type") or "")
            raw_index = data.get("index")
            index = str(raw_index) if raw_index is not None else ""
            if event_type == "content_block_start":
                block = data.get("content_block") or {}
                if isinstance(block, Mapping) and block.get("type") == "tool_use":
                    anthropic_calls[index] = {
                        "call_id": block.get("id"),
                        "name": block.get("name"),
                        "arguments": [],
                        "input": block.get("input"),
                    }
                return []
            if event_type == "content_block_delta" and index in anthropic_calls:
                delta = data.get("delta") or {}
                if isinstance(delta, Mapping) and delta.get("type") == "input_json_delta":
                    partial = delta.get("partial_json")
                    if partial:
                        anthropic_calls[index]["arguments"].append(str(partial))
                return []
            if event_type == "content_block_stop" and index in anthropic_calls:
                state = anthropic_calls.pop(index)
                raw_arguments = "".join(state.get("arguments", [])) or state.get("input")
                return complete_stream_call(
                    state.get("call_id"), state.get("name"), raw_arguments
                )
            return []

        def flush_tool_events() -> list[AdapterToolCall]:
            return drain_tool_calls(anthropic_calls)

    if should_abort is not None and should_abort():
        raise StreamAborted()

    deadline = time.monotonic() + timeout_s
    client: object | None = None
    stream: object | None = None
    try:
        if protocol == "openai_chat":
            client = _openai_client(base_url=base, api_key=api_key, timeout_s=timeout_s, **({"full_url": True} if full_url else {}))
            stream = _openai_chat_create(client, body, stream=True)
        else:
            client = _anthropic_client(base_url=base, api_key=api_key, timeout_s=timeout_s, **({"full_url": True} if full_url else {}))
            stream = _anthropic_messages_create(
                client,
                body,
                anthropic_version,
                stream=True,
            )
        _ensure_sse_stream(stream)

        for event in stream:  # type: ignore[union-attr]
            # SDK 只能在流事件边界响应取消；立即关闭其 Stream，避免连接悬挂。
            if should_abort is not None and should_abort():
                _close_quietly(stream)
                raise StreamAborted()
            if time.monotonic() > deadline:
                _close_quietly(stream)
                raise TimeoutError("stream deadline exceeded")

            data = _sdk_response_dict(event)
            kind, text = delta_of(data)
            if text:
                yield (kind, text)
            for tool_call in tool_events_of(data):
                yield AdapterStreamEvent(kind="tool_call", tool_call=tool_call)
    except StreamAborted:
        raise
    except (openai.APITimeoutError, anthropic.APITimeoutError, TimeoutError) as exc:
        raise AppError(ErrorCode.TIMEOUT, "上游调用超时") from exc
    except (openai.APIStatusError, anthropic.APIStatusError) as exc:
        # 仅回显状态码，绝不把请求头（含 Key）或上游原文带给浏览器。
        raise AppError(ErrorCode.UPSTREAM, f"上游返回 {exc.status_code}") from exc
    except (openai.APIConnectionError, anthropic.APIConnectionError) as exc:
        raise AppError(ErrorCode.UPSTREAM, "上游连接失败") from exc
    except (openai.APIError, anthropic.APIError) as exc:
        raise AppError(ErrorCode.UPSTREAM, "上游调用失败") from exc
    except OSError as exc:
        # SDK 读连接中断不向浏览器回显原始异常。
        raise AppError(ErrorCode.UPSTREAM, "上游连接中断") from exc
    except (AttributeError, TypeError, ValueError) as exc:
        # SDK 解帧或 Pydantic 转换失败时，不允许把上游原文带给浏览器。
        raise AppError(ErrorCode.UPSTREAM, "上游流式响应结构异常") from exc
    finally:
        if stream is not None:
            _close_quietly(stream)
        if client is not None:
            _close_quietly(client)

    # 少数兼容网关不发送 finish/done 事件；SDK 流自然结束后补齐未完成调用。
    for tool_call in flush_tool_events():
        yield AdapterStreamEvent(kind="tool_call", tool_call=tool_call)


