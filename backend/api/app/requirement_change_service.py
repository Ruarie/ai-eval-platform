"""需求基线版本链、差异与影响分析（N-04 MVP）。

边界：
- 新版本必须从已有基线派生，保留 ``parent_id``；首版不能凭空覆盖旧版；
- 版本创建只解析编号条目，确认仍走 N-01 的人工确认接口；
- 影响分析只读：按旧基线绑定的用例集与关联，列出受变更影响的用例；
- 本期不自动创建/修改用例草稿，避免“分析即改库”。
"""

from __future__ import annotations

from typing import Any

from shared.requirements import diff_requirements, extract_requirements
from sqlalchemy.orm import Session

from .errors import AppError, ErrorCode
from .models import (
    AuditLog,
    CaseItem,
    CaseRequirementLink,
    CaseSet,
    RequirementBaseline,
    RequirementItem,
    User,
)
from .schemas import (
    RequirementBaselineCreate,
    RequirementDiffOut,
    RequirementImpactCaseOut,
    RequirementImpactOut,
    RequirementImpactSetOut,
)

MAX_IMPACT_CASES = 1000
MAX_IMPACT_SETS = 100
MAX_DIFF_ITEMS = 500


def baseline_items(db: Session, baseline_id: str) -> list[RequirementItem]:
    """按稳定顺序读取基线条目。"""
    return (
        db.query(RequirementItem)
        .filter(RequirementItem.baseline_id == baseline_id)
        .order_by(RequirementItem.sort_order.asc(), RequirementItem.created_at.asc())
        .all()
    )


def _item_dict(item: RequirementItem) -> dict[str, Any]:
    """转换为 diff 纯函数需要的结构。"""
    return {
        "id": item.id,
        "req_no": item.req_no,
        "title": item.title,
        "priority": item.priority,
        "module": item.module,
        "description": item.description,
    }


def create_version(
    db: Session,
    base: RequirementBaseline,
    payload: RequirementBaselineCreate,
    *,
    user: User,
    ip: str | None,
) -> RequirementBaseline:
    """从已确认基线派生一个新版本草稿。"""
    if base.status != "confirmed":
        raise AppError(ErrorCode.VALIDATION, "只有已确认的需求基线才能创建新版本")
    parsed = extract_requirements(payload.source_text)
    if not parsed:
        raise AppError(
            ErrorCode.VALIDATION,
            "未识别到需求编号（FR-/NFR-/BR-/SR-）；请先给需求条目编号后重试",
        )

    version = RequirementBaseline(
        parent_id=base.id,
        name=payload.name.strip(),
        source_kind=payload.source_kind,
        source_name=payload.source_name.strip(),
        status="draft",
        revision=base.revision + 1,
        requirement_count=len(parsed),
        created_by=user.id,
    )
    db.add(version)
    db.flush()
    for index, item in enumerate(parsed):
        db.add(
            RequirementItem(
                baseline_id=version.id,
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
            action="requirement_baseline_version_create",
            target_type="requirement_baseline",
            target_id=version.id,
            detail={
                "parent_id": base.id,
                "name": version.name,
                "requirement_count": len(parsed),
            },
            ip=ip,
        )
    )
    db.commit()
    db.refresh(version)
    return version


def diff_baselines(
    db: Session,
    base: RequirementBaseline,
    target: RequirementBaseline,
) -> RequirementDiffOut:
    """比较两个版本；目标版本可以是草稿，方便确认前预览。"""
    diff = diff_requirements(
        [_item_dict(item) for item in baseline_items(db, base.id)],
        [_item_dict(item) for item in baseline_items(db, target.id)],
        limit=MAX_DIFF_ITEMS,
    )
    return RequirementDiffOut(
        base_id=base.id,
        target_id=target.id,
        base_name=base.name,
        target_name=target.name,
        **diff,
    )


