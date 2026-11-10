"""从 Agent 回合事实里取出可统计的 token 用量。

用量中心和消息投影共用这一份口径：只保留上游返回的数字，不读正文。
"""

from __future__ import annotations

from typing import Any


def assistant_meter(data: dict[str, Any] | None) -> dict[str, Any]:
    """从 ``assistant/message`` 事实取出用量、模型名和耗时。

    没有 ``usage`` 对象时 ``turn_stats`` 为 None，调用方不把它算进用量。
    """
    payload = data if isinstance(data, dict) else {}
    usage = payload.get("usage")
    if not isinstance(usage, dict) or not usage:
        usage = None
    source: dict[str, Any] = {}
    message = payload.get("message")
    if isinstance(message, dict) and isinstance(message.get("source"), dict):
        source = message["source"]
    model = source.get("model")
    provider = source.get("provider")
    latency = payload.get("latency_ms")
    return {
        "turn_stats": {"usage": usage} if usage else None,
        "model_name": model if isinstance(model, str) and model.strip() else None,
        "provider": provider if isinstance(provider, str) and provider.strip() else None,
        "latency_ms": latency if isinstance(latency, int) and not isinstance(latency, bool) and latency >= 0 else None,
    }
