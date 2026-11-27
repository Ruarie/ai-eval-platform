"""WebSocket 短票单次消费：Redis SET NX + TTL，进程内回退。

短票 JWT 仍由 ``security.create_token`` 签发；本模块只负责「同一 jti 只能
连上一次」。生产走 Redis，重启后未过期的 jti 仍不可复用。Redis 不可用时
回退进程内存（测试与无 Redis 的本地开发），并打脱敏轨迹，不得阻断整站。
"""

from __future__ import annotations

import threading
import time

from app.agent.log import agent_trace
from app.config import settings

_KEY_PREFIX = "ws:ticket:"
_MEMORY: dict[str, float] = {}
_LOCK = threading.Lock()
_MEMORY_CAP = 4096


def reset_memory_tickets() -> None:
    """测试夹具：清空进程内已消费记录。"""
    with _LOCK:
        _MEMORY.clear()


def _gc_memory(now: float) -> None:
    """丢掉过期项；超量时按过期时间淘汰一半。"""
    expired = [jti for jti, deadline in _MEMORY.items() if deadline <= now]
    for jti in expired:
        del _MEMORY[jti]
    if len(_MEMORY) <= _MEMORY_CAP:
        return
    ordered = sorted(_MEMORY.items(), key=lambda item: item[1])
    for jti, _deadline in ordered[: len(ordered) // 2]:
        _MEMORY.pop(jti, None)


def consume_memory_ticket(jti: str, ttl_seconds: int) -> bool:
    """进程内 SET NX + TTL；True 表示首次消费。"""
    now = time.monotonic()
    ttl = max(1, int(ttl_seconds))
    with _LOCK:
        _gc_memory(now)
        if jti in _MEMORY:
            return False
        _MEMORY[jti] = now + ttl
        return True


def _redis_consume(jti: str, ttl_seconds: int) -> bool | None:
    """Redis SET NX EX。成功返回是否首次写入；连接失败返回 None 以便回退。"""
    client = _get_redis_client()
    if client is None:
        return None
    try:
        ok = client.set(f"{_KEY_PREFIX}{jti}", "1", nx=True, ex=max(1, int(ttl_seconds)))
        return bool(ok)
    except Exception as exc:
        _mark_redis_unavailable()
        agent_trace(f"WS 短票 Redis 不可用 type={type(exc).__name__}，回退进程内存")
        return None


# 进程级共享客户端（内部自带连接池）：旧实现每次握手都新建连接池，重连高峰时
# 反复建连；Redis 故障时每条连接还要各自阻塞约 0.8s。现在复用同一个客户端，
# 故障后冷却 _REDIS_RETRY_COOLDOWN_S 秒内直接走进程内存回退，不再逐次探测。
_REDIS_RETRY_COOLDOWN_S = 30.0
_REDIS_CLIENT = None
_REDIS_UNAVAILABLE_UNTIL = 0.0
_REDIS_LOCK = threading.Lock()


def _mark_redis_unavailable() -> None:
    """记录 Redis 故障并进入冷却期；冷却结束后下一次调用重新建连。"""
    global _REDIS_CLIENT, _REDIS_UNAVAILABLE_UNTIL
    with _REDIS_LOCK:
        client, _REDIS_CLIENT = _REDIS_CLIENT, None
        _REDIS_UNAVAILABLE_UNTIL = time.monotonic() + _REDIS_RETRY_COOLDOWN_S
    if client is not None:
        try:
            client.close()
        except Exception as exc:
            agent_trace(f"WS 短票 Redis 关闭连接失败 type={type(exc).__name__}")


def _get_redis_client():
    """惰性创建共享客户端；冷却期内或 redis 库缺失时返回 None。"""
    global _REDIS_CLIENT
    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT
    with _REDIS_LOCK:
        if _REDIS_CLIENT is not None:
            return _REDIS_CLIENT
        if time.monotonic() < _REDIS_UNAVAILABLE_UNTIL:
            return None
        try:
            import redis
        except Exception:
            return None
        try:
            _REDIS_CLIENT = redis.Redis.from_url(
                settings.redis_url,
                socket_connect_timeout=0.4,
                socket_timeout=0.4,
                decode_responses=True,
            )
        except Exception as exc:
            agent_trace(f"WS 短票 Redis 初始化失败 type={type(exc).__name__}，回退进程内存")
            return None
        return _REDIS_CLIENT


def reset_redis_client() -> None:
    """测试夹具：丢弃共享客户端并清除冷却状态。"""
    global _REDIS_CLIENT, _REDIS_UNAVAILABLE_UNTIL
    with _REDIS_LOCK:
        _REDIS_CLIENT = None
        _REDIS_UNAVAILABLE_UNTIL = 0.0


def consume_ws_jti(jti: str, ttl_seconds: int) -> bool:
    """消费一次性 jti：Redis 优先，不可用则进程内存。True=首次放行。"""
    token = str(jti or "").strip()
    if not token:
        return False
    redis_result = _redis_consume(token, ttl_seconds)
    if redis_result is not None:
        return redis_result
    return consume_memory_ticket(token, ttl_seconds)


def ttl_from_jwt_payload(payload: dict) -> int:
    """按 JWT exp 剩余秒数设置 Redis TTL，下限 1 秒、上限短票配置。"""
    cap = max(1, int(settings.ws_ticket_expire_minutes) * 60)
    exp = payload.get("exp")
    remaining: int | None = None
    if isinstance(exp, int | float):
        remaining = int(exp - time.time())
    elif hasattr(exp, "timestamp"):
        remaining = int(exp.timestamp() - time.time())
    if remaining is None:
        return cap
    return max(1, min(cap, remaining))
