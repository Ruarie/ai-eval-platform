"""历史轨迹查询（N-09 MVP）。

数据源是已持久化的 ``agent_events``；本接口只返回事件元数据，不返回消息正文、
工具结果、提示词或任何凭据。轨迹用于定位慢请求、工具失败与审批等待，不替代审计。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import AgentEvent, User
from ..schemas import TraceEventOut, TraceTurnDetailOut, TraceTurnOut
from ..session_access import require_visible_session

router = APIRouter(prefix="/api/sessions/{session_id}/trace", tags=["traces"])

MAX_EVENTS = 5000
MAX_TURN_EVENTS = 500


def _turn_of(envelope: dict[str, Any]) -> int | None:
    """从 data 或 correlation 中取回合号；非整数不猜测。"""
    data = envelope.get("data") if isinstance(envelope.get("data"), dict) else {}
    value = data.get("turn")
    if value is None:
        correlation = envelope.get("correlation")
        if isinstance(correlation, dict):
            value = correlation.get("turn")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _usage(data: dict[str, Any]) -> tuple[int, int, int]:
    """提取 usage；只取数字，缺失不推断。"""
    stats = data.get("turn_stats")
    usage = stats.get("usage") if isinstance(stats, dict) else None
    if not isinstance(usage, dict):
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    prompt = usage.get("prompt_tokens", usage.get("input_tokens", 0))
    completion = usage.get("completion_tokens", usage.get("output_tokens", 0))
    total = usage.get("total_tokens", 0)
    prompt = int(prompt) if isinstance(prompt, int | float) and not isinstance(prompt, bool) else 0
    completion = int(completion) if isinstance(completion, int | float) and not isinstance(completion, bool) else 0
    total = int(total) if isinstance(total, int | float) and not isinstance(total, bool) else prompt + completion
    return prompt, completion, total


def _error_code(data: dict[str, Any]) -> str:
    """错误码只取短字符串，避免把上游原文带回浏览器。"""
    value = data.get("error_code") or data.get("code")
    if not value and isinstance(data.get("error"), dict):
        value = data["error"].get("code")
    return str(value or "")[:80]


def _event_name(kind: str, data: dict[str, Any]) -> str:
    """事件名称白名单式投影，不拼接任意 data。"""
    if kind.startswith("tool/"):
        return str(data.get("name") or data.get("tool_name") or data.get("tool") or "tool")[:80]
    if kind.startswith("assistant/"):
        return "model"
    if kind.startswith("approval/") or kind.startswith("question/"):
        return str(data.get("tool_name") or data.get("name") or kind.split("/", 1)[0])[:80]
    if kind.startswith("turn/"):
        return "turn"
    return kind.split("/", 1)[0][:40]


def _status(kind: str, data: dict[str, Any]) -> str:
    """只展示状态/原因等短字段。"""
    if kind == "turn/start":
        return "running"
    if kind == "turn/end":
        return str(data.get("reason") or "finished")[:40]
    if kind == "runtime/error":
        return "failed"
    if kind == "assistant/attempt":
        return str(data.get("finish_reason") or "finished")[:40]
    if kind == "tool/call":
        return "called"
    if kind == "tool/result":
        return str(data.get("status") or "finished")[:40]
    if kind == "approval/asked" or kind == "question/asked":
        return "waiting"
    if kind == "approval/decided" or kind == "question/answered":
        return "resolved"
    return ""


def _safe_event(envelope: dict[str, Any]) -> TraceEventOut | None:
    """把一条持久事件投影为无正文的轨迹行。"""
    kind = str(envelope.get("type") or "")
    if not kind:
        return None
    data = envelope.get("data") if isinstance(envelope.get("data"), dict) else {}
    prompt, completion, _total = _usage(data)
    duration = data.get("duration_ms")
    if not isinstance(duration, int | float) or isinstance(duration, bool):
        duration = None
    ts = envelope.get("ts")
    if not isinstance(ts, int | float) or isinstance(ts, bool):
        ts = None
    return TraceEventOut(
        seq=int(envelope.get("seq") or 0),
        type=kind[:80],
        ts=float(ts) if ts is not None else None,
        turn=_turn_of(envelope),
        name=_event_name(kind, data),
        status=_status(kind, data),
        duration_ms=int(duration) if duration is not None else None,
        error_code=_error_code(data),
        prompt_tokens=prompt,
        completion_tokens=completion,
    )


def _load_events(db: Session, session_id: str) -> list[dict[str, Any]]:
    """按 seq 读取最近事件；上限防超大会话拖垮接口。"""
    rows = (
        db.query(AgentEvent.envelope)
        .filter(AgentEvent.session_id == session_id)
        .order_by(AgentEvent.seq.desc())
        .limit(MAX_EVENTS)
        .all()
    )
    # 先取最近窗口，再回到正序，长会话不会只看到最早的事件。
    return [row[0] for row in reversed(rows) if isinstance(row[0], dict)]


def _summaries(envelopes: list[dict[str, Any]]) -> list[TraceTurnOut]:
    """按回合聚合事件数量和用量，返回倒序摘要。"""
    buckets: dict[int, dict[str, Any]] = {}
    for envelope in envelopes:
        turn = _turn_of(envelope)
        if turn is None:
            continue
        bucket = buckets.setdefault(
            turn,
            {
                "started_at": None,
                "finished_at": None,
                "status": "running",
                "event_count": 0,
                "tool_calls": 0,
                "model_attempts": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        )
        kind = str(envelope.get("type") or "")
        data = envelope.get("data") if isinstance(envelope.get("data"), dict) else {}
        ts = envelope.get("ts")
        if isinstance(ts, int | float) and not isinstance(ts, bool):
            if bucket["started_at"] is None:
                bucket["started_at"] = float(ts)
            bucket["finished_at"] = float(ts)
        bucket["event_count"] += 1
        if kind == "tool/call":
            bucket["tool_calls"] += 1
        if kind in {"assistant/attempt_start", "assistant/attempt"}:
            bucket["model_attempts"] += 1
        if kind == "turn/end":
            bucket["status"] = str(data.get("reason") or "finished")[:40]
        elif kind == "runtime/error":
            bucket["status"] = "failed"
        if kind == "assistant/message":
            prompt, completion, total = _usage(data)
            bucket["prompt_tokens"] += prompt
            bucket["completion_tokens"] += completion
            bucket["total_tokens"] += total
    summaries = [
        TraceTurnOut(turn=turn, **values)
        for turn, values in sorted(buckets.items(), reverse=True)
    ]
    return summaries


@router.get("/turns", response_model=list[TraceTurnOut], summary="列出会话历史回合轨迹摘要")
def list_trace_turns(
    session_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TraceTurnOut]:
    """只返回事件元数据与 token 汇总；私有会话仅属主/管理员可见。"""
    require_visible_session(db, session_id, user.id)
    return _summaries(_load_events(db, session_id))[:limit]


@router.get("/turns/{turn}", response_model=TraceTurnDetailOut, summary="读取单个回合的轨迹事件")
def get_trace_turn(
    session_id: str,
    turn: int,
    limit: int = Query(default=MAX_TURN_EVENTS, ge=1, le=MAX_TURN_EVENTS),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TraceTurnDetailOut:
    """事件按 seq 正序返回；不返回正文/工具结果/提示词。"""
    require_visible_session(db, session_id, user.id)
    envelopes = _load_events(db, session_id)
    summaries = {item.turn: item for item in _summaries(envelopes)}
    events = [
        event
        for event in (_safe_event(envelope) for envelope in envelopes)
        if event is not None and event.turn == turn
    ][:limit]
    summary = summaries.get(turn) or TraceTurnOut(turn=turn, event_count=0)
    return TraceTurnDetailOut(turn=turn, summary=summary, events=events)
