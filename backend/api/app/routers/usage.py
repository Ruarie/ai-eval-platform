"""Token 用量中心（N-10 MVP）。

用量依据是每次模型回复里上游返回的 token 数字：
- 已写入 ``messages.turn_stats.usage`` 的 assistant 消息直接聚合；
- 当前 Agent 回合把同一份数字放在 ``assistant/message`` 事实的 ``data.usage``。
  历史消息若还没带 ``turn_stats``，从事实里只抽出 usage，不读正文；
- 同一条事实已经投影进消息时只计一次；
- 不做费用估算（当前没有可信的逐模型单价）。
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import AgentEvent, Message, User
from ..models import Session as AgentSession
from ..schemas import (
    UsageModelOut,
    UsageRecentOut,
    UsageSeriesOut,
    UsageSummaryOut,
    UsageUserOut,
)
from ..usage_facts import assistant_meter

router = APIRouter(prefix="/api/usage", tags=["usage"])

MAX_MESSAGES = 5000


def _usage(row: Any) -> tuple[int, int, int]:
    """从 turn_stats.usage 提取 token；字段缺失时按 prompt+completion 兜底。"""
    stats = row.turn_stats if isinstance(row.turn_stats, dict) else {}
    usage = stats.get("usage") if isinstance(stats.get("usage"), dict) else {}
    prompt = usage.get("prompt_tokens", usage.get("input_tokens", 0))
    completion = usage.get("completion_tokens", usage.get("output_tokens", 0))
    total = usage.get("total_tokens", 0)
    prompt = int(prompt) if isinstance(prompt, int | float) and not isinstance(prompt, bool) else 0
    completion = int(completion) if isinstance(completion, int | float) and not isinstance(completion, bool) else 0
    total = int(total) if isinstance(total, int | float) and not isinstance(total, bool) else 0
    if total <= 0:
        total = prompt + completion
    return max(0, prompt), max(0, completion), max(0, total)


def _parse_usage(value: Any) -> dict[str, Any]:
    """把 JSON 文本或对象收成 usage 字典；坏数据当成没有用量。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _day(value: datetime | None) -> str:
    """统一 YYYY-MM-DD；缺失时间不参与趋势。"""
    return value.date().isoformat() if value else ""


