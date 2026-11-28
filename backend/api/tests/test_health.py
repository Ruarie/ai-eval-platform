"""健康检查接口单测（M0 空跑，不依赖数据库）。"""

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app


def test_health():
    # 不进入 with 上下文，避免触发 lifespan 里的数据库引导逻辑
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"]
    # :8000 直连不经过 Nginx，API 自己也要带上同一组最小安全头。
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "SAMEORIGIN"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "frame-ancestors" in resp.headers["content-security-policy"]


class _BrokenSession:
    """连接失败替身：``/api/ready`` 必须在数据库不可用时返回 503。"""

    def __enter__(self):
        raise RuntimeError("database down")

    def __exit__(self, *_exc):
        return False


def test_ready_reports_database_failure(monkeypatch):
    """数据库不可用时就绪探针返回 503，避免编排层把流量导进坏副本。"""
    monkeypatch.setattr(main_module, "SessionLocal", lambda: _BrokenSession())
    client = TestClient(app)
    resp = client.get("/api/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "unavailable"
    assert body["database"] == "unavailable"


def test_ready_ok_when_database_available(monkeypatch):
    """数据库可用时就绪探针返回 200，Redis 仅作附加信息。"""

    class _FakeResult:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def execute(self, statement) -> None:
            self.calls.append(str(statement))

    class _FakeSession(_FakeResult):
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    session = _FakeSession()
    monkeypatch.setattr(main_module, "SessionLocal", lambda: session)
    monkeypatch.setattr(
        "app.workspace_exec_approval.redis_ready", lambda: True, raising=False
    )
    client = TestClient(app)
    resp = client.get("/api/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["redis"] == "ok"
    assert session.calls == ["SELECT 1"]
