"""WS 短票 Redis / 内存单次消费回归。"""

from app import ws_tickets


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def set(self, name, value, nx=False, ex=None):
        if nx and name in self.store:
            return False
        self.store[name] = value
        return True


def test_memory_ticket_single_use(monkeypatch) -> None:
    """无 Redis 时同一 jti 只能消费一次。"""
    monkeypatch.setattr(ws_tickets, "_redis_consume", lambda *_a, **_k: None)
    ws_tickets.reset_memory_tickets()
    assert ws_tickets.consume_ws_jti("jti-1", 60) is True
    assert ws_tickets.consume_ws_jti("jti-1", 60) is False
    assert ws_tickets.consume_ws_jti("", 60) is False


def test_redis_set_nx_rejects_second_use(monkeypatch) -> None:
    """Redis SET NX 成功后第二次消费失败。"""
    fake = _FakeRedis()

    def fake_redis(jti: str, ttl_seconds: int) -> bool | None:
        return bool(fake.set(f"ws:ticket:{jti}", "1", nx=True, ex=ttl_seconds))

    monkeypatch.setattr(ws_tickets, "_redis_consume", fake_redis)
    assert ws_tickets.consume_ws_jti("once", 30) is True
    assert ws_tickets.consume_ws_jti("once", 30) is False


def test_ttl_from_jwt_payload_uses_remaining_seconds(monkeypatch) -> None:
    """TTL 夹在 1 秒与短票有效期之间。"""
    monkeypatch.setattr(ws_tickets.settings, "ws_ticket_expire_minutes", 5)
    monkeypatch.setattr(ws_tickets.time, "time", lambda: 1_000_000.0)
    assert ws_tickets.ttl_from_jwt_payload({"exp": 1_000_000 + 12}) == 12
    assert ws_tickets.ttl_from_jwt_payload({"exp": 1_000_000 - 10}) == 1
    assert ws_tickets.ttl_from_jwt_payload({}) == 300


class _CountingRedisFactory:
    """记录 from_url 调用次数，可切换为抛连接错误。"""

    def __init__(self) -> None:
        self.created = 0
        self.fail = False
        self.closed = 0
        factory = self

        class _Client(_FakeRedis):
            def set(self, name, value, nx=False, ex=None):
                if factory.fail:
                    raise ConnectionError("down")
                return super().set(name, value, nx=nx, ex=ex)

            def close(self) -> None:
                factory.closed += 1

        self._client_cls = _Client

    def from_url(self, *_a, **_k):
        self.created += 1
        return self._client_cls()


def _install_factory(monkeypatch) -> _CountingRedisFactory:
    import redis

    factory = _CountingRedisFactory()
    monkeypatch.setattr(redis.Redis, "from_url", staticmethod(factory.from_url))
    ws_tickets.reset_redis_client()
    ws_tickets.reset_memory_tickets()
    return factory


def test_redis_client_is_shared_across_consumes(monkeypatch) -> None:
    """多次握手复用同一个客户端，不再每次新建连接池。"""
    factory = _install_factory(monkeypatch)
    try:
        assert ws_tickets.consume_ws_jti("a", 30) is True
        assert ws_tickets.consume_ws_jti("b", 30) is True
        assert ws_tickets.consume_ws_jti("a", 30) is False
        assert factory.created == 1
    finally:
        ws_tickets.reset_redis_client()


def test_redis_failure_enters_cooldown_and_falls_back(monkeypatch) -> None:
    """Redis 故障后冷却期内不再建连，直接走进程内存；冷却结束后重新建连。"""
    factory = _install_factory(monkeypatch)
    clock = {"now": 1000.0}
    monkeypatch.setattr(ws_tickets.time, "monotonic", lambda: clock["now"])
    try:
        factory.fail = True
        assert ws_tickets.consume_ws_jti("x", 30) is True  # Redis 失败 → 内存回退放行
        assert factory.created == 1 and factory.closed == 1
        assert ws_tickets.consume_ws_jti("x", 30) is False  # 冷却期内走内存，仍单次
        assert ws_tickets.consume_ws_jti("y", 30) is True
        assert factory.created == 1  # 冷却期内没有再次建连

        factory.fail = False
        clock["now"] += ws_tickets._REDIS_RETRY_COOLDOWN_S + 1
        assert ws_tickets.consume_ws_jti("z", 30) is True
        assert factory.created == 2  # 冷却结束后重新建连
    finally:
        ws_tickets.reset_redis_client()
