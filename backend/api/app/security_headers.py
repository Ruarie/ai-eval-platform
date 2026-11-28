"""API 直连时补上与 Nginx 相同的最小安全响应头。

浏览器走 80 端口时由 Nginx 注入这些头。生产若把 :8000 暴露到宿主机，
请求不经过 Nginx，缺少 nosniff 与点击劫持限制。已有更严格的
Content-Security-Policy（附件下载的 sandbox）不覆盖。

不用 BaseHTTPMiddleware：它会把流式响应收进内存，附件下载不能被整文件缓存。

写请求如果带了 Origin，必须是当前主机或 CORS 白名单。浏览器跨站提交会带上
别人的 Origin；不带 Origin 的调用（测试客户端、服务端）保持可用。
"""

from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from .config import settings

# 与 frontend/security-headers.conf 保持同一口径。
_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"SAMEORIGIN"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"geolocation=(), payment=(), usb=()"),
    (b"content-security-policy", b"frame-ancestors 'self'; base-uri 'self'"),
)
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_REJECT_BODY = '{"code":"UNAUTHORIZED","message":"请求来源不被允许"}'.encode()


class SecurityHeadersMiddleware:
    """为还没有对应头的 HTTP 响应补上安全头。"""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if not _origin_allowed(scope):
            await _reject(send)
            return

        async def send_with_headers(message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                present = {name.lower() for name, _value in headers}
                headers.extend(item for item in _HEADERS if item[0] not in present)
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _header(scope, name: bytes) -> str:
    """读取单个请求头。ASGI 头名是小写字节。"""
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            return value.decode("latin-1")
    return ""


def _origin_allowed(scope) -> bool:
    """写请求的 Origin 必须是当前站点或已配置的前端地址。"""
    if scope.get("method", "GET").upper() not in _UNSAFE_METHODS:
        return True
    origin = _header(scope, b"origin").strip()
    if not origin or origin == "null":
        # 没有 Origin 的调用方不是浏览器跨站表单；null 来自沙箱页，拒绝。
        return origin != "null"
    if origin in settings.cors_origin_list:
        return True
    host = _header(scope, b"host")
    scheme = scope.get("scheme") or "http"
    if origin == f"{scheme}://{host}":
        return True
    parsed = urlsplit(origin)
    hostname = host.split(":", 1)[0]
    # Nginx 的 $host 不带端口，8443 上的浏览器 Origin 会带上端口。
    return bool(hostname) and parsed.scheme == scheme and parsed.hostname == hostname


async def _reject(send) -> None:
    """按统一错误体拒绝，并带上安全头。"""
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(_REJECT_BODY)).encode()),
        *_HEADERS,
    ]
    await send({"type": "http.response.start", "status": 403, "headers": headers})
    await send({"type": "http.response.body", "body": _REJECT_BODY})
