"""Route-aware ASGI request-body hard limits for raw Server ingress (WB-546)."""
from __future__ import annotations

import re

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from config import settings


SIGNED_INGRESS_MAX_BYTES = 64 * 1024
_WEBHOOK_PATH = re.compile(r"^/api/webhooks/automations/[^/]+$")
_ASSET_PART_PATH = re.compile(r"^/api/assets/uploads/[^/]+/parts/[0-9]+$")


def _body_limit(scope: Scope) -> int | None:
    path = str(scope.get("path") or "")
    method = str(scope.get("method") or "").upper()
    if method == "POST" and (path == "/api/relay/events" or _WEBHOOK_PATH.fullmatch(path)):
        return SIGNED_INGRESS_MAX_BYTES
    if method == "PUT" and _ASSET_PART_PATH.fullmatch(path):
        return settings.ASSET_UPLOAD_PART_BYTES
    return None


class RawIngressBodyLimitMiddleware:
    """Bound raw ingress before ``Request.body()`` can buffer an unbounded stream."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or (limit := _body_limit(scope)) is None:
            await self.app(scope, receive, send)
            return

        headers = {name.lower(): value for name, value in scope.get("headers", [])}
        declared = headers.get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            await JSONResponse({"detail": "request body too large"}, status_code=413)(
                scope, receive, send,
            )
            return

        messages: list[Message] = []
        received = 0
        while True:
            message = await receive()
            messages.append(message)
            if message.get("type") != "http.request":
                break
            received += len(message.get("body") or b"")
            if received > limit:
                await JSONResponse({"detail": "request body too large"}, status_code=413)(
                    scope, receive, send,
                )
                return
            if not message.get("more_body", False):
                break

        index = 0

        async def replay_receive() -> Message:
            nonlocal index
            if index < len(messages):
                message = messages[index]
                index += 1
                return message
            return await receive()

        await self.app(scope, replay_receive, send)
