"""Worker 共用事件助手：WS 事件号分配。

事件号由 ``shared.event_seq`` 统一分配（会话行 ``last_event_id`` 计数器，
一条 ``UPDATE ... RETURNING`` 完成加锁与取号），与 api 侧 ``_next_event_id``
共用同一实现，避免两侧各自维护一套「锁行 + MAX 扫描」而在并发下撞号。
"""

from __future__ import annotations

import logging

from shared.event_seq import next_event_id, realign_event_seq
from shared.event_vocab import EVENT_VERSION
from sqlalchemy.exc import IntegrityError

from .db import SessionLocal
from .models import WsEvent

logger = logging.getLogger("worker.events")

# #4 D3：落库 payload 内嵌的词汇版本保留字段（与 api 侧 ws.py 同构；转发/回放剥离）
_EVENT_VERSION_KEY = "event_version"


def push_ws(session_id: str | None, event: str, payload: dict, task_id: str | None = None) -> None:
    """向会话事件表追加标准事件；task_id 独立成列，payload 仅存事件数据。

    #4 D3：写库 payload 注入 ``event_version`` 词汇版本保留字段（与 api
    ``_emit_persistent`` 同构），使 api 转发侧具备版本一致性校验面；
    版本常量来自 shared.event_vocab（词汇表单一事实源，禁止本地自持常量）。
    """
    if not session_id:
        return
    stored_payload = dict(payload)
    stored_payload[_EVENT_VERSION_KEY] = EVENT_VERSION
    db = SessionLocal()
    try:
        for attempt in range(2):
            event_id = next_event_id(db, session_id)
            if event_id is None:
                # 会话不存在（或已被清理）：不写事件，重连回放也查不到该会话。
                return
            db.add(
                WsEvent(
                    session_id=session_id,
                    task_id=task_id,
                    event_id=event_id,
                    event=event,
                    payload=stored_payload,
                )
            )
            try:
                db.commit()
                return
            except IntegrityError:
                # 计数器落后于历史（迁移窗口/人工导入）：对齐后重试一次。
                db.rollback()
                if attempt == 0:
                    realign_event_seq(db, session_id)
                    db.commit()
                    continue
                raise
    except Exception:
        # 事件推送失败不影响任务本体执行；重连后可经 REST 历史回放补齐
        db.rollback()
        logger.exception("push_ws failed (session=%s event=%s)", session_id, event)
    finally:
        db.close()
