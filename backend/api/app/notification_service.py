"""站内通知服务（N-08 MVP）。

- 通知只保存标题、正文、站内链接和去重键，不保存密钥/上游原文；
- 同一用户同一 `dedupe_key` 只保留一条，避免 Worker 重试刷屏；
- 列表/未读/已读全部按当前用户隔离。
"""

from __future__ import annotations

import time

from sqlalchemy.orm import Session

from .models import Notification, utcnow
from .schemas import NotificationListOut, NotificationOut

MAX_TITLE = 120
MAX_BODY = 1000
MAX_LINK = 500


def add_notification(
    db: Session,
    *,
    user_id: str,
    type: str,
    title: str,
    body: str = "",
    link: str = "",
    dedupe_key: str = "",
) -> Notification | None:
    """追加通知；同用户同去重键已存在时返回 None。"""
    key = (dedupe_key or f"{type}:{time.time_ns()}")[:160]
    exists = (
        db.query(Notification.id)
        .filter(Notification.user_id == user_id, Notification.dedupe_key == key)
        .first()
    )
    if exists:
        return None
    row = Notification(
        user_id=user_id,
        type=str(type or "system")[:40],
        title=str(title or "")[:MAX_TITLE],
        body=str(body or "")[:MAX_BODY],
        link=str(link or "")[:MAX_LINK],
        dedupe_key=key,
    )
    db.add(row)
    return row


def _out(row: Notification) -> NotificationOut:
    """ORM 通知转响应。"""
    return NotificationOut(
        id=row.id,
        type=row.type,
        title=row.title,
        body=row.body or "",
        link=row.link or "",
        read_at=row.read_at,
        created_at=row.created_at,
    )


def _base(db: Session, user_id: str):
    """当前用户的通知查询。"""
    return db.query(Notification).filter(Notification.user_id == user_id)


def unread_count(db: Session, user_id: str) -> int:
    """未读数量。"""
    return _base(db, user_id).filter(Notification.read_at.is_(None)).count()


def list_notifications(
    db: Session,
    user_id: str,
    *,
    unread_only: bool = False,
    offset: int = 0,
    limit: int = 20,
) -> NotificationListOut:
    """按创建时间倒序分页。"""
    query = _base(db, user_id)
    if unread_only:
        query = query.filter(Notification.read_at.is_(None))
    total = query.count()
    rows = (
        query.order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return NotificationListOut(
        items=[_out(row) for row in rows],
        total=total,
        unread=unread_count(db, user_id),
        offset=offset,
        limit=limit,
    )


def mark_read(db: Session, user_id: str, notification_id: str) -> bool:
    """标记单条已读；不存在或不属于当前用户返回 False。"""
    row = (
        _base(db, user_id)
        .filter(Notification.id == notification_id)
        .first()
    )
    if not row:
        return False
    if row.read_at is None:
        row.read_at = utcnow()
        db.commit()
    return True


def mark_all_read(db: Session, user_id: str) -> int:
    """全部标为已读，返回影响条数。"""
    count = (
        _base(db, user_id)
        .filter(Notification.read_at.is_(None))
        .update({Notification.read_at: utcnow()}, synchronize_session=False)
    )
    db.commit()
    return int(count or 0)
