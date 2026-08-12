"""Browser security response headers for the Server-hosted Console (WB-534)."""
from __future__ import annotations

from collections.abc import MutableSequence

from starlette.types import ASGIApp, Message, Receive, Scope, Send


_CSP = "; ".join(
    (
        "default-src 'self'",
        "base-uri 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self' data:",
        "connect-src 'self' https: wss:",
    )
)

_BASE_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"content-security-policy", _CSP.encode("ascii")),
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=(), usb=()"),
)
_HSTS = (b"strict-transport-security", b"max-age=31536000; includeSubDomains")


class SecurityHeadersMiddleware:
    """Apply a fail-safe browser baseline without forcing HSTS on local HTTP."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers: MutableSequence[tuple[bytes, bytes]] = message.setdefault("headers", [])
                existing = {name.lower() for name, _value in headers}
                for name, value in _BASE_HEADERS:
                    if name not in existing:
                        headers.append((name, value))
                if scope.get("scheme") == "https" and _HSTS[0] not in existing:
                    headers.append(_HSTS)
            await send(message)

        await self.app(scope, receive, send_with_headers)
