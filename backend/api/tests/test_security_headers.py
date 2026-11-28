"""安全响应头不依赖完整应用启动，也不覆盖已有的更严格 CSP。"""

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.security_headers import SecurityHeadersMiddleware


def _app() -> Starlette:
    async def plain(_request):
        return PlainTextResponse("ok")

    async def sandboxed(_request):
        return PlainTextResponse("file", headers={"Content-Security-Policy": "sandbox"})

    async def write(_request):
        return PlainTextResponse("saved")

    app = Starlette(routes=[
        Route("/plain", plain),
        Route("/file", sandboxed),
        Route("/write", write, methods=["POST"]),
    ])
    app.add_middleware(SecurityHeadersMiddleware)
    return app


def test_security_headers_are_added_when_missing():
    response = TestClient(_app()).get("/plain")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "SAMEORIGIN"
    assert "frame-ancestors" in response.headers["content-security-policy"]


def test_existing_sandbox_csp_is_kept():
    response = TestClient(_app()).get("/file")
    assert response.headers["content-security-policy"] == "sandbox"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_write_without_origin_and_same_host_are_allowed():
    client = TestClient(_app())
    assert client.post("/write").status_code == 200
    assert client.post("/write", headers={"Origin": "http://testserver"}).status_code == 200
    # 8443 的 Origin 带端口，反代 Host 不带端口，仍应视为本站。
    assert client.post("/write", headers={"Origin": "http://testserver:8443"}).status_code == 200


def test_cross_site_write_is_rejected():
    response = TestClient(_app()).post("/write", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert response.json()["code"] == "UNAUTHORIZED"
    assert response.headers["x-content-type-options"] == "nosniff"
    # 读请求不拦截，避免健康检查和普通链接被 Origin 误伤。
    assert TestClient(_app()).get("/plain", headers={"Origin": "https://evil.example"}).status_code == 200
