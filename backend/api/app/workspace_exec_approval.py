"""远程命令执行的待审批队列。

``POST /api/workspaces/{id}/exec`` 不再直接执行命令，而是登记一条待审批请求，
由用户在页面上看过「目标主机 + 根目录 + 完整命令」后确认，才真正下发。

生产把审批单和执行结果放进 Redis，多副本可以确认同一次申请，重启后未过期的
申请仍然有效。Redis 不可用时退回进程内存：重启丢失等价于全部拒绝。
归属校验在这里做（``user_id`` + ``workspace_id`` 双匹配）。
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger("ai-eval.workspace_exec")

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
_runs: dict[str, dict] = {}
_redis = None
_redis_checked_at = 0.0
_memory_only = False
_REDIS_PREFIX = "ws:exec:"
_RUN_PREFIX = "ws:execrun:"
# 取出并校验归属。不匹配时不删除，避免误消费别人的审批单。
_POP_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then return false end
local ws, uid = string.match(raw, '^([^\\n]*)\\n([^\\n]*)\\n')
if ws ~= ARGV[1] or uid ~= ARGV[2] then return false end
redis.call('DEL', KEYS[1])
return raw
"""


def _purge_expired() -> None:
    now = time.monotonic()
    for approval_id in [key for key, item in _pending.items() if now - item.created_at > APPROVAL_TTL_S]:
        _pending.pop(approval_id, None)


def testing_use_memory(enabled: bool) -> bool:
    """单测强制走内存。返回之前的值，方便夹具恢复。"""
    global _memory_only
    previous = _memory_only
    _memory_only = enabled
    return previous


def try_enable_redis(url: str) -> None:
    """进程启动时连接 Redis。连不上就继续用内存，不阻断启动。"""
    global _redis, _redis_checked_at
    if _memory_only or not str(url or "").strip():
        return
    try:
        import redis
    except Exception:
        return
    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=0.4, socket_timeout=0.4, decode_responses=True)
        client.ping()
        _redis = client
    except Exception as exc:
        _redis = None
        logger.warning("远程命令审批 Redis 不可用 type=%s，退回进程内存", type(exc).__name__)
    _redis_checked_at = time.monotonic()


def _client():
    if _memory_only:
        return None
    return _redis


def redis_ready() -> bool | None:
    """就绪探针的 Redis 连通性：未启用返回 None，连不上返回 False。

    Redis 属可降级依赖（短票与审批单都有内存回退），因此该结果只作
    报告，不参与就绪判定。
    """
    client = _client()
    if client is None:
        return None
    try:
        client.ping()
        return True
    except Exception:
        return False


def _pack(item: PendingExec) -> str:
    body = json.dumps({
        "approval_id": item.approval_id,
        "workspace_id": item.workspace_id,
        "user_id": item.user_id,
        "command": item.command,
        "timeout_s": item.timeout_s,
        "host": item.host,
        "root": item.root,
    }, ensure_ascii=False)
    return f"{item.workspace_id}\n{item.user_id}\n{body}"


def _unpack(raw: str) -> PendingExec | None:
    try:
        _ws, _uid, body = raw.split("\n", 2)
        data = json.loads(body)
    except (ValueError, json.JSONDecodeError):
        return None
    return PendingExec(
        approval_id=str(data.get("approval_id") or ""),
        workspace_id=str(data.get("workspace_id") or ""),
        user_id=str(data.get("user_id") or ""),
        command=str(data.get("command") or ""),
        timeout_s=int(data.get("timeout_s") or 60),
        host=str(data.get("host") or ""),
        root=str(data.get("root") or ""),
        created_at=time.monotonic(),
    )


def _new_item(
    *, workspace_id: str, user_id: str, command: str, timeout_s: int, host: str, root: str
) -> PendingExec:
    return PendingExec(
        approval_id=uuid.uuid4().hex,
        workspace_id=workspace_id,
        user_id=user_id,
        command=command,
        timeout_s=timeout_s,
        host=host,
        root=root,
    )