@router.get("/summary", response_model=UsageSummaryOut, summary="Token 用量汇总")
def usage_summary(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> UsageSummaryOut:
    """按指定时间窗聚合 assistant 消息的 token 用量。"""
    now = datetime.now(UTC)
    start_day = (now - timedelta(days=days - 1)).date()
    start_at = datetime.combine(start_day, datetime.min.time(), tzinfo=UTC)

    base_query = db.query(Message).filter(
        Message.role == "assistant",
        Message.created_at >= start_at,
        Message.turn_stats.isnot(None),
    )
    # 先取匹配总数：超过聚合上限时必须告知前端只统计了最近一段，
    # 不能让截断后的样本看起来像全量用量。
    # 只数主键。Query.count() 会把 content 放进子查询，计数本身就把正文读出来。
    matched = base_query.with_entities(func.count(Message.id)).scalar() or 0
    # 聚合只用用量与归属字段。content / attachments 可能很大，不能随 5000 行一起读入。
    rows = (
        base_query.with_entities(
            Message.session_id,
            Message.created_at,
            Message.turn_stats,
            Message.model_name,
            Message.profile_id,
            Message.source_id,
        )
        .order_by(Message.created_at.desc())
        .limit(MAX_MESSAGES)
        .all()
    )
    covered = {row.source_id for row in rows if row.source_id}
    event_query = db.query(AgentEvent).filter(
        AgentEvent.type == "assistant/message",
        AgentEvent.created_at >= start_at,
    )
    event_matched = event_query.with_entities(func.count(AgentEvent.id)).scalar() or 0
    # 只抽出 usage / 模型名 / 事件号。事实正文留在 envelope 里，不进这次查询。
    event_id = AgentEvent.envelope["event_id"].as_string()
    usage_text = AgentEvent.envelope["data"]["usage"].as_string()
    model_text = AgentEvent.envelope["data"]["message"]["source"]["model"].as_string()
    event_rows = (
        event_query.with_entities(
            AgentEvent.session_id,
            AgentEvent.created_at,
            event_id,
            usage_text,
            model_text,
        )
        .order_by(AgentEvent.created_at.desc())
        .limit(MAX_MESSAGES)
        .all()
    )
    facts: list[Any] = list(rows)
    for session_id, created_at, event_key, raw_usage, model_name in event_rows:
        if event_key and event_key in covered:
            continue
        meter = assistant_meter({"usage": _parse_usage(raw_usage), "message": {"source": {"model": model_name}}})
        if not meter["turn_stats"]:
            continue
        facts.append(
            SimpleNamespace(
                session_id=session_id,
                created_at=created_at,
                turn_stats=meter["turn_stats"],
                model_name=meter["model_name"],
                profile_id=None,
            )
        )
    facts.sort(key=lambda item: item.created_at.timestamp() if item.created_at else 0, reverse=True)
    truncated = matched > MAX_MESSAGES or event_matched > MAX_MESSAGES
    session_ids = {row.session_id for row in facts}
    sessions = (
        db.query(AgentSession.id, AgentSession.title, AgentSession.user_id)
        .filter(AgentSession.id.in_(session_ids))
        .all()
        if session_ids
        else []
    )
    session_meta = {row[0]: (row[1], row[2]) for row in sessions}
    user_ids = {row[2] for row in sessions if row[2]}
    users = (
        db.query(User.id, User.username).filter(User.id.in_(user_ids)).all() if user_ids else []
    )
    user_names = {row[0]: row[1] for row in users}

    total_prompt = total_completion = total_tokens = 0
    series_map: dict[str, dict[str, int]] = defaultdict(
        lambda: {"calls": 0, "prompt": 0, "completion": 0, "total": 0}
    )
    model_map: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"calls": 0, "sessions": set(), "prompt": 0, "completion": 0, "total": 0}
    )
    user_map: dict[str, dict[str, int]] = defaultdict(lambda: {"calls": 0, "total": 0})
    recent: list[UsageRecentOut] = []
    calls = 0

    for row in facts:
        prompt, completion, total = _usage(row)
        if not total and not prompt and not completion:
            continue
        calls += 1
        total_prompt += prompt
        total_completion += completion
        total_tokens += total
        day = _day(row.created_at)
        if day:
            bucket = series_map[day]
            bucket["calls"] += 1
            bucket["prompt"] += prompt
            bucket["completion"] += completion
            bucket["total"] += total

        model_name = (row.model_name or "").strip() or "未记录"
        profile_id = row.profile_id or ""
        model_bucket = model_map[(profile_id, model_name)]
        model_bucket["calls"] += 1
        model_bucket["sessions"].add(row.session_id)
        model_bucket["prompt"] += prompt
        model_bucket["completion"] += completion
        model_bucket["total"] += total

        owner_id = session_meta.get(row.session_id, ("", ""))[1] or ""
        owner_name = user_names.get(owner_id, "未记录") if owner_id else "未记录"
        user_bucket = user_map[owner_id or "unknown"]
        user_bucket["calls"] += 1
        user_bucket["total"] += total
        user_bucket["username"] = owner_name

        if len(recent) < 50:
            recent.append(
                UsageRecentOut(
                    created_at=row.created_at,
                    session_id=row.session_id,
                    session_title=session_meta.get(row.session_id, ("", ""))[0] or "未命名会话",
                    model_name=model_name,
                    prompt_tokens=prompt,
                    completion_tokens=completion,
                    total_tokens=total,
                )
            )

    series: list[UsageSeriesOut] = []
    for offset in range(days):
        day = (start_day + timedelta(days=offset)).isoformat()
        bucket = series_map.get(day, {"calls": 0, "prompt": 0, "completion": 0, "total": 0})
        series.append(
            UsageSeriesOut(
                day=day,
                calls=int(bucket["calls"]),
                prompt_tokens=int(bucket["prompt"]),
                completion_tokens=int(bucket["completion"]),
                total_tokens=int(bucket["total"]),
            )
        )

    by_model = [
        UsageModelOut(
            profile_id=key[0],
            model_name=key[1],
            calls=value["calls"],
            sessions=len(value["sessions"]),
            prompt_tokens=value["prompt"],
            completion_tokens=value["completion"],
            total_tokens=value["total"],
        )
        for key, value in model_map.items()
    ]
    by_model.sort(key=lambda item: (item.total_tokens, item.calls), reverse=True)

    by_user = []
    for owner_id, value in user_map.items():
        by_user.append(
            UsageUserOut(
                user_id=owner_id,
                username=str(value.get("username", "未记录")),
                calls=int(value["calls"]),
                total_tokens=int(value["total"]),
            )
        )
    by_user.sort(key=lambda item: item.total_tokens, reverse=True)

    return UsageSummaryOut(
        days=days,
        generated_at=now,
        calls=calls,
        sessions=len(session_ids),
        users=len({sid for sid in session_ids if session_meta.get(sid, ("", ""))[1]}),
        prompt_tokens=total_prompt,
        completion_tokens=total_completion,
        total_tokens=total_tokens,
        truncated=truncated,
        scanned_messages=len(facts),
        sample_limit=MAX_MESSAGES,
        series=series,
        by_model=by_model,
        by_user=by_user,
        recent=recent,
    )
