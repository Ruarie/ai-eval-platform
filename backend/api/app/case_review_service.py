"""用例评审的数据库辅助：版本快照、版本号与用户名投影（N-02）。

只被路由层与确认链路调用；不承载权限判断与 HTTP 语义。
"""

from __future__ import annotations

from typing import Any

from shared.case_review import snapshot_cases
from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import CaseItem, CaseSet, CaseSetVersion, User, utcnow


def latest_version_number(db: Session, case_set_id: str) -> int:
    """当前用例集最大版本号；没有版本时返回 0。"""
    value = (
        db.query(func.max(CaseSetVersion.version))
        .filter(CaseSetVersion.case_set_id == case_set_id)
        .scalar()
    )
    return int(value or 0)


def build_snapshot(db: Session, case_set: CaseSet) -> dict[str, Any]:
    """读取当前用例行并生成完整快照；调用方负责事务边界。"""
    items = (
        db.query(CaseItem)
        .filter(CaseItem.case_set_id == case_set.id)
        .order_by(CaseItem.sort_order)
        .all()
    )
    return {
        "cases": snapshot_cases(items),
        "checks": list(case_set.checks or []),
        "column_schema": list(case_set.column_schema or []),
    }


def create_version(
    db: Session,
    case_set: CaseSet,
    *,
    user_id: str | None,
    reason: str = "",
) -> CaseSetVersion:
    """为用例集生成下一个不可变版本；不提交事务。"""
    next_version = latest_version_number(db, case_set.id) + 1
    snapshot = build_snapshot(db, case_set)
    version = CaseSetVersion(
        case_set_id=case_set.id,
        version=next_version,
        reason=(reason or "").strip()[:200],
        case_count=len(snapshot["cases"]),
        snapshot=snapshot,
        created_by=user_id,
    )
    db.add(version)
    return version


def user_names(db: Session, user_ids: list[str | None]) -> dict[str, str]:
    """批量查询成员展示名，缺失时回退用户名；避免逐行查库。"""
    ids = {value for value in user_ids if value}
    if not ids:
        return {}
    rows = db.query(User).filter(User.id.in_(ids)).all()
    return {
        row.id: (row.display_name or row.username or row.id)
        for row in rows
    }


def now_iso() -> str:
    """统一 UTC ISO 时间，供审计/响应使用。"""
    return utcnow().isoformat()
