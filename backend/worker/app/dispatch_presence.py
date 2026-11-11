"""把本进程登记到调度星图，并在执行期间持续刷新心跳。

领取仍按任务表 SKIP LOCKED，不读取节点权重。心跳只说明这个进程是否存活、
是否正在执行，以及管理员是否把它标成排空或离线。排空和离线时不再领新任务。
"""

from __future__ import annotations

import logging
import os
import socket
from datetime import UTC, datetime
from threading import Event, Lock, Thread

from .db import SessionLocal
from .models import DispatchWorker

logger = logging.getLogger("worker.presence")

# 调度页把超过 30 秒没有心跳的 idle/busy 显示为离线，因此刷新间隔必须更短。
PRESENCE_INTERVAL_SECONDS = 10
NODE_CAPS = ["testcase"]
_GOVERNED_STATES = {"offline", "draining", "restarting"}


def node_id() -> str:
    """同一容器重启后仍用同一个节点 ID，避免星图留下一串失联副本。"""
    configured = os.environ.get("WORKER_NODE_ID", "").strip()
    raw = configured or socket.gethostname() or "worker-1"
    return raw[:64]


def node_name() -> str:
    """展示名可单独配置；缺省时带上节点 ID，便于多副本区分。"""
    configured = os.environ.get("WORKER_NODE_NAME", "").strip()
    raw = configured or f"用例 Worker {node_id()}"
    return raw[:128]


class Presence:
    """后台刷新调度节点心跳，并记录当前是否正在执行。"""

    def __init__(self) -> None:
        self._lock = Lock()
        self._busy = False
        self._task_id: str | None = None
        self._stopped = Event()
        self._thread: Thread | None = None
        self._identity = node_id()

    def start(self) -> None:
        """先写一次心跳再进后台循环，避免进程刚启动的空窗被显示成离线。"""
        self.beat()
        self._thread = Thread(target=self._loop, name="dispatch-presence", daemon=True)
        self._thread.start()

    def set_activity(self, *, busy: bool, task_id: str | None) -> None:
        """执行开始或结束时立即刷新，不必等到下一拍心跳。"""
        with self._lock:
            self._busy = busy
            self._task_id = task_id
        self.beat()

    def allows_claim(self) -> bool:
        """排空和离线维护不再领新任务。心跳表暂时读不到时仍允许领取，避免停掉用例生成。"""
        try:
            return claim_allowed(self._identity)
        except Exception:
            logger.warning("调度节点状态读取失败，本轮仍按队列领取")
            return True

    def take_idle_restart(self) -> bool:
        """本节点被管理员标记为 restarting 时改回 idle 并让主循环退出。

        主循环持有的是 :class:`Presence` 实例，必须在类上暴露该动作；直接调用
        模块级函数会让主循环每轮抛 AttributeError 而永不领任务。
        """
        try:
            return take_idle_restart(self._identity)
        except Exception:
            logger.warning("调度节点重启状态读取失败 node=%s", self._identity)
            return False

    def beat(self) -> None:
        """把当前活动写回调度节点。数据库短暂失败只记日志，不打断主循环。"""
        with self._lock:
            busy = self._busy
            task_id = self._task_id
        try:
            write_presence(self._identity, node_name(), busy, task_id)
        except Exception:
            logger.warning("调度节点心跳写入失败 node=%s", self._identity)

    def _loop(self) -> None:
        while not self._stopped.wait(PRESENCE_INTERVAL_SECONDS):
            self.beat()


def claim_allowed(worker_node_id: str) -> bool:
    """没有登记行时允许领取；显式排空、离线或等待重启则拒绝。"""
    with SessionLocal() as db:
        row = db.query(DispatchWorker).filter(DispatchWorker.id == worker_node_id).first()
        if row is None:
            return True
        return row.state not in _GOVERNED_STATES


def take_idle_restart(worker_node_id: str) -> bool:
    """空闲且被标成 restarting 时改回 idle，并让主循环退出以便容器重新拉起。

    先改回 idle，避免新进程起来后仍看到 restarting 而立刻再次退出。
    """
    with SessionLocal() as db:
        row = db.query(DispatchWorker).filter(DispatchWorker.id == worker_node_id).first()
        if row is None or row.state != "restarting":
            return False
        row.state = "idle"
        row.current_task_id = None
        db.commit()
        return True


def write_presence(worker_node_id: str, name: str, busy: bool, task_id: str | None) -> None:
    """登记或刷新本进程。已有的权重、能力和排空/离线状态不被心跳改写。"""
    now = datetime.now(UTC)
    desired = "busy" if busy else "idle"
    load = 100.0 if busy else 0.0
    with SessionLocal() as db:
        row = db.query(DispatchWorker).filter(DispatchWorker.id == worker_node_id).first()
        if row is None:
            db.add(
                DispatchWorker(
                    id=worker_node_id,
                    name=name,
                    caps=list(NODE_CAPS),
                    state=desired,
                    weight=100,
                    load_percent=load,
                    current_task_id=task_id,
                    last_heartbeat_at=now,
                )
            )
        else:
            row.last_heartbeat_at = now
            row.load_percent = load
            row.current_task_id = task_id
            if row.state not in _GOVERNED_STATES:
                row.state = desired
        db.commit()