def create(
    *, workspace_id: str, user_id: str, command: str, timeout_s: int, host: str, root: str
) -> PendingExec:
    """登记待审批命令。Redis 用 TTL；内存队列满时淘汰最旧一条。"""
    item = _new_item(
        workspace_id=workspace_id, user_id=user_id, command=command,
        timeout_s=timeout_s, host=host, root=root,
    )
    client = _client()
    if client is not None:
        client.set(f"{_REDIS_PREFIX}{item.approval_id}", _pack(item), ex=APPROVAL_TTL_S)
        return item
    with _lock:
        _purge_expired()
        if len(_pending) >= MAX_PENDING:
            oldest = min(_pending.values(), key=lambda pending: pending.created_at)
            _pending.pop(oldest.approval_id, None)
        _pending[item.approval_id] = item
        return item


def get(approval_id: str, *, workspace_id: str, user_id: str) -> PendingExec | None:
    """按 ID 取待审批命令；归属不符或已过期一律返回 None（不泄露存在性）。"""
    client = _client()
    if client is not None:
        raw = client.get(f"{_REDIS_PREFIX}{approval_id}")
        item = _unpack(raw) if raw else None
        if item is None or item.workspace_id != workspace_id or item.user_id != user_id:
            return None
        return item
    with _lock:
        _purge_expired()
        item = _pending.get(approval_id)
        if item is None or item.workspace_id != workspace_id or item.user_id != user_id:
            return None
        return item


def pop(approval_id: str, *, workspace_id: str, user_id: str) -> PendingExec | None:
    """取出并删除（确认或拒绝都用它，保证一条命令只能被执行一次）。"""
    client = _client()
    if client is not None:
        raw = client.eval(_POP_SCRIPT, 1, f"{_REDIS_PREFIX}{approval_id}", workspace_id, user_id)
        if not raw:
            return None
        return _unpack(raw)
    with _lock:
        _purge_expired()
        item = _pending.get(approval_id)
        if item is None or item.workspace_id != workspace_id or item.user_id != user_id:
            return None
        return _pending.pop(approval_id, None)


def begin_run(approval_id: str, *, workspace_id: str, user_id: str, timeout_s: int) -> None:
    """确认后立刻记下 running，请求线程可以返回。"""
    record = {
        "approval_id": approval_id,
        "workspace_id": workspace_id,
        "user_id": user_id,
        "status": "running",
        "timeout_s": timeout_s,
    }
    client = _client()
    if client is not None:
        client.set(
            f"{_RUN_PREFIX}{approval_id}",
            json.dumps(record, ensure_ascii=False),
            ex=max(60, int(timeout_s) + 120),
        )
        return
    with _lock:
        _runs[approval_id] = record


def finish_run(approval_id: str, *, workspace_id: str, user_id: str, payload: dict) -> None:
    """后台执行结束后写入结果。密码不进这份记录。"""
    record = {
        "approval_id": approval_id,
        "workspace_id": workspace_id,
        "user_id": user_id,
        **payload,
    }
    client = _client()
    if client is not None:
        client.set(f"{_RUN_PREFIX}{approval_id}", json.dumps(record, ensure_ascii=False), ex=900)
        return
    with _lock:
        _runs[approval_id] = record


def read_run(approval_id: str, *, workspace_id: str, user_id: str) -> dict | None:
    """读取执行状态。归属不符视为不存在。"""
    client = _client()
    if client is not None:
        raw = client.get(f"{_RUN_PREFIX}{approval_id}")
        if not raw:
            return None
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            return None
    else:
        with _lock:
            record = _runs.get(approval_id)
        if record is None:
            return None
    if record.get("workspace_id") != workspace_id or record.get("user_id") != user_id:
        return None
    return record


def clear() -> None:
    """测试或运维使用：清空进程内队列。"""
    with _lock:
        _pending.clear()
        _runs.clear()
