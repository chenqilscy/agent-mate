"""AgentMate backend entrypoint (FastAPI + SSE).

Local-first: this runs on the user's machine as a localhost service. The browser
(Vite dev server, or the Tauri shell) is just the display. Requests resolve a
Server-issued Bearer identity through the auth middleware; without one they use
the anonymous LOCAL_USER data scope, which is not a login account.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

# Trusted isolated tool subprocess. Handle before the web app, DB and router
# imports so a one-call worker stays small and never starts HTTP/background work.
if "--tool-worker" in sys.argv[1:]:
    from agent.tool_worker import main as run_tool_worker
    raise SystemExit(run_tool_worker())

# MCP-server subcommand: when the bundled exe re-execs itself as
# `AgentMate.exe --mcp-server=<name>` (see agent/mcp_client.py), run that FastMCP
# server on stdio and exit — never start the web app. Handled first, before the
# heavy web-app imports, so a connector process stays lightweight.
for _arg in sys.argv[1:]:
    if _arg.startswith("--mcp-server="):
        from mcp_servers import run_mcp_server
        run_mcp_server(_arg.split("=", 1)[1])
        raise SystemExit(0)

# Tauri writes a per-launch IPC token through the sidecar stdin pipe. The
# command line carries only this mode flag, never the credential itself.
if "--ipc-token-stdin" in sys.argv[1:]:
    import local_agent_ipc

    _ipc_token = sys.stdin.readline(257).strip()
    try:
        local_agent_ipc.install_token(_ipc_token)
    except ValueError as exc:
        raise SystemExit(f"Local Agent IPC bootstrap failed: {exc}") from exc
    finally:
        _ipc_token = ""

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
from routers import asr, auth, automations, catalog, channels, chat, data, device_settings, experts, files, governance, ideas, server, kdocs, knowledge, me, memory, milestones, models, notifications, ops, orchestrations, prefs, project_health, projects, runs, security, sessions, skills, work_items
from storage import db, orchestration_store
import local_agent_core
import local_agent_store
import server_client


def _startup() -> None:
    db.init_db()
    if settings.server_enabled:
        local_agent_store.init_db()
        # Temporary one-way compatibility bridge: WB-435 will bind the Server
        # identity directly through Tauri IPC once UI business traffic leaves
        # this legacy app. Core mode never opens the business database at all.
        for owner_id, token in db.list_server_identities():
            local_agent_store.set_server_identity(owner_id, token)
    recovered = db.recover_stale_runs()
    if recovered:
        logging.getLogger("agentmate.runs").warning(
            "paused %d Run(s) abandoned by the previous backend process", len(recovered),
        )
    import device_settings as runtime_device_settings
    runtime_device_settings.apply_all()
    orchestration_store.ensure_tables()
    migrated = db.migrate_skill_identities(agent_skills.canonical_skill_key)
    if migrated["changed"] or migrated["dropped"]:
        logging.getLogger("agentmate.skills").info("skill identity migration: %s", migrated)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    cleanup: list[tuple[str, Callable[[], Awaitable[None]]]] = []
    try:
        _startup()
        scheduler.start()
        cleanup.append(("automation scheduler", scheduler.stop))
        cleanup.append(("background worker", background_worker.stop))
        await background_worker.start()
        cleanup.append(("channel manager", channel_manager.stop))
        await channel_manager.refresh()
        yield
    finally:
        for name, stop in reversed(cleanup):
            try:
                await stop()
            except Exception:  # noqa: BLE001 - shutdown must continue for remaining resources
                logging.getLogger("agentmate.lifecycle").exception("failed to stop %s", name)
        try:
            telemetry.shutdown()
        finally:
            server_client.close()


app = FastAPI(title="AgentMate API", version="1.0.0", lifespan=_lifespan)


@app.exception_handler(server_client.ServerRejected)
async def _server_rejected(_request: Request, exc: server_client.ServerRejected) -> JSONResponse:
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

# Reject oversized JSON API bodies before they are buffered (WB-010). File uploads
# stream and enforce their own 50MB cap, so they're exempt from this smaller limit.
MAX_JSON_BODY = 8 * 1024 * 1024  # 8 MB


class BodySizeLimitMiddleware:
    """Reject oversized JSON bodies by declared and actually received bytes.

    Deliberately not a BaseHTTPMiddleware (@app.middleware("http")): that wraps
    every response in its own anyio cancel scope, which crashes SSE endpoints that
    spawn nested task groups (MCP stdio_client). The bounded pre-read prevents a
    missing/forged Content-Length from bypassing the cap while preserving the exact
    ASGI request messages for downstream consumers.
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
                messages: list[dict] = []
                received = 0
                while True:
                    message = await receive()
                    messages.append(message)
                    if message.get("type") != "http.request":
                        break
                    received += len(message.get("body") or b"")
                    if received > self.max_bytes:
                        await JSONResponse(
                            {"detail": "请求体过大"}, status_code=413,
                        )(scope, receive, send)
                        return
                    if not message.get("more_body", False):
                        break

                index = 0

                async def replay_receive():
                    nonlocal index
                    if index < len(messages):
                        message = messages[index]
                        index += 1
                        return message
                    # Once the buffered request frames are consumed, preserve the
                    # real client lifecycle. Synthesizing a disconnect here makes
                    # StreamingResponse cancel an SSE generator after its first
                    # frame even though the client is still connected.
                    return await receive()

                await self.app(scope, replay_receive, send)
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

# Native-only control surface. Browser calls cannot obtain the per-launch token;
# Tauri exposes only narrow commands rather than a generic authenticated proxy.
app.add_middleware(local_agent_core.LocalAgentIpcMiddleware)


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
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
app.include_router(ideas.router)
app.include_router(data.router)
app.include_router(security.router)
app.include_router(local_agent_core.router)


if __name__ == "__main__":
    import uvicorn

    # No reload on Windows: uvicorn's reload child creates its event loop before
    # importing this module, so it never picks up the Proactor policy set above —
    # and a Selector loop can't spawn the MCP connector subprocesses. Running
    # in-process keeps the Proactor loop (and matches the project's hard-restart
    # workflow). Elsewhere reload is fine.
    core_mode = "--local-agent-core" in sys.argv[1:]
    reload = sys.platform != "win32" and not FROZEN and not core_mode
    # Reload needs the "main:app" import string; without it (frozen bundle, or
    # Windows) pass the app object directly — a bundle can't re-import `main`
    # (it's __main__, not an importable module).
    target = "main:app" if reload else (local_agent_core.app if core_mode else app)
    # The Core is never allowed to honor a configurable LAN bind address.
    host = (
        local_agent_core.bind_host()
        if (core_mode or "--ipc-token-stdin" in sys.argv[1:])
        else settings.HOST
    )
    uvicorn.run(target, host=host, port=settings.PORT, reload=reload)
