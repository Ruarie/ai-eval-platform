"""协议适配的共享工具：消息/工具规整、用量与结束原因归一、缓存与思考字段。

从 adapters.py 拆出后由适配层引用；全部为纯数据变换，不持有客户端或连接状态。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import uuid4

from .config import settings
from .errors import AppError, ErrorCode

if TYPE_CHECKING:
    from .llm.contracts import SystemSegment


_OPENAI_REASONING_PREFIXES = ("o1", "o3", "o4", "gpt-5")
_REASONING_EFFORTS = {"low", "medium", "high", "xhigh", "max"}

def _tool_call_arguments(raw: object) -> dict[str, object]:
    """把上游函数参数归一为对象，拒绝无效 JSON 而不猜测执行参数。"""
    if isinstance(raw, Mapping):
        return {str(key): value for key, value in raw.items()}
    if raw in (None, ""):
        return {}
    if not isinstance(raw, str):
        raise ValueError("工具参数不是 JSON 对象")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("工具参数不是 JSON 对象")
    return {str(key): value for key, value in parsed.items()}



def _is_openai_reasoning_model(model: str) -> bool:
    """判断模型名是否属于 OpenAI/o 系列或明确的推理模型。"""
    normalized = model.strip().lower()
    return normalized.startswith(_OPENAI_REASONING_PREFIXES) or any(
        marker in normalized for marker in ("reasoner", "reasoning", "deepseek-r1")
    )


def _openai_reasoning_effort(model: str, enabled: bool, effort: str) -> str | None:
    """返回可发送的 OpenAI effort；普通模型不携带推理专用字段。"""
    # CursorAPI 将模型可选项编码在 ``model[param=value]`` 中，并不会读取
    # OpenAI 请求体的 reasoning_effort；检测到该规格时保留模型名原样透传。
    if "[" in model and model.rstrip().endswith("]"):
        return None
    if not _is_openai_reasoning_model(model):
        return None
    if enabled and effort in _REASONING_EFFORTS:
        return effort
    # 当前新一代 GPT-5/o4 模型支持 none；老模型关闭时仅由网关过滤摘要。
    normalized = model.strip().lower()
    if normalized.startswith(("gpt-5", "o4")):
        return "none"
    return None


def _apply_openai_reasoning(
    body: dict,
    *,
    model: str,
    enabled: bool,
    effort: str,
) -> None:
    """按 Chat Completions 的字段写入推理控制参数。"""
    selected = _openai_reasoning_effort(model, enabled, effort)
    if selected is None:
        return
    body["reasoning_effort"] = selected


def _apply_compatible_thinking(
    body: dict,
    base: str,
    model: str,
    enabled: bool,
    effort: str = "medium",
) -> None:
    """为已知 OpenAI 兼容推理端点设置 thinking 开关。"""
    target = f"{base} {model}".lower()
    if "xiaomimimo" in target:
        body["thinking"] = {"type": "enabled" if enabled else "disabled"}
        return

    # Gemini 的 OpenAI 兼容接口不会仅凭模型名把思考摘要放进流；必须
    # 显式传入 Google 扩展字段。这里使用 REST 请求所需的 extra_body
    # 结构，避免把供应商专用字段误发给普通 OpenAI 兼容模型。
    if "gemini" in model.strip().lower() and enabled:
        level = {
            "low": "low",
            "medium": "medium",
            "high": "high",
            # 平台的更高档位映射为 Gemini 支持的最高 thinking_level。
            "xhigh": "high",
            "max": "high",
        }.get(effort, "medium")
        body["extra_body"] = {
            "google": {
                "thinking_config": {
                    "thinking_level": level,
                    "include_thoughts": True,
                }
            }
        }
        return

    # 阿里云 MaaS 网关上的推理模型（deepseek-v4 / glm 等）默认开启思考，会把
    # max_tokens 全部用于 reasoning_content，正文为空或截断——这正是 40 条用例
    # 批量生成 100% 失败、12 条生成偶发 502 的根因。生成类调用（enabled=False）
    # 显式关闭思考，与 Worker 侧 protocol.py 保持同一口径（该字段已在评测链路验证）。
    # 其它推理供应商不在这里猜测专有字段：截断由 llm_client 的重试与
    # BUDGET_EXCEEDED 兜底，避免向不支持的端点发送未知参数。
    if "maas.aliyuncs.com" in target:
        body["thinking"] = {"type": "enabled" if enabled else "disabled"}
        return


def _anthropic_thinking_budget(max_tokens: int, effort: str) -> int:
    """把平台强度映射为 Anthropic thinking budget，并限制在输出预算内。"""
    ratio = {"low": 0.2, "medium": 0.4, "high": 0.6, "xhigh": 0.75, "max": 0.8}.get(effort, 0.4)
    return max(256, min(max_tokens - 1, round(max_tokens * ratio)))


def _supports_anthropic_thinking(model: str) -> bool:
    """仅对已知支持 extended thinking 的 Claude 型号发送 thinking 字段。"""
    normalized = model.strip().lower()
    return any(
        marker in normalized
        for marker in ("claude-3-7", "claude-sonnet-4", "claude-opus-4", "claude-haiku-4")
    )


@dataclass(frozen=True)
class AdapterToolCall:
    """协议适配器输出的原生工具调用（不依赖 LangGraph 契约包）。"""

    call_id: str
    name: str
    arguments: Mapping[str, object]


def _finish_reason(protocol: str, data: dict) -> str | None:
    """归一终止原因，供生成类端点判断是否被输出上限截断。

    两类协议用不同词表表达同一件事：OpenAI 的 ``finish_reason=length`` 与
    Anthropic 的 ``stop_reason=max_tokens`` 都意味着正文不完整。
    """
    try:
        if protocol == "openai_responses":
            if data.get("status") == "incomplete":
                reason = (data.get("incomplete_details") or {}).get("reason")
                return "length" if reason == "max_output_tokens" else str(reason or "incomplete")
            return "stop"
        if protocol == "openai_chat":
            choices = data.get("choices") or []
            first = choices[0] if choices and isinstance(choices[0], Mapping) else {}
            raw = first.get("finish_reason")
            return None if raw is None else str(raw)
        raw = data.get("stop_reason")
        if raw is None:
            return None
        return {"end_turn": "stop", "max_tokens": "length", "tool_use": "tool_calls"}.get(str(raw), str(raw))
    except (AttributeError, TypeError, IndexError):
        return None


def _norm_usage(data: dict, *, anthropic: bool) -> dict:
    """把两类协议各自的 usage 字段归一为统一 token 与缓存计数结构。

    缓存字段仅在上游明确返回时透传：Anthropic 使用 input token 的读/创建
    计数，OpenAI 使用 ``prompt_tokens_details.cached_tokens``。缺失表示上游
    未提供该观测，不能伪造为命中或零命中。
    """
    usage = data.get("usage") or {}
    if not isinstance(usage, Mapping):
        usage = {}
    if anthropic:
        # Anthropic 使用 input_tokens / output_tokens 命名，total 需自行求和
        prompt = int(usage.get("input_tokens") or 0)
        completion = int(usage.get("output_tokens") or 0)
        normalized = {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        }
        cache_read = int(usage.get("cache_read_input_tokens") or 0)
        cache_creation = int(usage.get("cache_creation_input_tokens") or 0)
        if cache_read or cache_creation:
            normalized.update(
                cache_read_input_tokens=cache_read,
                cache_creation_input_tokens=cache_creation,
            )
        return normalized
    # OpenAI Chat 与兼容网关使用 prompt/completion_tokens。
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or (prompt + completion))
    normalized = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }
    details = usage.get("prompt_tokens_details")
    if isinstance(details, Mapping):
        cache_read = int(details.get("cached_tokens") or 0)
        if cache_read:
            normalized["cache_read_input_tokens"] = cache_read
    return normalized


def _full_text(protocol: str, data: dict) -> str:
    """从完整（非流式）响应对象中提取全文，供 call_protocol 与流式兜底复用。"""
    if protocol == "openai_chat":
        # 兼容网关在 max_tokens=1 时可能返回 content=None
        choices = data["choices"]
        return str(choices[0]["message"].get("content") or "")
    # anthropic_messages：content 数组内仅拼接 text 内容块
    return "".join(str(block.get("text") or "") for block in data["content"] if block.get("type") == "text")


def _new_call_id() -> str:
    """为未提供调用 ID 的兼容端点生成稳定的本轮关联标识。"""
    return f"toolcall_{uuid4().hex}"


def _full_tool_calls(protocol: str, data: dict) -> tuple[AdapterToolCall, ...]:
    """从两类协议完整响应提取函数调用并统一参数与调用 ID。"""
    raw_calls: list[tuple[object, object, object]] = []
    if protocol == "openai_chat":
        message = (data.get("choices") or [{}])[0].get("message") or {}
        calls = message.get("tool_calls") or []
        if not calls and isinstance(message.get("function_call"), Mapping):
            calls = [{"id": "", "function": message["function_call"]}]
        for call in calls:
            if not isinstance(call, Mapping):
                continue
            function = call.get("function") or {}
            if isinstance(function, Mapping):
                raw_calls.append((call.get("id"), function.get("name"), function.get("arguments")))
    else:
        for block in data.get("content") or []:
            if isinstance(block, Mapping) and block.get("type") == "tool_use":
                raw_calls.append((block.get("id"), block.get("name"), block.get("input")))

    calls: list[AdapterToolCall] = []
    for raw_id, raw_name, raw_arguments in raw_calls:
        name = str(raw_name or "").strip()
        if not name:
            # 少数兼容网关会在普通文本响应里附带不完整的 tool_use 占位块；
            # 它不构成可执行调用，忽略而不是把正常正文升级为上游错误。
            continue
        calls.append(
            AdapterToolCall(
                call_id=str(raw_id or "").strip() or _new_call_id(),
                name=name,
                arguments=_tool_call_arguments(raw_arguments),
            )
        )
    return tuple(calls)


def _complete_stream_tool_call(
    raw_id: object,
    raw_name: object,
    raw_arguments: object,
) -> AdapterToolCall | None:
    """把已累计完成的流式参数转换为可执行调用，拒绝不完整 JSON。"""
    name = str(raw_name or "").strip()
    if not name:
        return None
    try:
        arguments = _tool_call_arguments(raw_arguments)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError(ErrorCode.UPSTREAM, "上游工具调用参数结构异常") from exc
    return AdapterToolCall(
        call_id=str(raw_id or "").strip() or _new_call_id(),
        name=name,
        arguments=arguments,
    )


def _anthropic_system_param(
    system: str | None,
    segments: tuple[SystemSegment, ...] | None = None,
    *,
    cache_enabled: bool = False,
) -> str | list[dict[str, object]]:
    """Anthropic Messages 的 system 参数：缓存边界开启时返回带断点的内容块数组。

    ADR-5：断点只落在**最后一个可缓存静态段**（S1 Persona / S2 Skill Hint /
    S4 Skill 工作流），动态段（S6 会话摘要、S7 当轮输入）位于断点之后随请求
    发送但不计入缓存前缀。不满足条件（开关关 / 无分段）时返回原字符串，
    行为与骨架化版本一致。``cache_control`` 由协议档 anthropic-version
    （2023-06-01 起支持）承载；上游不支持时错误归一兜底，调用方可关闭开关。
    OpenAI 系协议依赖自动前缀缓存，仅需保证前缀字节级稳定，不做本处理。
    """
    if not cache_enabled or not segments:
        return system or ""
    blocks: list[dict[str, object]] = []
    last_cacheable: int | None = None
    for index, segment in enumerate(segments):
        if segment.cacheable and segment.text:
            last_cacheable = index
    for index, segment in enumerate(segments):
        if not segment.text:
            continue
        block: dict[str, object] = {"type": "text", "text": segment.text}
        if index == last_cacheable:
            block["cache_control"] = {"type": "ephemeral"}
        blocks.append(block)
    return blocks


def _prompt_cache_flag(prompt_cache: bool | None) -> bool:
    """缓存开关判定：显式传入优先，否则读运行配置（默认关闭）。"""
    return settings.prompt_cache_enabled if prompt_cache is None else prompt_cache
