"""用例资产库服务（N-05 MVP）。

职责：
- 确认入库时把用例物化为跨集合资产；重复物化幂等，不覆盖人工标签；
- 资产检索、标签、概览与文本相似度提示；
- 本期只做“发现 + 查重”，不自动合并或复制资产。
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .models import CaseAsset, CaseItem, CaseSet
from .schemas import (
    CaseAssetOut,
    CaseAssetSimilarIn,
    CaseAssetSimilarItemOut,
    CaseAssetStatsOut,
)

MAX_TAG_LENGTH = 20
MAX_TAGS = 10
_NORMALIZE = re.compile(r"[\s\W_]+", re.UNICODE)


def _clean_tags(tags: list[str]) -> list[str]:
    """去空白、去重、截断，保持用户输入顺序。"""
    seen: set[str] = set()
    result: list[str] = []
    for raw in tags:
        value = str(raw or "").strip()[:MAX_TAG_LENGTH]
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
        if len(result) >= MAX_TAGS:
            break
    return result


def materialize_case_set(
    db: Session,
    case_set: CaseSet,
    *,
    user_id: str | None,
) -> int:
    """把用例集内尚未物化的用例写入资产库，返回新增数量。"""
    items = (
        db.query(CaseItem)
        .filter(CaseItem.case_set_id == case_set.id)
        .order_by(CaseItem.sort_order.asc())
        .all()
    )
    if not items:
        return 0
    existing = {
        row[0]
        for row in db.query(CaseAsset.source_case_item_id)
        .filter(CaseAsset.source_case_item_id.in_([item.id for item in items]))
        .all()
        if row[0]
    }
    created = 0
    for item in items:
        if item.id in existing:
            continue
        db.add(
            CaseAsset(
                source_case_set_id=case_set.id,
                source_case_item_id=item.id,
                name=item.name,
                module=item.module or "",
                submodule=item.submodule or "",
                feature_point=item.feature_point or "",
                strategy=item.strategy or "",
                priority=item.priority or "",
                precondition=item.precondition or "",
                steps=item.steps or "",
                expected=item.expected or "",
                tags=[],
                source_version=case_set.revision or 1,
                created_by=user_id,
            )
        )
        created += 1
    return created


def backfill_assets(db: Session, *, limit_sets: int = 100) -> tuple[int, int]:
    """为历史已确认用例集补资产；返回 (扫描集合数, 新增资产数)。"""
    sets = (
        db.query(CaseSet)
        .filter(CaseSet.status == "confirmed")
        .order_by(CaseSet.updated_at.desc())
        .limit(limit_sets)
        .all()
    )
    created = 0
    for case_set in sets:
        created += materialize_case_set(db, case_set, user_id=case_set.created_by)
    db.commit()
    return len(sets), created


def _set_names(db: Session, assets: list[CaseAsset]) -> dict[str, str]:
    """批量读取来源用例集名称，避免逐行回表。"""
    ids = {asset.source_case_set_id for asset in assets if asset.source_case_set_id}
    if not ids:
        return {}
    rows = db.query(CaseSet.id, CaseSet.name).filter(CaseSet.id.in_(ids)).all()
    return {row[0]: row[1] for row in rows}


def asset_out(asset: CaseAsset, names: dict[str, str]) -> CaseAssetOut:
    """ORM 资产转响应。"""
    return CaseAssetOut(
        id=asset.id,
        source_case_set_id=asset.source_case_set_id,
        source_set_name=names.get(asset.source_case_set_id or "", ""),
        source_case_item_id=asset.source_case_item_id,
        name=asset.name,
        module=asset.module,
        submodule=asset.submodule,
        feature_point=asset.feature_point,
        strategy=asset.strategy,
        priority=asset.priority,
        precondition=asset.precondition,
        steps=asset.steps,
        expected=asset.expected,
        tags=list(asset.tags or []),
        source_version=asset.source_version,
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


def search_assets(
    db: Session,
    *,
    q: str = "",
    module: str = "",
    strategy: str = "",
    priority: str = "",
    tag: str = "",
    offset: int = 0,
    limit: int = 20,
) -> tuple[list[CaseAssetOut], int]:
    """按文本/模块/策略/优先级/标签检索资产。"""
    query = db.query(CaseAsset).filter(CaseAsset.revoked_at.is_(None))
    term = q.strip()
    if term:
        pattern = f"%{term}%"
        query = query.filter(
            or_(
                CaseAsset.name.ilike(pattern),
                CaseAsset.feature_point.ilike(pattern),
                CaseAsset.expected.ilike(pattern),
                CaseAsset.precondition.ilike(pattern),
                CaseAsset.steps.ilike(pattern),
            )
        )
    if module.strip():
        query = query.filter(CaseAsset.module == module.strip())
    if strategy.strip():
        query = query.filter(CaseAsset.strategy == strategy.strip())
    if priority.strip():
        query = query.filter(CaseAsset.priority == priority.strip())
    if tag.strip():
        # PostgreSQL JSONB 包含查询；SQLite 功能测试不覆盖标签过滤。
        query = query.filter(CaseAsset.tags.contains([tag.strip()]))
    total = query.count()
    rows = (
        query.order_by(CaseAsset.updated_at.desc(), CaseAsset.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    names = _set_names(db, rows)
    return [asset_out(row, names) for row in rows], total


def update_tags(db: Session, asset: CaseAsset, tags: list[str]) -> CaseAsset:
    """覆盖式更新标签；空数组表示清空。"""
    asset.tags = _clean_tags(tags)
    db.commit()
    db.refresh(asset)
    return asset


def asset_stats(db: Session) -> CaseAssetStatsOut:
    """资产库概览：总数、来源集合、模块与标签分布。"""
    base = db.query(CaseAsset).filter(CaseAsset.revoked_at.is_(None))
    total = base.count()
    source_sets = (
        db.query(func.count(func.distinct(CaseAsset.source_case_set_id)))
        .filter(CaseAsset.revoked_at.is_(None), CaseAsset.source_case_set_id.isnot(None))
        .scalar()
        or 0
    )
    modules = [
        {"module": row[0] or "未分模块", "count": row[1]}
        for row in db.query(CaseAsset.module, func.count(CaseAsset.id))
        .filter(CaseAsset.revoked_at.is_(None))
        .group_by(CaseAsset.module)
        .order_by(func.count(CaseAsset.id).desc())
        .limit(15)
        .all()
    ]
    tag_counts: dict[str, int] = {}
    for asset in base.with_entities(CaseAsset.tags).all():
        for tag in asset[0] or []:
            tag_counts[str(tag)] = tag_counts.get(str(tag), 0) + 1
    tags = [
        {"tag": tag, "count": count}
        for tag, count in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))[:30]
    ]
    return CaseAssetStatsOut(total=total, source_sets=source_sets, modules=modules, tags=tags)


def _normalize(text: str) -> str:
    """查重前统一大小写、空白与标点，避免格式差异拉低相似度。"""
    return _NORMALIZE.sub("", str(text or "").lower())


def _ratio(left: str, right: str) -> float:
    """空文本不算相似，避免大量空字段把分数抬高。"""
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def similar_assets(
    db: Session,
    payload: CaseAssetSimilarIn,
) -> list[CaseAssetSimilarItemOut]:
    """对最近 500 条资产做文本相似度排序，只返回候选。"""
    rows = (
        db.query(CaseAsset)
        .filter(CaseAsset.revoked_at.is_(None))
        .order_by(CaseAsset.updated_at.desc())
        .limit(500)
        .all()
    )
    target_name = _normalize(payload.name)
    target_expected = _normalize(payload.expected)
    target_steps = _normalize(payload.steps)
    names = _set_names(db, rows)
    scored: list[tuple[float, CaseAsset]] = []
    for asset in rows:
        name_score = _ratio(target_name, _normalize(asset.name))
        expected_score = _ratio(target_expected, _normalize(asset.expected))
        steps_score = _ratio(target_steps, _normalize(asset.steps))
        weights = [0.65, 0.25, 0.10]
        values = [name_score, expected_score, steps_score]
        active = [
            (weight, value)
            for weight, value in zip(weights, values, strict=True)
            if value > 0
        ]
        if not active:
            continue
        weight_sum = sum(weight for weight, _ in active)
        score = sum(weight * value for weight, value in active) / weight_sum
        if score >= 0.2:
            scored.append((score, asset))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        CaseAssetSimilarItemOut(
            id=asset.id,
            name=asset.name,
            score=round(score, 4),
            module=asset.module,
            priority=asset.priority,
            source_case_set_id=asset.source_case_set_id,
            source_set_name=names.get(asset.source_case_set_id or "", ""),
        )
        for score, asset in scored[: payload.limit]
    ]
