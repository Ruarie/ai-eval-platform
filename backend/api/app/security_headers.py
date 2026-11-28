"""API 直连时补上与 Nginx 相同的最小安全响应头。

浏览器走 80 端口时由 Nginx 注入这些头。生产若把 :8000 暴露到宿主机，
请求不经过 Nginx，缺少 nosniff 与点击劫持限制。已有更严格的
Content-Security-Policy（附件下载的 sandbox）不覆盖。

不用 BaseHTTPMiddleware：它会把流式响应收进内存，附件下载不能被整文件缓存。
"""

from collections.abc import Awaitable, Callable

# 与 frontend/security-headers.conf 保持同一口径。
_HEADERS = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"SAMEORIGIN"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"geolocation=(), payment=(), usb=()"),
    (b"content-security-policy", b"frame-ancestors 'self'; base-uri 'self'"),
)


class SecurityHeadersMiddleware:
    """为还没有对应头的 HTTP 响应补上安全头。"""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                present = {name.lower() for name, _value in headers}
                headers.extend(item for item in _HEADERS if item[0] not in present)
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
