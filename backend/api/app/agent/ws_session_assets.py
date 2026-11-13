"""会话附件归属：本会话用户消息引用过的 file_id 集合（资产溯源门禁用）。"""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.orm import Session

from ..models import Message


def session_owned_file_ids(db: Session, session_id: str) -> frozenset[str]:
    """本会话用户消息引用过的附件 ``file_id`` 集合。

    供资产溯源门禁（``feedback/rules.py``）使用：只对真正引用过的附件做归属
    校验，空集时门禁保持短路（既有语义）。注入 ``configurable["assets"]``。
    """

    try:
        rows = (
            db.query(Message.attachments)
            .filter(Message.session_id == session_id, Message.role == "user")
            .all()
        )
    except Exception:  # noqa: BLE001 —— 桩 DB/查询失败降级为空集（门禁短路=未注入语义）
        return frozenset()
    ids: set[str] = set()
    for (attachments,) in rows:
        for item in attachments or []:
            if not isinstance(item, Mapping):
                continue
            file_id = item.get("file_id")
            if isinstance(file_id, str) and file_id:
                ids.add(file_id)
    return frozenset(ids)
