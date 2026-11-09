"""用例评审工作流与版本历史路由（N-02，API V2.53）。

职责：
- 人工评审请求、结论与评论；
- AI 评审历史查询（写入由 ``/ai-review`` 完成）；
- 用例集版本快照、字段级 diff 与回滚为新草稿。

权限沿用全员同权：任何正常成员可发起/评审/评论；已确认用例集只读，
不再接受新的评审请求或版本写入。所有写操作落 AuditLog。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi import Request as FastApiRequest
from shared.case_review import diff_snapshots
from sqlalchemy.orm import Session

from ..case_review_service import create_version, user_names
from ..db import get_db
from ..deps import get_current_user
from ..errors import AppError, ErrorCode
from ..models import (
    AuditLog,
    CaseItem,
    CaseReviewComment,
    CaseReviewRequest,
    CaseReviewRun,
    CaseSet,
    CaseSetVersion,
    User,
    utcnow,
)
from ..schemas import (
    CaseReviewCommentIn,
    CaseReviewCommentOut,
    CaseReviewDecisionIn,
    CaseReviewRequestIn,
    CaseReviewRequestOut,
    CaseReviewRunOut,
    CaseReviewWorkspaceOut,
    CaseSetVersionDetailOut,
    CaseSetVersionOut,
    CaseVersionCreateIn,
    CaseVersionDiffOut,
    CaseVersionRestoreOut,
)
from ._common import client_ip

router = APIRouter(prefix="/api/case-sets", tags=["case-review"])


def _get_set(db: Session, set_id: str, *, lock: bool = False) -> CaseSet:
    """读取用例集；锁定时用于版本号与评审状态串行化。"""
    query = db.query(CaseSet).filter(CaseSet.id == set_id)
    if lock:
        query = query.with_for_update()
    case_set = query.first()
    if not case_set:
        raise AppError(ErrorCode.NOT_FOUND, "用例集不存在")
    return case_set


def _parse_due(value: Any) -> datetime | None:
    """把前端 ISO 字符串/日期归一为带 UTC 时区的时间；空值返回 None。"""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AppError(ErrorCode.VALIDATION, "评审截止时间格式不正确") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _require_active_user(db: Session, user_id: str) -> User:
    """评审负责人必须是正常成员，不能指向已停用账号。"""
    user = db.get(User, user_id)
    if not user or user.disabled:
        raise AppError(ErrorCode.VALIDATION, "评审负责人不存在或已停用")
    return user


def _request_out(request: CaseReviewRequest, names: dict[str, str]) -> CaseReviewRequestOut:
    """评审请求响应；负责人/发起人名称由批量查询注入。"""
    return CaseReviewRequestOut(
        id=request.id,
        status=request.status,
        note=request.note or "",
        decision_note=request.decision_note or "",
        assignee_id=request.assignee_id,
        assignee_name=names.get(request.assignee_id or "", ""),
        due_at=request.due_at,
        created_by=request.created_by,
        created_by_name=names.get(request.created_by or "", ""),
        created_at=request.created_at,
        decided_at=request.decided_at,
    )


def _comment_out(comment: CaseReviewComment, names: dict[str, str]) -> CaseReviewCommentOut:
    """评论响应。"""
    return CaseReviewCommentOut(
        id=comment.id,
        case_item_id=comment.case_item_id,
        author_id=comment.author_id,
        author_name=names.get(comment.author_id or "", ""),
        body=comment.body,
        created_at=comment.created_at,
    )


def _run_out(run: CaseReviewRun) -> CaseReviewRunOut:
    """AI 评审历史响应。"""
    return CaseReviewRunOut(
        id=run.id,
        score=run.score,
        verdict=run.verdict,
        summary=run.summary or "",
        dimensions=run.dimensions or {},
        issues=run.issues or [],
        case_count=run.case_count,
        source_truncated=run.source_truncated,
        created_at=run.created_at,
    )


def _version_out(version: CaseSetVersion, names: dict[str, str]) -> CaseSetVersionOut:
    """版本元信息响应。"""
    return CaseSetVersionOut(
        id=version.id,
        version=version.version,
        reason=version.reason or "",
        case_count=version.case_count,
        created_by=version.created_by,
        created_by_name=names.get(version.created_by or "", ""),
        created_at=version.created_at,
    )


def _workspace(db: Session, case_set: CaseSet) -> CaseReviewWorkspaceOut:
    """聚合评审工作台：当前请求、评论、AI 历史与版本列表。"""
    latest = (
        db.query(CaseReviewRequest)
        .filter(CaseReviewRequest.case_set_id == case_set.id)
        .order_by(CaseReviewRequest.created_at.desc())
        .first()
    )
    active = (
        db.query(CaseReviewRequest)
        .filter(
            CaseReviewRequest.case_set_id == case_set.id,
            CaseReviewRequest.status == "pending",
        )
        .order_by(CaseReviewRequest.created_at.desc())
        .first()
    )
    comments = (
        db.query(CaseReviewComment)
        .filter(CaseReviewComment.case_set_id == case_set.id)
        .order_by(CaseReviewComment.created_at.desc())
        .limit(200)
        .all()
    )
    runs = (
        db.query(CaseReviewRun)
        .filter(CaseReviewRun.case_set_id == case_set.id)
        .order_by(CaseReviewRun.created_at.desc())
        .limit(20)
        .all()
    )
    versions = (
        db.query(CaseSetVersion)
        .filter(CaseSetVersion.case_set_id == case_set.id)
        .order_by(CaseSetVersion.version.desc())
        .limit(50)
        .all()
    )
    names = user_names(
        db,
        [
            case_set.review_assignee_id,
            latest.assignee_id if latest else None,
            latest.created_by if latest else None,
            active.assignee_id if active else None,
            active.created_by if active else None,
            *(comment.author_id for comment in comments),
            *(version.created_by for version in versions),
        ],
    )
    return CaseReviewWorkspaceOut(
        case_set_id=case_set.id,
        review_state=case_set.review_state or "draft",
        review_assignee_id=case_set.review_assignee_id,
        review_assignee_name=names.get(case_set.review_assignee_id or "", ""),
        active_request=_request_out(active, names) if active else None,
        latest_request=_request_out(latest, names) if latest else None,
        comments=[_comment_out(comment, names) for comment in comments],
        ai_runs=[_run_out(run) for run in runs],
        versions=[_version_out(version, names) for version in versions],
    )


@router.get("/{set_id}/review", response_model=CaseReviewWorkspaceOut)
def get_review_workspace(
    set_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """读取评审工作台；已确认/已废弃用例集也允许查看历史。"""
    return _workspace(db, _get_set(db, set_id))


@router.post("/{set_id}/review-requests", response_model=CaseReviewWorkspaceOut)
def create_review_request(
    set_id: str,
    body: CaseReviewRequestIn,
    request: FastApiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """发起人工评审；同一用例集同时只允许一个 pending 请求。"""
    case_set = _get_set(db, set_id, lock=True)
    if case_set.status != "generated":
        raise AppError(ErrorCode.VALIDATION, "只有草稿用例集可以发起评审")
    active = (
        db.query(CaseReviewRequest)
        .filter(
            CaseReviewRequest.case_set_id == case_set.id,
            CaseReviewRequest.status == "pending",
        )
        .first()
    )
    if active:
        raise AppError(ErrorCode.CONCURRENCY, "已有进行中的评审，请先完成或关闭")
    assignee_id = (body.assignee_id or user.id).strip()
    _require_active_user(db, assignee_id)
    review = CaseReviewRequest(
        case_set_id=case_set.id,
        assignee_id=assignee_id,
        status="pending",
        note=(body.note or "").strip(),
        due_at=_parse_due(body.due_at),
        created_by=user.id,
    )
    db.add(review)
    db.flush()
    case_set.review_state = "reviewing"
    case_set.review_assignee_id = assignee_id
    db.add(
        AuditLog(
            user_id=user.id,
            action="case_review_request",
            target_type="case_set",
            target_id=case_set.id,
            detail={"request_id": review.id, "assignee_id": assignee_id, "due_at": str(review.due_at or "")},
            ip=client_ip(request),
        )
    )
    db.commit()
    db.refresh(case_set)
    return _workspace(db, case_set)


@router.post("/{set_id}/review-requests/{request_id}/decision", response_model=CaseReviewWorkspaceOut)
def decide_review_request(
    set_id: str,
    request_id: str,
    body: CaseReviewDecisionIn,
    request: FastApiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """提交评审结论；通过时自动生成版本快照，要求修改必须填原因。"""
    case_set = _get_set(db, set_id, lock=True)
    review = (
        db.query(CaseReviewRequest)
        .filter(
            CaseReviewRequest.id == request_id,
            CaseReviewRequest.case_set_id == case_set.id,
        )
        .with_for_update()
        .first()
    )
    if not review:
        raise AppError(ErrorCode.NOT_FOUND, "评审请求不存在")
    if review.status != "pending":
        raise AppError(ErrorCode.CONCURRENCY, "评审已结束，请刷新后查看")
    note = (body.note or "").strip()
    if body.decision == "changes_requested" and not note:
        raise AppError(ErrorCode.VALIDATION, "要求修改时必须填写原因")
    review.status = body.decision
    review.decision_note = note
    review.decided_by = user.id
    review.decided_at = utcnow()
    case_set.review_state = "approved" if body.decision == "approved" else "changes_requested"
    if body.decision == "approved" and case_set.status == "generated":
        create_version(db, case_set, user_id=user.id, reason="review_approved")
    db.add(
        AuditLog(
            user_id=user.id,
            action="case_review_decision",
            target_type="case_set",
            target_id=case_set.id,
            detail={"request_id": review.id, "decision": body.decision},
            ip=client_ip(request),
        )
    )
    db.commit()
    db.refresh(case_set)
    return _workspace(db, case_set)


@router.post("/{set_id}/comments", response_model=CaseReviewWorkspaceOut)
def add_review_comment(
    set_id: str,
    body: CaseReviewCommentIn,
    request: FastApiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """新增整体或行级评论；不修改用例内容与 revision。"""
    case_set = _get_set(db, set_id)
    if case_set.status == "cancelled":
        raise AppError(ErrorCode.VALIDATION, "已废弃用例集不能再评论")
    case_item_id = (body.case_item_id or "").strip() or None
    if case_item_id:
        item = (
            db.query(CaseItem)
            .filter(CaseItem.id == case_item_id, CaseItem.case_set_id == case_set.id)
            .first()
        )
        if not item:
            raise AppError(ErrorCode.VALIDATION, "评论关联的用例不存在")
    comment = CaseReviewComment(
        case_set_id=case_set.id,
        case_item_id=case_item_id,
        author_id=user.id,
        body=body.body.strip(),
    )
    db.add(comment)
    db.flush()
    db.add(
        AuditLog(
            user_id=user.id,
            action="case_review_comment",
            target_type="case_set",
            target_id=case_set.id,
            detail={"comment_id": comment.id, "case_item_id": case_item_id},
            ip=client_ip(request),
        )
    )
    db.commit()
    db.refresh(case_set)
    return _workspace(db, case_set)


@router.get("/{set_id}/ai-reviews", response_model=list[CaseReviewRunOut])
def list_ai_reviews(
    set_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """AI 评审历史；最新在前，不覆盖旧结果。"""
    _get_set(db, set_id)
    runs = (
        db.query(CaseReviewRun)
        .filter(CaseReviewRun.case_set_id == set_id)
        .order_by(CaseReviewRun.created_at.desc())
        .limit(limit)
        .all()
    )
    return [_run_out(run) for run in runs]


@router.post("/{set_id}/versions", response_model=CaseSetVersionOut)
def create_case_version(
    set_id: str,
    body: CaseVersionCreateIn,
    request: FastApiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """手动创建版本快照；用于评审前留档或阶段性对比。"""
    case_set = _get_set(db, set_id, lock=True)
    if case_set.status != "generated":
        raise AppError(ErrorCode.VALIDATION, "只有草稿用例集可以手动创建版本")
    if case_set.generated_count < 1:
        raise AppError(ErrorCode.VALIDATION, "空用例集不能创建版本")
    version = create_version(db, case_set, user_id=user.id, reason=body.reason or "手动存版")
    db.add(
        AuditLog(
            user_id=user.id,
            action="case_set_version_create",
            target_type="case_set",
            target_id=case_set.id,
            detail={"version": version.version, "reason": version.reason},
            ip=client_ip(request),
        )
    )
    db.commit()
    db.refresh(version)
    return _version_out(version, user_names(db, [version.created_by]))


@router.get("/{set_id}/versions", response_model=list[CaseSetVersionOut])
def list_case_versions(
    set_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """版本列表；只返回元信息，避免一次传输全部快照。"""
    _get_set(db, set_id)
    versions = (
        db.query(CaseSetVersion)
        .filter(CaseSetVersion.case_set_id == set_id)
        .order_by(CaseSetVersion.version.desc())
        .limit(100)
        .all()
    )
    names = user_names(db, [version.created_by for version in versions])
    return [_version_out(version, names) for version in versions]


@router.get("/{set_id}/versions/{version}/diff", response_model=CaseVersionDiffOut)
def diff_case_version(
    set_id: str,
    version: int,
    base_version: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """版本字段级 diff；默认对比上一版，第一版对比空快照。"""
    _get_set(db, set_id)
    target = (
        db.query(CaseSetVersion)
        .filter(CaseSetVersion.case_set_id == set_id, CaseSetVersion.version == version)
        .first()
    )
    if not target:
        raise AppError(ErrorCode.NOT_FOUND, "版本不存在")
    base_number = base_version if base_version is not None else max(version - 1, 0)
    base_cases: list[dict[str, Any]] = []
    if base_number > 0:
        base = (
            db.query(CaseSetVersion)
            .filter(CaseSetVersion.case_set_id == set_id, CaseSetVersion.version == base_number)
            .first()
        )
        if not base:
            raise AppError(ErrorCode.NOT_FOUND, "对比版本不存在")
        base_cases = list((base.snapshot or {}).get("cases") or [])
    target_cases = list((target.snapshot or {}).get("cases") or [])
    result = diff_snapshots(base_cases, target_cases)
    return CaseVersionDiffOut(base_version=base_number, target_version=version, **result)


@router.get("/{set_id}/versions/{version}", response_model=CaseSetVersionDetailOut)
def get_case_version(
    set_id: str,
    version: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """读取版本详情与完整快照。"""
    _get_set(db, set_id)
    row = (
        db.query(CaseSetVersion)
        .filter(CaseSetVersion.case_set_id == set_id, CaseSetVersion.version == version)
        .first()
    )
    if not row:
        raise AppError(ErrorCode.NOT_FOUND, "版本不存在")
    names = user_names(db, [row.created_by])
    return CaseSetVersionDetailOut(
        **_version_out(row, names).model_dump(),
        snapshot=row.snapshot or {},
    )


@router.post("/{set_id}/versions/{version}/restore", response_model=CaseVersionRestoreOut)
def restore_case_version(
    set_id: str,
    version: int,
    request: FastApiRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """以历史版本创建新草稿，不覆盖历史或当前用例集。"""
    source_set = _get_set(db, set_id)
    row = (
        db.query(CaseSetVersion)
        .filter(CaseSetVersion.case_set_id == set_id, CaseSetVersion.version == version)
        .first()
    )
    if not row:
        raise AppError(ErrorCode.NOT_FOUND, "版本不存在")
    snapshot = row.snapshot or {}
    cases = list(snapshot.get("cases") or [])
    if not cases:
        raise AppError(ErrorCode.VALIDATION, "版本快照为空，无法回滚")
    new_set = CaseSet(
        name=f"{source_set.name}（回滚 v{version}）"[:120],
        status="generated",
        generated_count=len(cases),
        confirmed_count=0,
        revision=0,
        folder_id=source_set.folder_id,
        column_schema=list(snapshot.get("column_schema") or []),
        checks=list(snapshot.get("checks") or []),
        requirement_baseline_id=source_set.requirement_baseline_id,
        created_by=user.id,
    )
    db.add(new_set)
    db.flush()
    for index, case in enumerate(cases):
        db.add(
            CaseItem(
                case_set_id=new_set.id,
                strategy=str(case.get("strategy") or "正向"),
                priority=str(case.get("priority") or "HX"),
                module=str(case.get("module") or ""),
                submodule=str(case.get("submodule") or ""),
                feature_point=str(case.get("feature_point") or ""),
                name=str(case.get("name") or "未命名用例"),
                precondition=str(case.get("precondition") or ""),
                steps=str(case.get("steps") or ""),
                expected=str(case.get("expected") or ""),
                test_type=str(case.get("test_type") or ""),
                extras=case.get("extras") or {},
                sort_order=index,
                pending_complete=not (case.get("name") and case.get("expected")),
            )
        )
    db.add(
        AuditLog(
            user_id=user.id,
            action="case_set_version_restore",
            target_type="case_set",
            target_id=new_set.id,
            detail={"source_set_id": source_set.id, "source_version": version},
            ip=client_ip(request),
        )
    )
    db.commit()
    db.refresh(new_set)
    return CaseVersionRestoreOut(
        case_set_id=new_set.id,
        name=new_set.name,
        source_version=version,
    )
