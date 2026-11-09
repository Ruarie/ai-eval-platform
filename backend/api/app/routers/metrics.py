"""用例生成质量看板（N-03 MVP）。

只读聚合 ``tasks`` / ``case_sets`` / ``case_review_runs`` / ``case_items``：
- 运行数、生成数、确认数、采纳率、成功率；
- 按天趋势、按模型/协议档、按状态、按模块分布；
- 最近运行明细与最新 AI 评审分数。

统计口径只使用已落库事实；没有 AI 评分或模型名的运行明确留空，不用 0 冒充。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import CaseItem, CaseReviewRun, CaseSet, Task, User
from ..schemas import (
    CasegenMetricsOut,
    CasegenModelOut,
    CasegenModuleOut,
    CasegenRunOut,
    CasegenSeriesOut,
    CasegenStatusOut,
)

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

_STATUS_ORDER = ["queued", "running", "awaiting_case_confirm", "succeeded", "failed", "cancelled"]
_TERMINAL_SUCCESS = {"succeeded"}
_TERMINAL_FAILED = {"failed"}
_TERMINAL_CANCELLED = {"cancelled"}


def _as_dict(value: object) -> dict:
    """任务 config/result 可能为 None 或历史脏数据，统一按空对象处理。"""
    return value if isinstance(value, dict) else {}


def _rate(numerator: int, denominator: int) -> float:
    """比例统一保留四位小数；分母为 0 时返回 0。"""
    return round(numerator / denominator, 4) if denominator else 0.0


def _duration_ms(started: datetime | None, finished: datetime | None) -> int | None:
    """仅使用服务端记录的时间；缺失或类型不一致时不推算。"""
    if not started or not finished:
        return None
    try:
        return max(0, int((finished - started).total_seconds() * 1000))
    except TypeError:
        return None


def _day_key(value: datetime | None) -> str:
    """把时间统一成 YYYY-MM-DD；无时间返回空串。"""
    if not value:
        return ""
    return value.date().isoformat()


@router.get("/casegen", response_model=CasegenMetricsOut, summary="用例生成质量看板")
def casegen_metrics(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> CasegenMetricsOut:
    """聚合指定时间窗内的用例生成运行与质量指标。"""
    now = datetime.now(UTC)
    start_day = (now - timedelta(days=days - 1)).date()
    start_at = datetime.combine(start_day, datetime.min.time(), tzinfo=UTC)

    tasks = (
        db.query(Task)
        .filter(Task.kind == "testcase", Task.created_at >= start_at)
        .order_by(Task.created_at.desc())
        .limit(1000)
        .all()
    )
    task_ids = [task.id for task in tasks]
    sets = (
        db.query(CaseSet).filter(CaseSet.task_id.in_(task_ids)).all() if task_ids else []
    )
    set_by_task = {case_set.task_id: case_set for case_set in sets if case_set.task_id}
    set_ids = [case_set.id for case_set in sets]

    # 每个用例集只取最新一次 AI 评审；历史仍保留在 case_review_runs。
    latest_runs: dict[str, CaseReviewRun] = {}
    if set_ids:
        for run in (
            db.query(CaseReviewRun)
            .filter(CaseReviewRun.case_set_id.in_(set_ids))
            .order_by(CaseReviewRun.created_at.desc())
            .all()
        ):
            latest_runs.setdefault(run.case_set_id, run)

    modules: list[CasegenModuleOut] = []
    if set_ids:
        rows = (
            db.query(CaseItem.module, func.count(CaseItem.id))
            .filter(CaseItem.case_set_id.in_(set_ids))
            .group_by(CaseItem.module)
            .order_by(func.count(CaseItem.id).desc())
            .limit(20)
            .all()
        )
        modules = [CasegenModuleOut(module=module or "未分模块", case_count=count) for module, count in rows]

    items: list[CasegenRunOut] = []
    model_stats: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"runs": 0, "generated": 0, "confirmed": 0, "scores": []}
    )
    status_counts: dict[str, int] = defaultdict(int)
    series_map: dict[str, dict] = defaultdict(lambda: {"runs": 0, "generated": 0, "confirmed": 0})

    total_generated = 0
    total_confirmed = 0
    ai_scores: list[int] = []
    review_approved = 0
    succeeded = failed = cancelled = awaiting = 0

    for task in tasks:
        config = _as_dict(task.config)
        result = _as_dict(task.result)
        case_set = set_by_task.get(task.id)
        latest = latest_runs.get(case_set.id) if case_set else None

        target = int(config.get("max_count") or 0)
        generated = int(result.get("generated_count") or (case_set.generated_count if case_set else 0) or 0)
        confirmed = int(case_set.confirmed_count if case_set else 0)
        score = latest.score if latest else None
        model_name = str(result.get("model_name") or config.get("model_name") or "").strip()
        profile_id = str(result.get("profile_id") or config.get("profile_id") or "").strip()
        profile_name = str(result.get("profile_name") or "").strip()
        adoption = _rate(confirmed, generated)

        status_counts[task.status] += 1
        if task.status in _TERMINAL_SUCCESS:
            succeeded += 1
        elif task.status in _TERMINAL_FAILED:
            failed += 1
        elif task.status in _TERMINAL_CANCELLED:
            cancelled += 1
        elif task.status == "awaiting_case_confirm":
            awaiting += 1

        total_generated += generated
        total_confirmed += confirmed
        if score is not None:
            ai_scores.append(int(score))
        if case_set and case_set.review_state == "approved":
            review_approved += 1

        day = _day_key(task.created_at)
        if day:
            series_map[day]["runs"] += 1
            series_map[day]["generated"] += generated
            series_map[day]["confirmed"] += confirmed

        key = (profile_id, model_name or "未记录")
        bucket = model_stats[key]
        bucket["runs"] += 1
        bucket["generated"] += generated
        bucket["confirmed"] += confirmed
        if score is not None:
            bucket["scores"].append(int(score))

        items.append(
            CasegenRunOut(
                task_id=task.id,
                case_set_id=case_set.id if case_set else None,
                name=case_set.name if case_set else "",
                status=task.status,
                model_name=model_name,
                profile_id=profile_id,
                profile_name=profile_name,
                target_count=target,
                generated_count=generated,
                confirmed_count=confirmed,
                adoption_rate=adoption,
                ai_score=score,
                ai_verdict=latest.verdict if latest else "",
                review_state=case_set.review_state if case_set else "",
                error_code=str(result.get("error_code") or ""),
                created_at=task.created_at,
                started_at=task.started_at,
                finished_at=task.finished_at,
                duration_ms=_duration_ms(task.started_at, task.finished_at),
            )
        )

    series: list[CasegenSeriesOut] = []
    for offset in range(days):
        day = (start_day + timedelta(days=offset)).isoformat()
        row = series_map.get(day, {"runs": 0, "generated": 0, "confirmed": 0})
        series.append(
            CasegenSeriesOut(
                day=day,
                runs=int(row["runs"]),
                generated=int(row["generated"]),
                confirmed=int(row["confirmed"]),
                adoption_rate=_rate(int(row["confirmed"]), int(row["generated"])),
            )
        )

    by_model = [
        CasegenModelOut(
            profile_id=key[0],
            model_name=key[1],
            runs=value["runs"],
            generated=value["generated"],
            confirmed=value["confirmed"],
            adoption_rate=_rate(value["confirmed"], value["generated"]),
            avg_ai_score=round(sum(value["scores"]) / len(value["scores"]), 1)
            if value["scores"]
            else None,
        )
        for key, value in model_stats.items()
    ]
    by_model.sort(key=lambda item: (item.runs, item.generated), reverse=True)

    by_status = [
        CasegenStatusOut(status=status, count=status_counts.get(status, 0))
        for status in _STATUS_ORDER
        if status_counts.get(status, 0)
    ]

    return CasegenMetricsOut(
        days=days,
        generated_at=now,
        total_runs=len(tasks),
        succeeded_runs=succeeded,
        failed_runs=failed,
        cancelled_runs=cancelled,
        awaiting_runs=awaiting,
        success_rate=_rate(succeeded, len(tasks)),
        total_generated=total_generated,
        total_confirmed=total_confirmed,
        adoption_rate=_rate(total_confirmed, total_generated),
        ai_scored_runs=len(ai_scores),
        avg_ai_score=round(sum(ai_scores) / len(ai_scores), 1) if ai_scores else None,
        review_approved=review_approved,
        series=series,
        by_model=by_model,
        by_status=by_status,
        modules=modules,
        recent=items[:50],
    )
