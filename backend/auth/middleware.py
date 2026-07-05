"""Per-request auth: read the Bearer token and stash the resolved user id in the
contextvar that `current_user()` reads.

Pure ASGI (not BaseHTTPMiddleware) so it never wraps the response in an anyio
cancel scope — that wrapper crashes SSE endpoints which spawn nested task groups
(learned the hard way with the request-size middleware, A2).
"""
from __future__ import annotations

from auth.deps import resolve_token_to_user_id, set_current_user_id


class AuthMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") == "http":
            token = None
            for k, v in scope.get("headers") or []:
                if k == b"authorization":
                    val = v.decode("latin-1")
                    if val[:7].lower() == "bearer ":
                        token = val[7:].strip()
                    break
            set_current_user_id(resolve_token_to_user_id(token))
        await self.app(scope, receive, send)
