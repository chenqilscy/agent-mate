"""AgentMate backend entrypoint (FastAPI + SSE).

Local-first: this runs on the user's machine as a localhost service. The browser
(Vite dev server, or the Tauri shell in M5) is just the display. All routes pass
through the auth dependency which, in M1, injects the fixed local user.
"""
from __future__ import annotations

import asyncio
import logging
import sys

# MCP-server subcommand: when the bundled exe re-execs itself as
# `AgentMate.exe --mcp-server=<name>` (see agent/mcp_client.py), run that FastMCP
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

# httpx 的 INFO 行包含完整请求 URL；部分第三方 API 把凭据放在路径中，绝不能进终端/日志（WB-200）。
# 业务层的 agentmate.* 日志不受影响，连接成功/失败仍可观察。
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent import background_worker, scheduler, skills as agent_skills, telemetry
from auth.middleware import AuthMiddleware
from channels import manager as channel_manager
from config import FROZEN, settings
from routers import asr, auth, automations, catalog, channels, chat, data, device_settings, experts, files, governance, server, kdocs, knowledge, me, memory, milestones, models, notifications, ops, orchestrations, prefs, project_health, projects, runs, security, sessions, skills, work_items
from storage import db, orchestration_store

app = FastAPI(title="AgentMate API", version="1.0.0")

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
            _path = scope.get("path", "")
            # 文件上传流式且各有 50MB 上限，豁免这个较小的 JSON 限制：
            # /api/files/upload 与 知识库文档上传 /api/knowledge/{id}/documents。
            _is_upload = _path.startswith("/api/files/upload") or (
                _path.startswith("/api/knowledge/") and _path.endswith("/documents")
            )
            if not _is_upload:
                cl = dict(scope.get("headers") or []).get(b"content-length")
                if cl and cl.isdigit() and int(cl) > self.max_bytes:
                    await JSONResponse({"detail": "请求体过大"}, status_code=413)(scope, receive, send)
                    return
        await self.app(scope, receive, send)


app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_JSON_BODY)
# Resolve the Bearer token → current user (M7 C1). Pure ASGI, so SSE stays intact.
app.add_middleware(AuthMiddleware)

# During M0–M4 the UI is served by Vite on :8102 and proxies /api. CORS stays
# permissive for localhost so direct-origin dev (no proxy) also works.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8102",
        "http://127.0.0.1:8102",
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
    import device_settings as runtime_device_settings
    runtime_device_settings.apply_all()
    orchestration_store.ensure_tables()
    migrated = db.migrate_skill_identities(agent_skills.canonical_skill_key)
    if migrated["changed"] or migrated["dropped"]:
        logging.getLogger("agentmate.skills").info("skill identity migration: %s", migrated)


@app.on_event("startup")
async def _start_scheduler() -> None:
    # Automation scheduler runs on the app's event loop (agent/scheduler.py).
    scheduler.start()


@app.on_event("startup")
async def _start_background_worker() -> None:
    await background_worker.start()


@app.on_event("shutdown")
async def _stop_scheduler() -> None:
    await scheduler.stop()


@app.on_event("shutdown")
async def _stop_background_worker() -> None:
    await background_worker.stop()


@app.on_event("startup")
async def _start_channels() -> None:
    # 助理外部渠道（WB-072/077/086·087）：渠道管理器按 DB 里「启用且类型可用」的渠道起 poller
    # （多助理·多 bot）。无渠道/无 token → 零 poller，纯本地不受影响。
    await channel_manager.refresh()


@app.on_event("shutdown")
async def _stop_channels() -> None:
    await channel_manager.stop()


@app.on_event("shutdown")
def _stop_telemetry() -> None:
    # Langfuse batches exports in background threads. Default-off/no client is a no-op.
    telemetry.shutdown()


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "llm_configured": settings.llm_configured,
        "langfuse_configured": settings.langfuse_configured,
    }


app.include_router(auth.router)
app.include_router(me.router)
app.include_router(models.router)
app.include_router(sessions.router)
app.include_router(runs.router)
app.include_router(orchestrations.router)
app.include_router(chat.router)
app.include_router(files.router)
app.include_router(projects.router)
app.include_router(experts.router)
app.include_router(kdocs.router)
app.include_router(skills.router)
app.include_router(work_items.router)
app.include_router(milestones.router)
app.include_router(governance.router)
app.include_router(project_health.router)
app.include_router(automations.router)
app.include_router(notifications.router)
app.include_router(ops.router)
app.include_router(catalog.router)
app.include_router(server.router)
app.include_router(channels.router)
app.include_router(asr.router)
app.include_router(knowledge.router)
app.include_router(prefs.router)
app.include_router(device_settings.router)
app.include_router(memory.router)
app.include_router(data.router)
app.include_router(security.router)


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
