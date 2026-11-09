"""需求基线与用例覆盖路由（N-01 MVP）。

职责边界：

- 基线只保存从原文抽取的需求条目，不复制整份需求正文；
- 覆盖率只统计“已确认基线 + 已关联用例”的事实，不宣称功能正确；
- 自动关联只返回候选，落库必须经人工确认接口；
- 关联元数据不修改用例内容，也不推进 ``case_sets.revision``。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from shared.requirements import auto_link_requirements, build_coverage, extract_requirements
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..errors import AppError, ErrorCode
from ..models import (
    AuditLog,
    CaseItem,
    CaseRequirementLink,
    CaseSet,
    RequirementBaseline,
    RequirementItem,
    User,
    utcnow,
)
from ..requirement_change_service import (
    create_version,
    diff_baselines,
    impact_baselines,
    resolve_pair,
)
from ..schemas import (
    CaseAutoLinkIn,
    CaseAutoLinkOut,
    CaseCoverageOut,
    CaseRequirementBindIn,
    CaseRequirementLinkIn,
    RequirementBaselineCreate,
    RequirementBaselineDetailOut,
    RequirementBaselineOut,
    RequirementDiffOut,
    RequirementImpactOut,
    RequirementItemOut,
    RequirementItemUpdate,
)
from ._common import client_ip

router = APIRouter(tags=["requirements"])

# 单次人工关联的上限，防止浏览器误提交超大数组拖垮事务。
MAX_LINK_CASES = 5000
MAX_REQUIREMENTS_PER_CASE = 20


def _get_baseline_or_404(db: Session, baseline_id: str, *, lock: bool = False) -> RequirementBaseline:
    """读取需求基线或抛出 NOT_FOUND。"""
    query = db.query(RequirementBaseline).filter(RequirementBaseline.id == baseline_id)
    if lock:
        query = query.populate_existing().with_for_update()
    baseline = query.first()
    if not baseline:
        raise AppError(ErrorCode.NOT_FOUND, "需求基线不存在")
    return baseline


def _get_case_set_or_404(db: Session, set_id: str) -> CaseSet:
    """读取用例集或抛出 NOT_FOUND。"""
    case_set = db.query(CaseSet).filter(CaseSet.id == set_id).first()
    if not case_set:
        raise AppError(ErrorCode.NOT_FOUND, "用例集不存在")
    return case_set


def _list_requirements(db: Session, baseline_id: str) -> list[RequirementItem]:
    """按排序号返回基线内全部需求条目。"""
    return (
        db.query(RequirementItem)
        .filter(RequirementItem.baseline_id == baseline_id)
        .order_by(RequirementItem.sort_order.asc(), RequirementItem.created_at.asc())
        .all()
    )


def _item_out(item: RequirementItem) -> RequirementItemOut:
    """把 ORM 条目转换为响应模型。"""
    return RequirementItemOut(
        id=item.id,
        req_no=item.req_no,
        title=item.title,
        description=item.description or "",
        priority=item.priority or "",
        module=item.module or "",
        source_ref=item.source_ref or "",
        sort_order=item.sort_order or 0,
    )


def _baseline_detail(db: Session, baseline: RequirementBaseline) -> RequirementBaselineDetailOut:
    """组装基线详情，避免前端多次请求。"""
    return RequirementBaselineDetailOut(
        id=baseline.id,
        parent_id=baseline.parent_id,
        name=baseline.name,
        source_kind=baseline.source_kind,
        source_name=baseline.source_name,
        status=baseline.status,
        revision=baseline.revision,
        requirement_count=baseline.requirement_count,
        created_by=baseline.created_by,
        created_at=baseline.created_at,
        updated_at=baseline.updated_at,
        requirements=[_item_out(item) for item in _list_requirements(db, baseline.id)],
    )


def _assert_confirmed(baseline: RequirementBaseline) -> None:
    """只有确认后的基线才能作为覆盖率分母或关联目标。"""
    if baseline.status != "confirmed":
        raise AppError(ErrorCode.VALIDATION, "需求基线尚未确认，请先完成人工校对并确认")


def _assert_bound(case_set: CaseSet, baseline_id: str) -> None:
    """用例集必须显式绑定到同一基线，避免跨基线关联。"""
    if case_set.requirement_baseline_id != baseline_id:
        raise AppError(ErrorCode.VALIDATION, "用例集未绑定该需求基线，请先绑定")


@router.post(
    "/api/requirement-baselines",
    response_model=RequirementBaselineDetailOut,
    status_code=201,
    summary="创建需求基线并解析编号条目",
)
def create_requirement_baseline(
    payload: RequirementBaselineCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RequirementBaselineDetailOut:
    """从需求原文抽取 FR-/NFR-/BR-/SR- 条目，保存为可校对草稿。"""
    parsed = extract_requirements(payload.source_text)
    if not parsed:
        raise AppError(
            ErrorCode.VALIDATION,
            "未识别到需求编号（FR-/NFR-/BR-/SR-）；请先给需求条目编号后重试",
        )

    baseline = RequirementBaseline(
        name=payload.name.strip(),
        source_kind=payload.source_kind,
        source_name=payload.source_name.strip(),
        status="draft",
        revision=1,
        requirement_count=len(parsed),
        created_by=user.id,
    )
    db.add(baseline)
    db.flush()

    for index, item in enumerate(parsed):
        db.add(
            RequirementItem(
                baseline_id=baseline.id,
                req_no=item.req_no,
                title=item.title,
                description="",
                priority=item.priority,
                module=item.module,
                source_ref=item.source_ref,
                sort_order=index,
            )
        )

    db.add(
        AuditLog(
            user_id=user.id,
            action="requirement_baseline_create",
            target_type="requirement_baseline",
            target_id=baseline.id,
            detail={
                "name": baseline.name,
                "source_kind": baseline.source_kind,
                "requirement_count": len(parsed),
            },
            ip=client_ip(request),
        )
    )
    db.commit()
    db.refresh(baseline)
    return _baseline_detail(db, baseline)


@router.get(
    "/api/requirement-baselines",
    response_model=list[RequirementBaselineOut],
    summary="列出需求基线",
)
def list_requirement_baselines(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[RequirementBaselineOut]:
    """按创建时间倒序返回最近 100 份基线。"""
    rows = (
        db.query(RequirementBaseline)
        .order_by(RequirementBaseline.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        RequirementBaselineOut(
            id=row.id,
            parent_id=row.parent_id,
            name=row.name,
            source_kind=row.source_kind,
            source_name=row.source_name,
            status=row.status,
            revision=row.revision,
            requirement_count=row.requirement_count,
            created_by=row.created_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.get(
    "/api/requirement-baselines/{baseline_id}",
    response_model=RequirementBaselineDetailOut,
    summary="读取需求基线详情",
)
def get_requirement_baseline(
    baseline_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> RequirementBaselineDetailOut:
    """返回基线元信息与全部需求条目。"""
    return _baseline_detail(db, _get_baseline_or_404(db, baseline_id))


@router.put(
    "/api/requirement-baselines/{baseline_id}/requirements/{requirement_id}",
    response_model=RequirementItemOut,
    summary="人工校对单条需求",
)
def update_requirement_item(
    baseline_id: str,
    requirement_id: str,
    payload: RequirementItemUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RequirementItemOut:
    """草稿基线可校对标题/描述/优先级/模块；确认后只读。"""
    baseline = _get_baseline_or_404(db, baseline_id, lock=True)
    if baseline.status != "draft":
        raise AppError(ErrorCode.VALIDATION, "需求基线已确认，不可继续修改")
    item = (
        db.query(RequirementItem)
        .filter(RequirementItem.id == requirement_id, RequirementItem.baseline_id == baseline_id)
        .first()
    )
    if not item:
        raise AppError(ErrorCode.NOT_FOUND, "需求条目不存在")

    values = payload.model_dump(exclude_unset=True)
    priority = values.get("priority")
    if priority is not None and str(priority).strip() not in {"", "P0", "P1", "P2", "P3"}:
        raise AppError(ErrorCode.VALIDATION, "优先级仅支持 P0/P1/P2/P3")
    for field, value in values.items():
        if value is not None:
            setattr(item, field, str(value).strip())
    baseline.revision += 1
    baseline.updated_at = utcnow()
    db.add(
        AuditLog(
            user_id=user.id,
            action="requirement_item_update",
            target_type="requirement_baseline",
            target_id=baseline.id,
            detail={"requirement_id": item.id, "fields": sorted(values)},
            ip=client_ip(request),
        )
    )
    db.commit()
    db.refresh(item)
    return _item_out(item)


@router.post(
    "/api/requirement-baselines/{baseline_id}/confirm",
    response_model=RequirementBaselineDetailOut,
    summary="确认需求基线",
)
def confirm_requirement_baseline(
    baseline_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RequirementBaselineDetailOut:
    """确认后基线只读，并可作为覆盖率分母。重复确认幂等返回。"""
    baseline = _get_baseline_or_404(db, baseline_id, lock=True)
    items = _list_requirements(db, baseline_id)
    if not items:
        raise AppError(ErrorCode.VALIDATION, "需求基线为空，不能确认")
    if baseline.status != "confirmed":
        baseline.status = "confirmed"
        baseline.requirement_count = len(items)
        baseline.revision += 1
        baseline.updated_at = utcnow()
        db.add(
            AuditLog(
                user_id=user.id,
                action="requirement_baseline_confirm",
                target_type="requirement_baseline",
                target_id=baseline.id,
                detail={"name": baseline.name, "requirement_count": len(items)},
                ip=client_ip(request),
            )
        )
        db.commit()
        db.refresh(baseline)
    return _baseline_detail(db, baseline)


@router.post(
    "/api/requirement-baselines/{baseline_id}/versions",
    response_model=RequirementBaselineDetailOut,
    status_code=201,
    summary="从已确认基线创建新版本草稿",
)
def create_requirement_baseline_version(
    baseline_id: str,
    payload: RequirementBaselineCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RequirementBaselineDetailOut:
    """新版本保留 parent_id，确认前仍可人工校对。"""
    base = _get_baseline_or_404(db, baseline_id, lock=True)
    version = create_version(db, base, payload, user=user, ip=client_ip(request))
    return _baseline_detail(db, version)


@router.get(
    "/api/requirement-baselines/{baseline_id}/diff",
    response_model=RequirementDiffOut,
    summary="对比需求基线版本",
)
def diff_requirement_baseline(
    baseline_id: str,
    base_id: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> RequirementDiffOut:
    """默认与 parent 对比；没有父版本时必须显式传 base_id。"""
    target = _get_baseline_or_404(db, baseline_id)
    base, target = resolve_pair(db, target, base_id)
    return diff_baselines(db, base, target)


@router.get(
    "/api/requirement-baselines/{baseline_id}/impact",
    response_model=RequirementImpactOut,
    summary="分析需求变更影响的用例",
)
def impact_requirement_baseline(
    baseline_id: str,
    base_id: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> RequirementImpactOut:
    """只读列出旧基线绑定用例集中受变更影响的用例。"""
    target = _get_baseline_or_404(db, baseline_id)
    base, target = resolve_pair(db, target, base_id)
    return impact_baselines(db, base, target)


@router.post(
    "/api/case-sets/{set_id}/requirement-baseline",
    response_model=CaseCoverageOut,
    summary="绑定用例集与需求基线",
)
def bind_case_set_baseline(
    set_id: str,
    payload: CaseRequirementBindIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CaseCoverageOut:
    """把用例集绑定到已确认基线，随后返回一次覆盖率快照。"""
    baseline_id = payload.baseline_id
    baseline = _get_baseline_or_404(db, baseline_id)
    _assert_confirmed(baseline)
    case_set = _get_case_set_or_404(db, set_id)
    if case_set.status == "cancelled":
        raise AppError(ErrorCode.VALIDATION, "用例集已废弃，不能绑定需求基线")

    if case_set.requirement_baseline_id != baseline_id:
        # 换绑基线时清理旧关联，避免旧基线的链接在换回时“复活”成幽灵覆盖。
        db.query(CaseRequirementLink).filter(
            CaseRequirementLink.case_set_id == case_set.id
        ).delete(synchronize_session=False)
        case_set.requirement_baseline_id = baseline_id
        db.add(
            AuditLog(
                user_id=user.id,
                action="case_set_requirement_bind",
                target_type="case_set",
                target_id=case_set.id,
                detail={"baseline_id": baseline_id, "baseline_revision": baseline.revision},
                ip=client_ip(request),
            )
        )
        db.commit()
        db.refresh(case_set)
    return _coverage_for(db, case_set, baseline)


def _coverage_for(
    db: Session,
    case_set: CaseSet,
    baseline: RequirementBaseline,
) -> CaseCoverageOut:
    """按当前绑定计算覆盖率；查询只读，不写库。"""
    items = _list_requirements(db, baseline.id)
    cases = (
        db.query(CaseItem)
        .filter(CaseItem.case_set_id == case_set.id)
        .order_by(CaseItem.sort_order.asc())
        .all()
    )
    requirement_ids = {item.id for item in items}
    if requirement_ids:
        links = (
            db.query(CaseRequirementLink)
            .filter(
                CaseRequirementLink.case_set_id == case_set.id,
                CaseRequirementLink.requirement_id.in_(requirement_ids),
            )
            .all()
        )
    else:
        # 空基线没有分母，不查询关联；覆盖率会返回 0/0。
        links = []
    coverage = build_coverage(
        [
            {
                "id": item.id,
                "req_no": item.req_no,
                "title": item.title,
                "priority": item.priority,
                "module": item.module,
            }
            for item in items
        ],
        [
            {
                "id": case.id,
                "name": case.name,
                "feature_point": case.feature_point,
                "module": case.module,
                "expected": case.expected,
            }
            for case in cases
        ],
        [
            {
                "requirement_id": link.requirement_id,
                "case_item_id": link.case_item_id,
                "source": link.source,
                "confidence": link.confidence,
            }
            for link in links
        ],
    )
    return CaseCoverageOut(
        baseline_id=baseline.id,
        baseline_name=baseline.name,
        baseline_version=baseline.revision,
        **coverage,
    )


@router.get(
    "/api/case-sets/{set_id}/coverage",
    response_model=CaseCoverageOut,
    summary="读取用例集需求覆盖率",
)
def get_case_set_coverage(
    set_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> CaseCoverageOut:
    """未绑定基线时明确拒绝，不用 0% 冒充“没有缺口”。"""
    case_set = _get_case_set_or_404(db, set_id)
    if not case_set.requirement_baseline_id:
        raise AppError(ErrorCode.VALIDATION, "用例集尚未绑定需求基线")
    baseline = _get_baseline_or_404(db, case_set.requirement_baseline_id)
    return _coverage_for(db, case_set, baseline)


@router.post(
    "/api/case-sets/{set_id}/requirements/auto-link",
    response_model=CaseAutoLinkOut,
    summary="生成用例到需求的自动关联候选",
)
def auto_link_case_requirements(
    set_id: str,
    payload: CaseAutoLinkIn,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> CaseAutoLinkOut:
    """只返回候选，不落库；前端人工确认后再调用 link 接口。"""
    baseline = _get_baseline_or_404(db, payload.baseline_id)
    _assert_confirmed(baseline)
    case_set = _get_case_set_or_404(db, set_id)
    _assert_bound(case_set, baseline.id)

    items = _list_requirements(db, baseline.id)
    cases = db.query(CaseItem).filter(CaseItem.case_set_id == set_id).all()
    candidates = auto_link_requirements(
        [
            {
                "id": item.id,
                "req_no": item.req_no,
                "title": item.title,
                "module": item.module,
            }
            for item in items
        ],
        [
            {
                "id": case.id,
                "name": case.name,
                "feature_point": case.feature_point,
                "module": case.module,
                "expected": case.expected,
            }
            for case in cases
        ],
        threshold=payload.threshold,
    )
    requirement_by_id = {item.id: item for item in items}
    case_by_id = {case.id: case for case in cases}
    # 单次最多返回 500 条候选，避免超大用例集把抽屉和响应撑爆。
    for candidate in candidates[:500]:
        requirement = requirement_by_id.get(candidate["requirement_id"])
        case = case_by_id.get(candidate["case_item_id"])
        candidate["req_no"] = requirement.req_no if requirement else ""
        candidate["req_title"] = requirement.title if requirement else ""
        candidate["case_name"] = case.name if case else ""
    candidates = candidates[:500]
    return CaseAutoLinkOut(links=candidates, matched_case_count=len(candidates))


@router.post(
    "/api/case-sets/{set_id}/requirements/link",
    summary="人工确认用例与需求的关联",
)
def link_case_requirements(
    set_id: str,
    payload: CaseRequirementLinkIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """按用例替换关联；空数组表示解除该用例在当前基线下的全部关联。"""
    baseline = _get_baseline_or_404(db, payload.baseline_id)
    _assert_confirmed(baseline)
    case_set = _get_case_set_or_404(db, set_id)
    _assert_bound(case_set, baseline.id)
    if case_set.status == "cancelled":
        raise AppError(ErrorCode.VALIDATION, "用例集已废弃，不能调整需求关联")
    if len(payload.links) > MAX_LINK_CASES:
        raise AppError(ErrorCode.VALIDATION, f"单次最多关联 {MAX_LINK_CASES} 条用例")

    cases = (
        db.query(CaseItem)
        .filter(CaseItem.case_set_id == set_id)
        .all()
    )
    case_by_id = {case.id: case for case in cases}
    requirement_by_id = {item.id: item for item in _list_requirements(db, baseline.id)}

    for link in payload.links:
        if link.case_item_id not in case_by_id:
            raise AppError(ErrorCode.VALIDATION, "关联用例不属于当前用例集")
        if len(link.requirement_ids) > MAX_REQUIREMENTS_PER_CASE:
            raise AppError(
                ErrorCode.VALIDATION,
                f"单条用例最多关联 {MAX_REQUIREMENTS_PER_CASE} 条需求",
            )
        unknown = [req_id for req_id in link.requirement_ids if req_id not in requirement_by_id]
        if unknown:
            raise AppError(ErrorCode.VALIDATION, "关联需求不属于当前基线")

    for link in payload.links:
        db.query(CaseRequirementLink).filter(
            CaseRequirementLink.case_set_id == set_id,
            CaseRequirementLink.case_item_id == link.case_item_id,
        ).delete(synchronize_session=False)
        for requirement_id in dict.fromkeys(link.requirement_ids):
            db.add(
                CaseRequirementLink(
                    case_set_id=set_id,
                    case_item_id=link.case_item_id,
                    requirement_id=requirement_id,
                    source="manual",
                    confidence=1.0,
                )
            )

    db.add(
        AuditLog(
            user_id=user.id,
            action="case_requirement_link",
            target_type="case_set",
            target_id=case_set.id,
            detail={
                "baseline_id": baseline.id,
                "baseline_revision": baseline.revision,
                "case_count": len(payload.links),
                "link_count": sum(len(link.requirement_ids) for link in payload.links),
            },
            ip=client_ip(request),
        )
    )
    db.commit()
    return {"ok": True, "case_count": len(payload.links)}
