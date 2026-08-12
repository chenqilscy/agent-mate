"""Same-origin HttpOnly session support for the Server Console (WB-539)."""
from __future__ import annotations

import time
from urllib.parse import urlsplit

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from config import settings


COOKIE_NAME = "agentmate_console_session"
CONSOLE_HEADER = "x-agentmate-console-session"
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_SESSION_ISSUERS = {
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/bootstrap",
    "/api/auth/sso/start",
    "/api/auth/sso/poll",
}


def wants_console_session(request: Request) -> bool:
    return request.headers.get(CONSOLE_HEADER, "") == "1"


def session_token(request: Request, authorization: str = "") -> str:
    if authorization[:7].lower() == "bearer ":
        return authorization[7:].strip()
    return request.cookies.get(COOKIE_NAME, "").strip()


def set_console_session(
    request: Request,
    response: Response,
    token: str,
    expires_at: float,
) -> None:
    if not wants_console_session(request):
        return
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=max(1, int(expires_at - time.time())),
        httponly=True,
        secure=request.url.scheme == "https" or settings.ENVIRONMENT == "production",
        samesite="strict",
        path="/api",
    )


def clear_console_session(response: Response) -> None:
    response.delete_cookie(
        COOKIE_NAME,
        path="/api",
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="strict",
    )


def console_auth_payload(
    request: Request,
    response: Response,
    *,
    token: str,
    expires_at: float,
    account: dict,
) -> dict:
    if wants_console_session(request):
        set_console_session(request, response, token, expires_at)
        return {"expires_at": expires_at, "account": account}
    return {"token": token, "expires_at": expires_at, "account": account}


def _same_origin(scope: Scope, origin: str) -> bool:
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    headers = {name.lower(): value for name, value in scope.get("headers", [])}
    host = headers.get(b"host", b"").decode("latin-1").lower()
    return bool(host) and parsed.scheme == scope.get("scheme", "http") and parsed.netloc.lower() == host


class ConsoleCsrfMiddleware:
    """Reject cross-origin writes authenticated only by the Console cookie."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or scope.get("method") not in _UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return
        headers = {name.lower(): value for name, value in scope.get("headers", [])}
        cookie_header = headers.get(b"cookie", b"").decode("latin-1")
        has_cookie = f"{COOKIE_NAME}=" in cookie_header
        has_bearer = headers.get(b"authorization", b"").lower().startswith(b"bearer ")
        path = str(scope.get("path", ""))
        if has_cookie and not has_bearer and path not in _SESSION_ISSUERS:
            marker = headers.get(CONSOLE_HEADER.encode("ascii"), b"")
            origin = headers.get(b"origin", b"").decode("latin-1")
            if marker != b"1" or not _same_origin(scope, origin):
                await JSONResponse({"detail": "csrf_rejected"}, status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)
