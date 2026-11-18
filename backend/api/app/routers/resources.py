"""能力中心资源路由（复刻 iWarden 的 Agent / Skills / Scripts / Rules 四个中心 + 资源广场）。

设计要点：
1. **一套实体，四种形态**：``resources.kind`` 区分 agent / skill / script / rule，
   ``content`` 存该形态的定义；前端按 kind 渲染不同字段，服务端不做业务语义校验，
   只限制体积（防止把大文件塞进 JSONB）。
2. **可见性只有两档**：``team`` 全员可见、``private`` 仅属主与管理员可见；写操作
   只允许属主或管理员，读取按可见性过滤，避免"看得见改不了"的中间态。
3. **使用与广场**：``use`` 端点按次写 ``resource_usage_events`` 并累加 ``usage_count``；
   广场的「飙升榜」取近 7 日事件数，避免用累计值冒充热度。
4. 不落任何凭据：Agent 资源只引用协议档 ID（``model_profile_id``），不存 Key 与端点。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..errors import AppError, ErrorCode
from ..models import Resource, ResourceUsageEvent, User
from ..schemas import (
    PlazaOut,
    PlazaRankItem,
    ResourceCloneIn,
    ResourceCreateIn,
    ResourceListOut,
    ResourceOut,
    ResourceUpdateIn,
    ResourceUseOut,
)
from ._common import write_audit

router = APIRouter(prefix="/api/resources", tags=["resources"])

KINDS = ("agent", "skill", "script", "rule")
# content 上限：定义文本足够描述一个 Agent/Skill，同时挡住大文件与二进制。
MAX_CONTENT_BYTES = 100_000
PLAZA_LIMIT = 10


def _can_read(resource: Resource, user: User) -> bool:
    """团队可见的资源对全员开放；私有资源仅属主与管理员可读。"""
    return resource.visibility == "team" or resource.owner_id == user.id or user.role == "admin"


def _can_edit(resource: Resource, user: User) -> bool:
    """只有属主与管理员可以改、删、克隆源（克隆本身只要求可读）。"""
    return resource.owner_id == user.id or user.role == "admin"


def _iso(value: datetime | None) -> str:
    """统一 UTC ISO 字符串，避免前端按本地时区猜。"""
    if value is None:
        return ""
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()


def _owner_names(db: Session, rows: list[Resource]) -> dict[str, str]:
    """批量取属主展示名，避免逐行回表。"""
    ids = {r.owner_id for r in rows if r.owner_id}
    if not ids:
        return {}
    users = db.query(User.id, User.username, User.display_name).filter(User.id.in_(ids)).all()
    return {uid: (display or username or "") for uid, username, display in users}


def _out(resource: Resource, names: dict[str, str], user: User) -> ResourceOut:
    """把 ORM 行投影成出参；editable 由服务端判定，前端不再複算权限。"""
    return ResourceOut(
        id=resource.id,
        kind=resource.kind,
        name=resource.name,
        summary=resource.summary,
        content=resource.content or {},
        owner_id=resource.owner_id,
        owner_name=names.get(resource.owner_id or "", ""),
        visibility=resource.visibility,
        usage_count=resource.usage_count,
        source_id=resource.source_id,
        editable=_can_edit(resource, user),
        created_at=_iso(resource.created_at),
        updated_at=_iso(resource.updated_at),
    )


def _get_readable(db: Session, resource_id: str, user: User) -> Resource:
    """读取资源或抛出 NOT_FOUND / DENIED（不存在与无权访问区分开）。"""
    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        raise AppError(ErrorCode.NOT_FOUND, "资源不存在或已删除")
    if not _can_read(resource, user):
        raise AppError(ErrorCode.DENIED, "无权访问该资源")
    return resource


def _normalize_content(kind: str, content: dict) -> dict:
    """结构守卫：必须是对象，且序列化后不超过上限。"""
    if not isinstance(content, dict):
        raise AppError(ErrorCode.VALIDATION, "content 必须是对象")
    size = len(json.dumps(content, ensure_ascii=False).encode("utf-8"))
    if size > MAX_CONTENT_BYTES:
        raise AppError(ErrorCode.VALIDATION, "资源内容超过 100KB 上限")
    return content


@router.get("", response_model=ResourceListOut, summary="资源列表（按类型与范围过滤）")
def list_resources(
    kind: str = Query(default="", max_length=16),
    scope: str = Query(default="all", pattern="^(all|mine)$"),
    q: str = Query(default="", max_length=80),
    sort: str = Query(default="recent", pattern="^(recent|popular)$"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResourceListOut:
    """列出可见资源：team 全员可见，private 仅属主（管理员可见全部）。"""
    if kind and kind not in KINDS:
        raise AppError(ErrorCode.VALIDATION, "未知的资源类型")

    query = db.query(Resource)
    if kind:
        query = query.filter(Resource.kind == kind)
    if scope == "mine":
        query = query.filter(Resource.owner_id == user.id)
    elif user.role != "admin":
        query = query.filter(
            or_(Resource.visibility == "team", Resource.owner_id == user.id)
        )
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Resource.name.ilike(like), Resource.summary.ilike(like)))

    total = query.count()
    if sort == "popular":
        query = query.order_by(Resource.usage_count.desc(), Resource.updated_at.desc())
    else:
        query = query.order_by(Resource.updated_at.desc())
    rows = query.offset(offset).limit(limit).all()
    names = _owner_names(db, rows)
    return ResourceListOut(items=[_out(r, names, user) for r in rows], total=total)


@router.get("/plaza", response_model=PlazaOut, summary="资源广场（精选 + 热门 / 飙升 / 新品）")
def plaza(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlazaOut:
    """广场只统计团队可见资源；榜单口径在响应里由各字段名如实表达。"""
    base = db.query(Resource).filter(Resource.visibility == "team")
    total = base.count()
    week_ago = datetime.now(UTC) - timedelta(days=7)
    weekly = dict(
        db.query(ResourceUsageEvent.resource_id, func.count(ResourceUsageEvent.id))
        .filter(ResourceUsageEvent.created_at >= week_ago)
        .group_by(ResourceUsageEvent.resource_id)
        .all()
    )

    def board(rows: list[Resource]) -> list[PlazaRankItem]:
        names = _owner_names(db, rows)
        return [
            PlazaRankItem(
                id=r.id,
                kind=r.kind,
                name=r.name,
                summary=r.summary,
                owner_name=names.get(r.owner_id or "", ""),
                usage_count=r.usage_count,
                weekly_uses=int(weekly.get(r.id, 0)),
                created_at=_iso(r.created_at),
            )
            for r in rows
        ]

    popular = base.order_by(Resource.usage_count.desc(), Resource.updated_at.desc()).limit(PLAZA_LIMIT).all()
    featured = [r for r in popular if r.usage_count > 0][:6] or popular[:6]
    newest = base.order_by(Resource.created_at.desc()).limit(PLAZA_LIMIT).all()
    # 飙升榜：近 7 日有使用事件的资源，按事件数降序；没有事件时为空而不是复用累计值。
    rising_ids = [rid for rid, _n in sorted(weekly.items(), key=lambda kv: kv[1], reverse=True)[:PLAZA_LIMIT]]
    rising_rows = db.query(Resource).filter(Resource.id.in_(rising_ids)).all() if rising_ids else []
    order = {rid: idx for idx, rid in enumerate(rising_ids)}
    rising_rows.sort(key=lambda r: order.get(r.id, 999))

    return PlazaOut(
        total=total,
        featured=board(featured),
        popular=board(popular),
        rising=board(rising_rows),
        newest=board(newest),
    )


@router.post("", response_model=ResourceOut, summary="新建资源")
def create_resource(
    payload: ResourceCreateIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResourceOut:
    """新建资源：属主固定为当前用户，初始使用计数为 0。"""
    content = _normalize_content(payload.kind, payload.content)
    resource = Resource(
        kind=payload.kind,
        name=payload.name.strip(),
        summary=payload.summary.strip(),
        content=content,
        owner_id=user.id,
        visibility=payload.visibility,
    )
    if not resource.name:
        raise AppError(ErrorCode.VALIDATION, "资源名称不能为空")
    db.add(resource)
    db.flush()
    write_audit(
        db, request, user, "resource_create", "resource", resource.id,
        {"kind": resource.kind, "visibility": resource.visibility},
    )
    db.commit()
    db.refresh(resource)
    return _out(resource, {user.id: user.display_name or user.username}, user)


@router.get("/{resource_id}", response_model=ResourceOut, summary="资源详情")
def get_resource(
    resource_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResourceOut:
    """读取单个资源（含私有资源的属主校验）。"""
    resource = _get_readable(db, resource_id, user)
    return _out(resource, _owner_names(db, [resource]), user)


@router.patch("/{resource_id}", response_model=ResourceOut, summary="更新资源")
def update_resource(
    resource_id: str,
    payload: ResourceUpdateIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResourceOut:
    """更新名称 / 摘要 / 内容 / 可见性；只有属主与管理员可改。"""
    resource = _get_readable(db, resource_id, user)
    if not _can_edit(resource, user):
        raise AppError(ErrorCode.DENIED, "只有创建者可以修改该资源")
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise AppError(ErrorCode.VALIDATION, "资源名称不能为空")
        resource.name = name
    if payload.summary is not None:
        resource.summary = payload.summary.strip()
    if payload.content is not None:
        resource.content = _normalize_content(resource.kind, payload.content)
    if payload.visibility is not None:
        resource.visibility = payload.visibility
    resource.updated_at = datetime.now(UTC)
    write_audit(db, request, user, "resource_update", "resource", resource.id, {})
    db.commit()
    db.refresh(resource)
    return _out(resource, _owner_names(db, [resource]), user)


@router.delete("/{resource_id}", summary="删除资源")
def delete_resource(
    resource_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    """硬删除并级联清掉使用事件；克隆出来的副本不受影响（source_id 置空）。"""
    resource = _get_readable(db, resource_id, user)
    if not _can_edit(resource, user):
        raise AppError(ErrorCode.DENIED, "只有创建者可以删除该资源")
    db.query(Resource).filter(Resource.source_id == resource.id).update({Resource.source_id: None})
    db.query(ResourceUsageEvent).filter(ResourceUsageEvent.resource_id == resource.id).delete()
    write_audit(
        db, request, user, "resource_delete", "resource", resource.id,
        {"kind": resource.kind, "name": resource.name},
    )
    db.delete(resource)
    db.commit()
    return {"deleted": True}


@router.post("/{resource_id}/use", response_model=ResourceUseOut, summary="使用资源（计数）")
def use_resource(
    resource_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResourceUseOut:
    """记录一次使用：累加计数并写事件，供广场「飙升榜」统计近 7 日增量。"""
    resource = _get_readable(db, resource_id, user)
    resource.usage_count = (resource.usage_count or 0) + 1
    db.add(ResourceUsageEvent(resource_id=resource.id, user_id=user.id))
    db.commit()
    db.refresh(resource)
    return ResourceUseOut(id=resource.id, usage_count=resource.usage_count, content=resource.content or {})


@router.post("/{resource_id}/clone", response_model=ResourceOut, summary="基于此创建")
def clone_resource(
    resource_id: str,
    payload: ResourceCloneIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResourceOut:
    """复制一份归当前用户所有，``source_id`` 保留血缘，便于回溯来源。"""
    source = _get_readable(db, resource_id, user)
    name = (payload.name or f"{source.name} 副本").strip()
    if not name:
        raise AppError(ErrorCode.VALIDATION, "资源名称不能为空")
    clone = Resource(
        kind=source.kind,
        name=name,
        summary=source.summary,
        content=source.content or {},
        owner_id=user.id,
        visibility="private",
        source_id=source.id,
    )
    db.add(clone)
    db.flush()
    write_audit(
        db, request, user, "resource_clone", "resource", clone.id, {"source_id": source.id},
    )
    db.commit()
    db.refresh(clone)
    return _out(clone, {user.id: user.display_name or user.username}, user)
