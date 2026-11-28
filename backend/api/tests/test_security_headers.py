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

    app = Starlette(routes=[Route("/plain", plain), Route("/file", sandboxed)])
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