def impact_baselines(
    db: Session,
    base: RequirementBaseline,
    target: RequirementBaseline,
) -> RequirementImpactOut:
    """按旧基线的用例关联列出受变更影响的用例。"""
    diff = diff_baselines(db, base, target)
    base_items = baseline_items(db, base.id)
    item_by_req_no = {item.req_no.strip().upper(): item for item in base_items}
    affected_req_ids: set[str] = set()
    change_type: dict[str, str] = {}
    for item in diff.changed:
        requirement = item_by_req_no.get(item.req_no.strip().upper())
        if requirement:
            affected_req_ids.add(requirement.id)
            change_type[requirement.id] = "changed"
    for item in diff.removed:
        requirement = item_by_req_no.get(item.req_no.strip().upper())
        if requirement:
            affected_req_ids.add(requirement.id)
            change_type[requirement.id] = "removed"

    if not affected_req_ids:
        return RequirementImpactOut(
            base_id=base.id,
            target_id=target.id,
            diff=diff,
            affected_set_count=0,
            affected_case_count=0,
        )

    sets = (
        db.query(CaseSet)
        .filter(CaseSet.requirement_baseline_id == base.id)
        .order_by(CaseSet.created_at.desc())
        .limit(MAX_IMPACT_SETS)
        .all()
    )
    set_ids = [case_set.id for case_set in sets]
    if not set_ids:
        return RequirementImpactOut(
            base_id=base.id,
            target_id=target.id,
            diff=diff,
            affected_set_count=0,
            affected_case_count=0,
        )

    links = (
        db.query(CaseRequirementLink)
        .filter(
            CaseRequirementLink.case_set_id.in_(set_ids),
            CaseRequirementLink.requirement_id.in_(affected_req_ids),
        )
        .order_by(CaseRequirementLink.created_at.asc())
        .all()
    )
    case_ids = {link.case_item_id for link in links}
    cases = (
        db.query(CaseItem).filter(CaseItem.id.in_(case_ids)).all() if case_ids else []
    )
    case_by_id = {case.id: case for case in cases}
    requirement_by_id = {item.id: item for item in base_items}
    set_by_id = {case_set.id: case_set for case_set in sets}

    rows: list[RequirementImpactCaseOut] = []
    per_set: dict[str, int] = {}
    for link in links:
        case = case_by_id.get(link.case_item_id)
        requirement = requirement_by_id.get(link.requirement_id)
        case_set = set_by_id.get(link.case_set_id)
        if not case or not requirement or not case_set:
            continue
        per_set[case_set.id] = per_set.get(case_set.id, 0) + 1
        if len(rows) < MAX_IMPACT_CASES:
            rows.append(
                RequirementImpactCaseOut(
                    case_set_id=case_set.id,
                    set_name=case_set.name,
                    set_status=case_set.status,
                    case_item_id=case.id,
                    case_name=case.name,
                    req_no=requirement.req_no,
                    req_title=requirement.title,
                    change_type=change_type.get(requirement.id, "changed"),
                )
            )

    sets_out = [
        RequirementImpactSetOut(
            case_set_id=case.id,
            name=case.name,
            status=case.status,
            affected_cases=per_set.get(case.id, 0),
        )
        for case in sets
        if per_set.get(case.id, 0) > 0
    ]
    return RequirementImpactOut(
        base_id=base.id,
        target_id=target.id,
        diff=diff,
        affected_set_count=len(sets_out),
        affected_case_count=sum(per_set.values()),
        sets=sets_out,
        cases=rows,
        truncated=len(rows) >= MAX_IMPACT_CASES,
    )


def resolve_pair(
    db: Session,
    target: RequirementBaseline,
    base_id: str | None,
) -> tuple[RequirementBaseline, RequirementBaseline]:
    """确定比较基准：显式 base_id 优先，其次 parent_id。"""
    resolved = base_id or target.parent_id
    if not resolved:
        raise AppError(ErrorCode.VALIDATION, "该基线没有父版本，无法做变更分析")
    base = db.query(RequirementBaseline).filter(RequirementBaseline.id == resolved).first()
    if not base:
        raise AppError(ErrorCode.NOT_FOUND, "对比基准版本不存在")
    if base.id == target.id:
        raise AppError(ErrorCode.VALIDATION, "对比基准不能是当前版本")
    return base, target
