"""WorkBuddy backend entrypoint (FastAPI + SSE).

Local-first: this runs on the user's machine as a localhost service. The browser
(Vite dev server, or the Tauri shell in M5) is just the display. All routes pass
through the auth dependency which, in M1, injects the fixed local user.
"""
from __future__ import annotations

import asyncio
import sys

# MCP-server subcommand: when the bundled exe re-execs itself as
# `WorkBuddy.exe --mcp-server=<name>` (see agent/mcp_client.py), run that FastMCP
# server on stdio and exit — never start the web app. Handled first, before the
# heavy web-app imports, so a connector process stays lightweight.
for _arg in sys.argv[1:]:
    if _arg.startswith("--mcp-server="):
        from mcp_servers import run_mcp_server
        run_mcp_server(_arg.split("=", 1)[1])
        raise SystemExit(0)

# Windows: force the Proactor event loop *at import time* so it also applies to
# uvicorn's reload child (which imports this module, not the __main__ block).
# The Selector loop uvicorn otherwise uses on Windows cannot spawn subprocesses,
# which breaks the MCP connectors (anyio.open_process → NotImplementedError).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent import scheduler
from auth.middleware import AuthMiddleware
from config import FROZEN, settings
from routers import auth, automations, chat, experts, files, me, models, notifications, projects, sessions, work_items
from storage import db

app = FastAPI(title="WorkBuddy API", version="0.1.0")

# Reject oversized JSON API bodies before they are buffered (WB-010). File uploads
# stream and enforce their own 50MB cap, so they're exempt from this smaller limit.
MAX_JSON_BODY = 8 * 1024 * 1024  # 8 MB


class BodySizeLimitMiddleware:
    """Reject oversized JSON bodies by Content-Length, as PURE ASGI middleware.

    Deliberately not a BaseHTTPMiddleware (@app.middleware("http")): that wraps
    every response in its own anyio cancel scope, which crashes SSE endpoints that
    spawn nested task groups (MCP stdio_client) with "Attempted to exit a cancel
    scope that isn't the current task's current cancel scope". Pure ASGI only peeks
    at the request headers and otherwise passes the app through untouched.
    """

    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") == "http" and scope.get("method") in ("POST", "PUT", "PATCH"):
            if not scope.get("path", "").startswith("/api/files/upload"):
                cl = dict(scope.get("headers") or []).get(b"content-length")
                if cl and cl.isdigit() and int(cl) > self.max_bytes:
                    await JSONResponse({"detail": "请求体过大"}, status_code=413)(scope, receive, send)
                    return
        await self.app(scope, receive, send)


app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_JSON_BODY)
# Resolve the Bearer token → current user (M7 C1). Pure ASGI, so SSE stays intact.
app.add_middleware(AuthMiddleware)

# During M0–M4 the UI is served by Vite on :5173 and proxies /api. CORS stays
# permissive for localhost so direct-origin dev (no proxy) also works.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        # Tauri desktop shell webview origins (A2): Windows serves the app from
        # http(s)://tauri.localhost, other platforms from tauri://localhost.
        "http://tauri.localhost",
        "https://tauri.localhost",
        "tauri://localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


@app.on_event("startup")
async def _start_scheduler() -> None:
    # Automation scheduler runs on the app's event loop (agent/scheduler.py).
    scheduler.start()


@app.on_event("shutdown")
async def _stop_scheduler() -> None:
    await scheduler.stop()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "llm_configured": settings.llm_configured}


app.include_router(auth.router)
app.include_router(me.router)
app.include_router(models.router)
app.include_router(sessions.router)
app.include_router(chat.router)
app.include_router(files.router)
app.include_router(projects.router)
app.include_router(experts.router)
app.include_router(work_items.router)
app.include_router(automations.router)
app.include_router(notifications.router)


if __name__ == "__main__":
    import uvicorn

    # No reload on Windows: uvicorn's reload child creates its event loop before
    # importing this module, so it never picks up the Proactor policy set above —
    # and a Selector loop can't spawn the MCP connector subprocesses. Running
    # in-process keeps the Proactor loop (and matches the project's hard-restart
    # workflow). Elsewhere reload is fine.
    reload = sys.platform != "win32" and not FROZEN
    # Reload needs the "main:app" import string; without it (frozen bundle, or
    # Windows) pass the app object directly — a bundle can't re-import `main`
    # (it's __main__, not an importable module).
    target = "main:app" if reload else app
    uvicorn.run(target, host=settings.HOST, port=settings.PORT, reload=reload)
