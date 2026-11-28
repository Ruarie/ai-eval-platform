"""页面候选用例的生成与对比。API 与 Worker 共用这一份整理逻辑。

模型调用由调用方注入：API 单测可以直接传入假模型，Worker 用自己的协议客户端。
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any

from shared.case_compare import compare_case_runs
from shared.casegen import (
    build_prompts,
    dedupe_cases,
    generation_token_budget,
    mark_pending_complete,
    parse_cases_with_stats,
    rebalance_with_stats,
    selfcheck,
)

logger = logging.getLogger("case_preview")

GENERATION_TIMEOUT_S = 280.0


class PreviewError(Exception):
    """候选整理失败。code 使用平台错误码字符串。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def materialize_cases(
    text: str, max_count: int, weights: dict[str, int]
) -> tuple[list[dict], dict[str, int]]:
    """解析、去重再按策略裁剪。"""
    try:
        cases, parse_stats = parse_cases_with_stats(text)
    except (ValueError, TypeError) as exc:
        raise PreviewError("UPSTREAM", "模型输出无法解析为用例") from exc
    cases, dropped_duplicate = dedupe_cases(cases)
    cases, dropped = rebalance_with_stats(cases, max_count, weights=weights)
    return cases, {**dropped, "dropped_duplicate": dropped_duplicate, **parse_stats}


def generate_candidates(
    source_text: str,
    max_count: int,
    weights: dict[str, int],
    call_model: Any,
) -> dict[str, Any]:
    """调用注入的模型并返回与原同步接口相同的候选结构（不含 source_truncated）。"""
    system, user_prompt = build_prompts(source_text, max_count, weights=weights)
    result = call_model(
        system,
        user_prompt,
        temperature=0.3,
        max_tokens=generation_token_budget(max_count),
        timeout_s=GENERATION_TIMEOUT_S,
    )
    cases, dropped = materialize_cases(getattr(result, "text", "") or "", max_count, weights)
    if not cases:
        raise PreviewError("UPSTREAM", "模型未返回符合所选策略的有效用例")
    return {
        "items": [mark_pending_complete(case) for case in cases],
        "checks": selfcheck(cases, weights=weights, source_text=source_text),
        "dropped": dropped,
    }


def _error_parts(exc: Exception) -> tuple[str, str]:
    """从平台错误里取出码和文案；未知异常不把原文交给调用方。"""
    code = getattr(exc, "code", None)
    if hasattr(code, "value"):
        code = code.value
    message = getattr(exc, "message", None)
    if isinstance(code, str) and isinstance(message, str) and message:
        return code, message
    logger.warning("模型对比单侧失败 type=%s", type(exc).__name__)
    return "INTERNAL", "AI 生成调用失败，请稍后重试"


def _failed_run(profile: Any, code: str, message: str, elapsed_ms: int) -> dict[str, Any]:
    return {
        "profile_id": profile.id,
        "profile_name": profile.name,
        "model": getattr(profile, "model", "") or "",
        "ok": False,
        "error": {"code": code, "message": message},
        "elapsed_ms": elapsed_ms,
        "items": [],
        "checks": [],
        "dropped": {},
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _one_side(
    profile: Any,
    system: str,
    user_prompt: str,
    max_count: int,
    weights: dict[str, int],
    call_profile: Any,
    source_text: str = "",
) -> dict[str, Any]:
    """跑一侧模型。失败留在该侧，不让另一侧被整单错误盖掉。"""
    started = time.perf_counter()
    payload = _failed_run(profile, "INTERNAL", "", 0)
    payload["error"] = None
    payload["dropped"] = {
        "dropped_unknown_strategy": 0,
        "dropped_over_quota": 0,
        "dropped_duplicate": 0,
        "dropped_missing_name": 0,
        "dropped_non_object": 0,
    }
    try:
        result = call_profile(
            profile,
            system,
            user_prompt,
            temperature=0.3,
            max_tokens=generation_token_budget(max_count),
            timeout_s=GENERATION_TIMEOUT_S,
        )
        cases, dropped = materialize_cases(getattr(result, "text", "") or "", max_count, weights)
        if not cases:
            raise PreviewError("UPSTREAM", "模型未返回符合所选策略的有效用例")
        usage = getattr(result, "usage", None) or {}
        payload.update({
            "ok": True,
            "model": getattr(profile, "model", "") or "",
            "items": [mark_pending_complete(case) for case in cases],
            "checks": selfcheck(cases, weights=weights, source_text=source_text),
            "dropped": dropped,
            "usage": {
                "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                "completion_tokens": int(usage.get("completion_tokens") or 0),
                "total_tokens": int(usage.get("total_tokens") or 0),
            },
        })
    except Exception as exc:
        code, message = _error_parts(exc)
        payload["error"] = {"code": code, "message": message}
    payload["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    return payload


def run_compare(
    profiles: list[Any],
    source_text: str,
    max_count: int,
    weights: dict[str, int],
    call_profile: Any,
) -> dict[str, Any]:
    """两侧并行生成。墙钟接近较慢的一侧。"""
    system, user_prompt = build_prompts(source_text, max_count, weights=weights)
    pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="case-compare")
    try:
        futures = [
            pool.submit(
                _one_side, profile, system, user_prompt, max_count, weights, call_profile, source_text,
            )
            for profile in profiles
        ]
        runs: list[dict[str, Any]] = []
        for profile, future in zip(profiles, futures, strict=True):
            try:
                runs.append(future.result(timeout=GENERATION_TIMEOUT_S + 5))
            except FutureTimeout:
                runs.append(_failed_run(
                    profile,
                    "TIMEOUT",
                    "模型对比超时，请减少生成条数后重试",
                    int(GENERATION_TIMEOUT_S * 1000),
                ))
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    comparison = compare_case_runs(
        runs[0]["items"] if runs[0]["ok"] else [],
        runs[1]["items"] if runs[1]["ok"] else [],
        weights,
        left_name=runs[0]["profile_name"] or "模型 A",
        right_name=runs[1]["profile_name"] or "模型 B",
        left_ok=bool(runs[0]["ok"]),
        right_ok=bool(runs[1]["ok"]),
        source_text=source_text,
    )
    return {"runs": runs, "comparison": comparison}
