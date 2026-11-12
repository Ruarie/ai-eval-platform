"""进程级 WS 事件轮询：一条查询覆盖所有会话，再经连接 Hub 广播。

此前每条连接各自轮询 ``ws_events``（空闲时 0.5 QPS/连接），在线连接越多打库
越多；现在进程内只有一个轮询器，按全局自增主键 ``id`` 游标增量读取，交给
``SESSION_CONNECTION_HUB`` 按会话分发——每条连接的游标、回放排队与背压语义
保持不变（Hub 内部仍按连接 cursor 去重）。

多副本部署时每个进程各自轮询全表，同一事件只广播给本进程登记的连接，
不会重复投递给同一客户端。
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Any

from ..config import settings
from ..db import SessionLocal
from ..errors import ErrorCode
from ..models import WsEvent
from ..routers import ws as ws_router
from ..session_connections import SESSION_CONNECTION_HUB

logger = logging.getLogger("ai-eval.ws-poller")

# 轮询间隔：只影响 Worker 直产事件（进度/报告/错误）的可见延迟。
POLL_INTERVAL_S = 0.3
# 单批上限：一次积压不会把整表读进内存；剩余部分下一轮继续。
BATCH_SIZE = 200


def _max_row_id() -> int:
    """当前最大行号：启动时作为游标，避免把历史事件整表重播一遍。"""
    db = SessionLocal()
    try:
        row = db.query(WsEvent.id).order_by(WsEvent.id.desc()).first()
        return int(row[0]) if row else 0
    finally:
        db.close()


def _fetch(after_id: int) -> list[dict[str, Any]]:
    """按全局行号增量取 Worker 直产事件；同步查询由调用方放进线程池。"""
    db = SessionLocal()
    try:
        rows = (
            db.query(
                WsEvent.id,
                WsEvent.session_id,
                WsEvent.task_id,
                WsEvent.event_id,
                WsEvent.event,
                WsEvent.payload,
                WsEvent.ts,
            )
            .filter(
                WsEvent.id > after_id,
                WsEvent.event.in_(ws_router._WORKER_FORWARD_EVENTS),
            )
            .order_by(WsEvent.id)
            .limit(BATCH_SIZE)
            .all()
        )
        return [
            {
                "row_id": int(row[0]),
                "session_id": row[1],
                "task_id": row[2],
                "event_id": int(row[3]),
                "event": row[4],
                "payload": row[5] or {},
                "ts": row[6],
            }
            for row in rows
        ]
    finally:
        db.close()


class WsEventPoller:
    """单进程内唯一的 ws_events 轮询器。"""

    def __init__(self) -> None:
        self._cursor = 0
        self._task: asyncio.Task[None] | None = None
        # strict 模式下同一条未契约事件只落一次 error，避免刷屏。
        self._rejected: set[tuple[str, str, str | None]] = set()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        try:
            self._cursor = _max_row_id()
        except Exception:  # noqa: BLE001 - 启动期读不到就从头扫描，不影响正确性
            logger.warning("WS 事件轮询初始化游标失败，从 0 开始", exc_info=True)
            self._cursor = 0
        self._task = asyncio.create_task(self._run(), name="ws-event-poller")
        logger.info("WS 事件轮询已启动 cursor=%s", self._cursor)

    async def close(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(POLL_INTERVAL_S)
            # 没有任何在线连接时不查库：v1 是历史协议，新会话都走 v2，
            # 空跑轮询只会给数据库增加无意义负载。
            if not SESSION_CONNECTION_HUB.has_connections():
                continue
            try:
                rows = await asyncio.to_thread(_fetch, self._cursor)
            except Exception:  # noqa: BLE001 - 单轮查询失败不应终止轮询
                logger.info("WS 事件轮询查询失败", exc_info=True)
                continue
            if not rows:
                continue
            logger.info("WS 事件轮询取到 %d 条 cursor=%s", len(rows), self._cursor)
            self._cursor = max(self._cursor, rows[-1]["row_id"])
            for row in rows:
                try:
                    await self._dispatch(row)
                except Exception:  # noqa: BLE001 - 单条分发失败不影响后续事件
                    logger.info(
                        "WS 事件分发失败 event=%s session=%s",
                        row.get("event"),
                        row.get("session_id"),
                        exc_info=True,
                    )

    async def _dispatch(self, row: dict[str, Any]) -> None:
        if not ws_router._should_forward_worker_event(row["event"], row["task_id"]):
            return
        payload, version = ws_router._split_event_version(row["payload"])
        reason = ws_router._event_vocab_mismatch(row["event"], version)
        if reason is not None:
            await self._reject(row, version, reason)
            return
        frame = ws_router._frame(
            row["session_id"],
            row["event"],
            row["event_id"],
            payload,
            task_id=row["task_id"],
            ts=row["ts"],
        )
        await SESSION_CONNECTION_HUB.broadcast_event(row["session_id"], frame)

    async def _reject(
        self, row: dict[str, Any], version: str | None, reason: str
    ) -> None:
        """未契约事件：默认告警跳过；strict 模式落 error 并只报一次。"""
        if not settings.event_vocab_strict:
            logger.warning(
                "Agent WS 转发跳过未契约事件 event=%s version=%s reason=%s",
                row["event"],
                version,
                reason,
            )
            return
        key = (row["session_id"], row["event"], version)
        if key in self._rejected:
            return
        self._rejected.add(key)
        logger.error(
            "Agent WS fail-closed 拒绝未契约事件 event=%s version=%s", row["event"], version
        )
        db = SessionLocal()
        try:
            await ws_router._emit_persistent(
                db,
                None,
                ws_router._ConnectionState(),
                row["session_id"],
                "error",
                {"code": ErrorCode.INTERNAL.value, "message": "收到未契约的 Worker 事件，已拒绝转发"},
            )
        finally:
            db.close()


# 单进程唯一实例；由 main.lifespan 启动与关闭。
WS_EVENT_POLLER = WsEventPoller()
