"""Per-request auth: read the Bearer token and stash the resolved user id in the
contextvar that `current_user()` reads.

Pure ASGI (not BaseHTTPMiddleware) so it never wraps the response in an anyio
cancel scope — that wrapper crashes SSE endpoints which spawn nested task groups
(learned the hard way with the request-size middleware, A2).

Server 桥（WB-062）：本地缓存未命中且已接 Server 时，把 token 交给 Server 校验。那是**阻塞的网络调用**，
所以丢进工作线程（anyio.to_thread），绝不在事件循环里跑（WB-002）。无 token 时使用匿名访客
作用域；它不是本地账号。已缓存的 Server token 在断网时仍可本地解析。
"""
from __future__ import annotations

import anyio

import server_client
from auth.deps import resolve_token_to_user_id, resolve_via_server, set_current_user_id


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
            uid = resolve_token_to_user_id(token)  # 本地缓存，同步、快
            if uid is None and token and server_client.server_enabled():
                # 未命中且已接 Server：阻塞的 Server 校验丢到工作线程，不占事件循环。
                uid = await anyio.to_thread.run_sync(resolve_via_server, token)
            set_current_user_id(uid)
        await self.app(scope, receive, send)
