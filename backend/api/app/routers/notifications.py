"""站内通知中心路由（N-08 MVP）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..errors import AppError, ErrorCode
from ..models import User
from ..notification_service import (
    list_notifications,
    mark_all_read,
    mark_read,
    unread_count,
)
from ..schemas import NotificationListOut, NotificationUnreadOut

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListOut, summary="列出当前成员通知")
def get_notifications(
    unread: bool = Query(default=False),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationListOut:
    """按创建时间倒序；`unread=true` 只看未读。"""
    return list_notifications(db, user.id, unread_only=unread, offset=offset, limit=limit)


@router.get("/unread-count", response_model=NotificationUnreadOut, summary="未读通知数")
def get_unread_count(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationUnreadOut:
    """顶栏徽标只取计数。"""
    return NotificationUnreadOut(unread=unread_count(db, user.id))


@router.post("/{notification_id}/read", response_model=NotificationUnreadOut, summary="标记单条已读")
def read_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationUnreadOut:
    """只能标记自己的通知。"""
    if not mark_read(db, user.id, notification_id):
        raise AppError(ErrorCode.NOT_FOUND, "通知不存在")
    return NotificationUnreadOut(unread=unread_count(db, user.id))


@router.post("/read-all", response_model=NotificationUnreadOut, summary="全部标为已读")
def read_all_notifications(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationUnreadOut:
    """返回清零后的未读数。"""
    mark_all_read(db, user.id)
    return NotificationUnreadOut(unread=0)
