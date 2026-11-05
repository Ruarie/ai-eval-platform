"""远程命令执行的待审批队列。

``POST /api/workspaces/{id}/exec`` 不再直接执行命令，而是登记一条待审批请求，
由用户在页面上看过「目标主机 + 根目录 + 完整命令」后确认，才真正下发。

放在进程内（dict + TTL）的原因：
- 审批是短生命周期对象（默认 5 分钟过期），重启丢失等价于"全部拒绝"，语义安全；
- 单容器单进程部署（与适配层一致），不需要跨进程共享；
- 避免为了几个临时字段再加一张表和迁移。

归属校验在这里做（``user_id`` + ``workspace_id`` 双匹配），路由层不再重复判断。
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

APPROVAL_TTL_S = 300
MAX_PENDING = 200


@dataclass(slots=True)
class PendingExec:
    """一条待确认的远程命令。"""

    approval_id: str
    workspace_id: str
    user_id: str
    command: str
    timeout_s: int
    host: str
    root: str
    created_at: float = field(default_factory=time.monotonic)

    @property
    def expires_in_s(self) -> int:
        left = APPROVAL_TTL_S - (time.monotonic() - self.created_at)
        return max(0, int(left))


_lock = threading.Lock()
_pending: dict[str, PendingExec] = {}


def _purge_expired() -> None:
    now = time.monotonic()
    for approval_id in [key for key, item in _pending.items() if now - item.created_at > APPROVAL_TTL_S]:
        _pending.pop(approval_id, None)


def create(
    *, workspace_id: str, user_id: str, command: str, timeout_s: int, host: str, root: str
) -> PendingExec:
    """登记待审批命令；队列满时淘汰最旧一条（正常使用不会触达）。"""
    with _lock:
        _purge_expired()
        if len(_pending) >= MAX_PENDING:
            oldest = min(_pending.values(), key=lambda item: item.created_at)
            _pending.pop(oldest.approval_id, None)
        item = PendingExec(
            approval_id=uuid.uuid4().hex,
            workspace_id=workspace_id,
            user_id=user_id,
            command=command,
            timeout_s=timeout_s,
            host=host,
            root=root,
        )
        _pending[item.approval_id] = item
        return item


def get(approval_id: str, *, workspace_id: str, user_id: str) -> PendingExec | None:
    """按 ID 取待审批命令；归属不符或已过期一律返回 None（不泄露存在性）。"""
    with _lock:
        _purge_expired()
        item = _pending.get(approval_id)
        if item is None:
            return None
        if item.workspace_id != workspace_id or item.user_id != user_id:
            return None
        return item


def pop(approval_id: str, *, workspace_id: str, user_id: str) -> PendingExec | None:
    """取出并删除（确认或拒绝都用它，保证一条命令只能被执行一次）。"""
    with _lock:
        _purge_expired()
        item = _pending.get(approval_id)
        if item is None:
            return None
        if item.workspace_id != workspace_id or item.user_id != user_id:
            return None
        return _pending.pop(approval_id, None)


def clear() -> None:
    """测试或运维使用：清空队列。"""
    with _lock:
        _pending.clear()
