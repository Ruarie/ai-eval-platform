"""Token 用量中心（N-10 MVP）。

只聚合已落库 assistant 消息的 ``turn_stats.usage``：
- 按天/模型/会话属主聚合，供容量与预算观察；
- 按模型名单价估算费用；未配置单价的调用明确标记为未计价；
- 不读取消息正文、提示词或工具结果。

预算阈值与告警留到后续批次。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import AuditLog, Message, ModelPrice, User, utcnow
from ..models import Session as AgentSession
from ..schemas import (
    ModelPriceListOut,
    ModelPriceOut,
    ModelPriceUpdateIn,
    UsageModelOut,
    UsageRecentOut,
    UsageSeriesOut,
    UsageSummaryOut,
    UsageUserOut,
)
from ._common import client_ip

router = APIRouter(prefix="/api/usage", tags=["usage"])

MAX_MESSAGES = 5000


def _usage(row: Message) -> tuple[int, int, int]:
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


def _day(value: datetime | None) -> str:
    """统一 YYYY-MM-DD；缺失时间不参与趋势。"""
    return value.date().isoformat() if value else ""


def _cost(prompt: int, completion: int, price: ModelPrice | None) -> float | None:
    """按每百万 token 单价估算；未配置价格返回 None，不用 0 冒充已计价。"""
    if not price:
        return None
    cost = (prompt * float(price.input_per_1m or 0) + completion * float(price.output_per_1m or 0)) / 1_000_000
    return round(cost, 6)


def _price_out(price: ModelPrice) -> ModelPriceOut:
    """单价 ORM 转响应。"""
    return ModelPriceOut(
        model_name=price.model_name,
        input_per_1m=float(price.input_per_1m or 0),
        output_per_1m=float(price.output_per_1m or 0),
        currency=price.currency,
        updated_at=price.updated_at,
    )


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

    rows = (
        db.query(Message)
        .filter(
            Message.role == "assistant",
            Message.created_at >= start_at,
            Message.turn_stats.isnot(None),
        )
        .order_by(Message.created_at.desc())
        .limit(MAX_MESSAGES)
        .all()
    )
    session_ids = {row.session_id for row in rows}
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

    price_map = {row.model_name: row for row in db.query(ModelPrice).all()}
    total_prompt = total_completion = total_tokens = 0
    total_cost = 0.0
    priced_calls = unpriced_calls = 0
    series_map: dict[str, dict[str, int]] = defaultdict(
        lambda: {"calls": 0, "prompt": 0, "completion": 0, "total": 0}
    )
    model_map: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "calls": 0,
            "sessions": set(),
            "prompt": 0,
            "completion": 0,
            "total": 0,
            "cost": 0.0,
            "priced": 0,
            "unpriced": 0,
        }
    )
    user_map: dict[str, dict[str, int]] = defaultdict(lambda: {"calls": 0, "total": 0})
    recent: list[UsageRecentOut] = []

    for row in rows:
        prompt, completion, total = _usage(row)
        if not total and not prompt and not completion:
            continue
        total_prompt += prompt
        total_completion += completion
        total_tokens += total
        model_name = (row.model_name or "").strip() or "未记录"
        price = price_map.get(model_name)
        cost = _cost(prompt, completion, price)
        if cost is None:
            unpriced_calls += 1
        else:
            total_cost += cost
            priced_calls += 1
        day = _day(row.created_at)
        if day:
            bucket = series_map[day]
            bucket["calls"] += 1
            bucket["prompt"] += prompt
            bucket["completion"] += completion
            bucket["total"] += total

        profile_id = row.profile_id or ""
        model_bucket = model_map[(profile_id, model_name)]
        model_bucket["calls"] += 1
        model_bucket["sessions"].add(row.session_id)
        model_bucket["prompt"] += prompt
        model_bucket["completion"] += completion
        model_bucket["total"] += total
        if cost is None:
            model_bucket["unpriced"] += 1
        else:
            model_bucket["priced"] += 1
            model_bucket["cost"] += cost

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
                    cost_usd=cost,
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
            priced_calls=value["priced"],
            unpriced_calls=value["unpriced"],
            cost_usd=round(value["cost"], 6) if value["priced"] else None,
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
        calls=sum(1 for row in rows if sum(_usage(row)) > 0),
        sessions=len(session_ids),
        users=len({sid for sid in session_ids if session_meta.get(sid, ("", ""))[1]}),
        prompt_tokens=total_prompt,
        completion_tokens=total_completion,
        total_tokens=total_tokens,
        priced_calls=priced_calls,
        unpriced_calls=unpriced_calls,
        total_cost_usd=round(total_cost, 6) if priced_calls else None,
        series=series,
        by_model=by_model,
        by_user=by_user,
        recent=recent,
    )


@router.get("/prices", response_model=ModelPriceListOut, summary="读取模型单价")
def list_model_prices(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ModelPriceListOut:
    """返回已配置单价的模型；未配置的模型不出现在列表中。"""
    rows = db.query(ModelPrice).order_by(ModelPrice.model_name.asc()).all()
    return ModelPriceListOut(items=[_price_out(row) for row in rows])


@router.put("/prices", response_model=ModelPriceListOut, summary="批量保存模型单价")
def save_model_prices(
    payload: ModelPriceUpdateIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ModelPriceListOut:
    """按模型名 upsert；未列出的模型保持不变，只记录变更数量。"""
    changed: list[str] = []
    for item in payload.prices:
        model_name = item.model_name.strip()
        if not model_name:
            continue
        row = db.query(ModelPrice).filter(ModelPrice.model_name == model_name).first()
        if not row:
            row = ModelPrice(model_name=model_name)
            db.add(row)
        row.input_per_1m = item.input_per_1m
        row.output_per_1m = item.output_per_1m
        row.currency = item.currency
        row.updated_by = user.id
        row.updated_at = utcnow()
        changed.append(model_name)
    if changed:
        db.add(
            AuditLog(
                user_id=user.id,
                action="model_price_update",
                target_type="model_price",
                target_id="bulk",
                detail={"models": changed[:200]},
                ip=client_ip(request),
            )
        )
    db.commit()
    rows = db.query(ModelPrice).order_by(ModelPrice.model_name.asc()).all()
    return ModelPriceListOut(items=[_price_out(row) for row in rows])
