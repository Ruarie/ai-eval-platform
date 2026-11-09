"""用例资产库路由（N-05 MVP）。

只读检索与标签维护；确认入库时由 cases 路由物化，另提供历史集合回填。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..case_asset_service import (
    asset_out,
    asset_stats,
    backfill_assets,
    search_assets,
    similar_assets,
    update_tags,
)
from ..db import get_db
from ..deps import get_current_user
from ..errors import AppError, ErrorCode
from ..models import AuditLog, CaseAsset, CaseSet, User
from ..schemas import (
    CaseAssetBackfillOut,
    CaseAssetListOut,
    CaseAssetSimilarIn,
    CaseAssetSimilarOut,
    CaseAssetStatsOut,
    CaseAssetTagsIn,
)
from ._common import client_ip

router = APIRouter(prefix="/api/case-assets", tags=["case-assets"])


def _get_asset(db: Session, asset_id: str) -> CaseAsset:
    """读取资产或抛出 NOT_FOUND；已撤回资产视为不存在。"""
    asset = (
        db.query(CaseAsset)
        .filter(CaseAsset.id == asset_id, CaseAsset.revoked_at.is_(None))
        .first()
    )
    if not asset:
        raise AppError(ErrorCode.NOT_FOUND, "用例资产不存在或已撤回")
    return asset


def _source_name(db: Session, asset: CaseAsset) -> str:
    """单条资产来源集合名称。"""
    if not asset.source_case_set_id:
        return ""
    row = db.query(CaseSet.name).filter(CaseSet.id == asset.source_case_set_id).first()
    return row[0] if row else ""


@router.get("", response_model=CaseAssetListOut, summary="检索用例资产")
def list_case_assets(
    q: str = Query(default="", max_length=200),
    module: str = Query(default="", max_length=80),
    strategy: str = Query(default="", max_length=20),
    priority: str = Query(default="", max_length=8),
    tag: str = Query(default="", max_length=20),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> CaseAssetListOut:
    """按关键词/模块/策略/优先级/标签检索；只返回未撤回资产。"""
    items, total = search_assets(
        db,
        q=q,
        module=module,
        strategy=strategy,
        priority=priority,
        tag=tag,
        offset=offset,
        limit=limit,
    )
    return CaseAssetListOut(items=items, total=total, offset=offset, limit=limit)


@router.get("/stats", response_model=CaseAssetStatsOut, summary="资产库概览")
def get_case_asset_stats(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> CaseAssetStatsOut:
    """返回总数、来源集合、模块与标签分布。"""
    return asset_stats(db)


@router.get("/{asset_id}", summary="读取单条用例资产")
def get_case_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    """详情包含完整步骤与预期，供资产抽屉展示。"""
    asset = _get_asset(db, asset_id)
    return asset_out(asset, {asset.source_case_set_id or "": _source_name(db, asset)}).model_dump()


@router.put("/{asset_id}/tags", summary="更新资产标签")
def set_case_asset_tags(
    asset_id: str,
    payload: CaseAssetTagsIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """覆盖式更新标签；最多 10 个、单标签 20 字。"""
    asset = _get_asset(db, asset_id)
    before = list(asset.tags or [])
    updated = update_tags(db, asset, payload.tags)
    db.add(
        AuditLog(
            user_id=user.id,
            action="case_asset_tags_update",
            target_type="case_asset",
            target_id=asset.id,
            detail={"before": before, "after": list(updated.tags or [])},
            ip=client_ip(request),
        )
    )
    db.commit()
    return asset_out(updated, {updated.source_case_set_id or "": _source_name(db, updated)})


@router.post("/similar", response_model=CaseAssetSimilarOut, summary="文本查重候选")
def find_similar_assets(
    payload: CaseAssetSimilarIn,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> CaseAssetSimilarOut:
    """对最近 500 条资产做文本相似度排序，只返回候选，不落库。"""
    return CaseAssetSimilarOut(items=similar_assets(db, payload))


@router.post("/backfill", response_model=CaseAssetBackfillOut, summary="回填历史已确认用例")
def backfill_case_assets(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CaseAssetBackfillOut:
    """为最近 100 个已确认用例集补资产；幂等。"""
    scanned, created = backfill_assets(db)
    db.add(
        AuditLog(
            user_id=user.id,
            action="case_asset_backfill",
            target_type="case_asset",
            target_id="backfill",
            detail={"scanned_sets": scanned, "created_assets": created},
            ip=client_ip(request),
        )
    )
    db.commit()
    return CaseAssetBackfillOut(scanned_sets=scanned, created_assets=created)
