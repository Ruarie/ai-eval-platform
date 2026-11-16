"""页面用例生成、对比和评审的 Worker 执行器。

API 只把裁剪后的来源写入 ``case_ai_jobs``。这里领取后调用模型，
生成和对比不落用例，评审才写 ``case_sets.checks`` 与评审历史。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from shared.case_preview import PreviewError, generate_candidates, run_compare
from shared.casegen import MAX_COUNT, build_review_prompt, parse_review
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import CaseAiJob, CaseItem, CaseReviewRun, CaseSet, ProtocolProfile, Setting, utcnow
from .profile_env import profile_connection, read_profile_env
from .protocol import ProtocolCallError, call_protocol

logger = logging.getLogger("worker.case_ai")

CASE_AI_LEASE_SECONDS = 420
REVIEW_TIMEOUT_S = 150.0
REVIEW_MAX_TOKENS = 4096
TRUNCATION_RETRY_CEILING = 32768


def claim_next_case_ai_job(db: Session) -> str | None:
    """领取最早的排队任务。调用方负责把这次领取算进并发上限。"""
    job = (
        db.query(CaseAiJob)
        .filter(CaseAiJob.status == "queued")
        .order_by(CaseAiJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .first()
    )
    if job is None:
        return None
    now = datetime.now(UTC)
    job.status = "running"
    job.started_at = now
    job.claim_expires_at = now + timedelta(seconds=CASE_AI_LEASE_SECONDS)
    db.commit()
    return job.id


def recover_expired_case_ai_jobs(db: Session) -> int:
    """租约过期的运行中任务记为失败，不自动再调一次模型。"""
    now = datetime.now(UTC)
    rows = (
        db.query(CaseAiJob)
        .filter(CaseAiJob.status == "running")
        .with_for_update(skip_locked=True)
        .all()
    )
    failed = 0
    for job in rows:
        expires = job.claim_expires_at
        if expires is not None and expires > now:
            continue
        job.status = "failed"
        job.error_code = "TIMEOUT"
        job.error_message = "用例 AI 任务失联超时"
        job.finished_at = now
        job.claim_expires_at = None
        failed += 1
    if failed:
        db.commit()
    return failed


def _lock_running(db: Session, job_id: str) -> CaseAiJob | None:
    job = (
        db.query(CaseAiJob)
        .filter(CaseAiJob.id == job_id, CaseAiJob.status == "running")
        .with_for_update()
        .first()
    )
    return job


def _fail(db: Session, job_id: str, code: str, message: str) -> None:
    job = _lock_running(db, job_id)
    if job is None:
        return
    job.status = "failed"
    job.error_code = code
    job.error_message = message[:500]
    job.finished_at = utcnow()
    job.claim_expires_at = None
    db.commit()


def _succeed(db: Session, job_id: str, result: dict[str, Any]) -> None:
    job = _lock_running(db, job_id)
    if job is None:
        return
    job.status = "succeeded"
    job.result = result
    job.finished_at = utcnow()
    job.claim_expires_at = None
    db.commit()


def _agent_profile(db: Session, profile_id: str | None = None) -> ProtocolProfile:
    if not profile_id:
        row = db.query(Setting).filter(Setting.key == "agent_profile_id").first()
        profile_id = row.value if row and isinstance(row.value, str) else None
    if not profile_id:
        raise PreviewError("VALIDATION", "尚未配置 Agent 协议档，无法调用 AI 生成")
    profile = db.query(ProtocolProfile).filter(ProtocolProfile.id == profile_id).first()
    if profile is None:
        raise PreviewError("VALIDATION", "Agent 协议档不存在")
    if "agent" not in (profile.usages or []):
        raise PreviewError("VALIDATION", f"协议档「{profile.name}」未启用 agent 用途")
    return profile


def _snapshot(profile: ProtocolProfile) -> SimpleNamespace:
    return SimpleNamespace(
        id=profile.id,
        name=profile.name,
        model=profile.model,
        protocol=profile.protocol,
        anthropic_version=profile.anthropic_version,
    )


def _invoke(profile: Any, system: str, user: str, *, temperature: float, max_tokens: int, timeout_s: float) -> Any:
    """按协议档调用模型。输出被截断时抬一次预算，仍截断则报预算不足。"""
    base_url, model, api_key = profile_connection(profile, allow_global_alias=True)
    if not base_url or not model or not api_key:
        raise PreviewError("VALIDATION", f"Agent 协议档「{profile.name}」未配置完整")
    full_url = read_profile_env(profile.id).full_url

    def once(budget: int) -> Any:
        return call_protocol(
            protocol=profile.protocol,
            base_url=base_url,
            full_url=full_url,
            model=model,
            api_key=api_key,
            messages=[{"role": "user", "content": user}],
            system=system,
            temperature=temperature,
            max_tokens=budget,
            anthropic_version=getattr(profile, "anthropic_version", None),
            timeout_s=timeout_s,
        )

    result = once(max_tokens)
    if getattr(result, "finish_reason", None) == "length":
        retry_budget = min(TRUNCATION_RETRY_CEILING, max_tokens * 2)
        if retry_budget > max_tokens:
            result = once(retry_budget)
            max_tokens = retry_budget
    if getattr(result, "finish_reason", None) == "length":
        raise PreviewError(
            "BUDGET_EXCEEDED",
            f"模型输出被长度上限截断（max_tokens={max_tokens}），请减少生成条数或拆分需求后重试",
        )
    return result


def _run_generate(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    profile = _snapshot(_agent_profile(db))
    db.commit()
    result = generate_candidates(
        str(payload.get("source_text") or ""),
        int(payload.get("max_count") or 45),
        dict(payload.get("strategy_weights") or {}),
        lambda system, user, **kwargs: _invoke(profile, system, user, **kwargs),
    )
    result["source_truncated"] = bool(payload.get("source_truncated"))
    return result


def _run_compare(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    profile_ids = payload.get("profile_ids") or []
    if not isinstance(profile_ids, list) or len(profile_ids) != 2:
        raise PreviewError("VALIDATION", "对比需要两个协议档")
    snapshots = [_snapshot(_agent_profile(db, profile_id)) for profile_id in profile_ids]
    db.commit()
    result = run_compare(
        snapshots,
        str(payload.get("source_text") or ""),
        int(payload.get("max_count") or 45),
        dict(payload.get("strategy_weights") or {}),
        lambda profile, system, user, **kwargs: _invoke(profile, system, user, **kwargs),
    )
    result["source_truncated"] = bool(payload.get("source_truncated"))
    return result


def _run_review(db: Session, payload: dict[str, Any], user_id: str) -> dict[str, Any]:
    case_set_id = str(payload.get("case_set_id") or "")
    case_set = db.query(CaseSet).filter(CaseSet.id == case_set_id).first()
    if case_set is None:
        raise PreviewError("NOT_FOUND", "用例集不存在")
    items = (
        db.query(CaseItem)
        .filter(CaseItem.case_set_id == case_set_id)
        .order_by(CaseItem.sort_order)
        .all()
    )
    if not items:
        raise PreviewError("VALIDATION", "用例集为空，没有可评审的内容")
    source_text = str(payload.get("source_text") or "").strip()
    source_truncated = bool(payload.get("source_truncated"))
    if not source_text:
        source_text = "（未提供需求文档：只评审用例自身的可执行性、重复与策略分布）"
    cases = [
        {
            "module": item.module,
            "name": item.name,
            "strategy": item.strategy,
            "steps": item.steps,
            "expected": item.expected,
        }
        for item in items[:MAX_COUNT]
    ]
    profile = _snapshot(_agent_profile(db))
    db.commit()
    system, user_prompt = build_review_prompt(source_text, cases)
    result = _invoke(
        profile, system, user_prompt,
        temperature=0.1, max_tokens=REVIEW_MAX_TOKENS, timeout_s=REVIEW_TIMEOUT_S,
    )
    try:
        review = parse_review(result.text)
    except (ValueError, TypeError) as exc:
        raise PreviewError("UPSTREAM", "评审输出无法解析，请重试") from exc
    review.update({
        "reviewed_at": utcnow().isoformat(),
        "case_count": len(cases),
        "source_truncated": source_truncated,
    })
    case_set = db.query(CaseSet).filter(CaseSet.id == case_set_id).first()
    if case_set is None:
        raise PreviewError("NOT_FOUND", "用例集不存在")
    checks = [
        check for check in (case_set.checks or [])
        if not (isinstance(check, dict) and check.get("kind") == "ai_review")
    ]
    checks.append({"kind": "ai_review", **review})
    case_set.checks = checks
    db.add(CaseReviewRun(
        case_set_id=case_set.id,
        score=int(review.get("score") or 0),
        verdict=str(review.get("verdict") or ""),
        summary=str(review.get("summary") or ""),
        dimensions=review.get("dimensions") or {},
        issues=review.get("issues") or [],
        case_count=len(cases),
        source_truncated=source_truncated,
        profile_id=profile.id,
        created_by=user_id,
    ))
    db.commit()
    return review


def run_case_ai_job(job_id: str) -> None:
    """执行一条已领取的用例 AI 任务。失败只写错误码和固定文案。"""
    db = SessionLocal()
    try:
        job = db.query(CaseAiJob).filter(CaseAiJob.id == job_id).first()
        if job is None or job.status != "running":
            return
        payload = dict(job.payload or {})
        kind = job.kind
        user_id = job.user_id
        db.commit()
        if kind == "generate":
            result = _run_generate(db, payload)
        elif kind == "compare":
            result = _run_compare(db, payload)
        elif kind == "review":
            result = _run_review(db, payload, user_id)
        else:
            raise PreviewError("VALIDATION", "未知的用例 AI 任务")
        _succeed(db, job_id, result)
    except PreviewError as exc:
        db.rollback()
        _fail(db, job_id, exc.code, exc.message)
    except ProtocolCallError as exc:
        db.rollback()
        _fail(db, job_id, exc.code, exc.message)
    except Exception:
        logger.exception("case ai job %s failed", job_id)
        db.rollback()
        _fail(db, job_id, "INTERNAL", "AI 生成调用失败，请稍后重试")
    finally:
        db.close()
