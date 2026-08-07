"""Minimal Local Agent Core application and protected loopback IPC (WB-434)."""
from __future__ import annotations

import asyncio
import ipaddress
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field, SecretStr
from starlette.responses import JSONResponse

import local_agent_ipc
import local_agent_store
import run_transport
import server_client
from agent import worker_health
from config import settings


IPC_HEADER = b"x-agentmate-ipc-token"


def bind_host() -> str:
    """The Local Agent control surface is never configurable onto the LAN."""
    return "127.0.0.1"


class LocalAgentIpcMiddleware:
    """Authenticate every Local Agent route with a per-sidecar random secret."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") == "http" and str(scope.get("path") or "").startswith("/api/local-agent"):
            client = scope.get("client") or ("", 0)
            remote = str(client[0] or "")
            try:
                loopback = ipaddress.ip_address(remote).is_loopback
            except ValueError:
                loopback = remote == "testclient"
            if not loopback:
                await JSONResponse(
                    {"detail": "Local Agent IPC is loopback-only"}, status_code=403,
                )(scope, receive, send)
                return
            supplied = ""
            for key, value in scope.get("headers") or []:
                if key.lower() == IPC_HEADER:
                    supplied = value.decode("latin-1")
                    break
            if len(local_agent_ipc.expected_token()) < 32:
                await JSONResponse(
                    {"detail": "Local Agent IPC is not initialized"}, status_code=503,
                )(scope, receive, send)
                return
            if not local_agent_ipc.authenticated(supplied):
                await JSONResponse(
                    {"detail": "Local Agent IPC authentication failed"}, status_code=401,
                )(scope, receive, send)
                return
        await self.app(scope, receive, send)


router = APIRouter(prefix="/api/local-agent", tags=["local-agent"])


def _status() -> dict[str, Any]:
    snapshot = local_agent_store.status_snapshot()
    return {
        "service": "local-agent-core",
        "protocol_version": run_transport.PROTOCOL_VERSION,
        "server_configured": settings.server_enabled,
        "transport": snapshot,
        "workers": worker_health.snapshot(),
    }


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, **_status()}


@router.get("/status")
def status() -> dict[str, Any]:
    return _status()


class IdentityBind(BaseModel):
    owner_id: str = Field(min_length=8, max_length=200)
    server_token: SecretStr = Field(min_length=16, max_length=4096)


@router.put("/identity")
def bind_identity(body: IdentityBind) -> dict[str, Any]:
    token = body.server_token.get_secret_value()
    state, account = server_client.verify_token_state(token)
    if state == "unavailable":
        raise HTTPException(503, "AgentMate Server is unavailable")
    if state != "valid" or not account:
        raise HTTPException(401, "Server identity is invalid")
    if str(account.get("id") or "") != body.owner_id:
        raise HTTPException(403, "Server identity owner mismatch")
    local_agent_store.set_server_identity(
        body.owner_id, token, float(account.get("_token_expires_at") or 0) or None,
    )
    return {"bound": True, "owner_id": body.owner_id}


class IdentityRemove(BaseModel):
    owner_id: str = Field(min_length=8, max_length=200)


@router.delete("/identity")
def remove_identity(body: IdentityRemove) -> dict[str, Any]:
    local_agent_store.clear_server_identity(body.owner_id)
    return {"removed": True, "owner_id": body.owner_id}


class ClaimBody(BaseModel):
    owner_id: str = Field(min_length=8, max_length=200)
    lease_seconds: int = Field(default=30, ge=5, le=300)


@router.post("/runs/claim")
def claim_run(body: ClaimBody) -> dict[str, Any]:
    user_token = local_agent_store.get_server_identity(body.owner_id)
    if not user_token:
        raise HTTPException(401, "No valid Server identity is bound to this Local Agent")
    device_token = run_transport.ensure_device(body.owner_id, user_token)
    if not device_token:
        raise HTTPException(503, "Local Agent device registration is unavailable")
    run = run_transport.claim_run(body.owner_id, device_token, lease_seconds=body.lease_seconds)
    return {"run": run}


class RunControl(BaseModel):
    owner_id: str = Field(min_length=8, max_length=200)
    lease_seconds: int = Field(default=30, ge=5, le=300)


def _device_token(owner_id: str) -> str:
    token = run_transport.device_token(owner_id)
    if not token:
        raise HTTPException(409, "Local Agent device is not authenticated")
    return token


class RunEventBody(BaseModel):
    owner_id: str = Field(min_length=8, max_length=200)
    type: str = Field(
        pattern=r"^(run\.(started|waiting_user|checkpoint|completed|failed|cancelled|cancel_ack)|command\.ack)$"
    )
    payload: dict[str, Any] = Field(default_factory=dict)


@router.post("/runs/{run_id}/events")
def append_run_event(run_id: str, body: RunEventBody) -> dict[str, Any]:
    if run_transport.lease_owner(run_id) != body.owner_id:
        raise HTTPException(404, "Active Run lease was not found")
    try:
        return {"event": run_transport.append_event(run_id, body.type, body.payload)}
    except run_transport.WalCapacityExceeded as exc:
        raise HTTPException(507, str(exc)) from exc
    except (ValueError, run_transport.LeaseFenced) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/runs/{run_id}/renew")
def renew_run(run_id: str, body: RunControl) -> dict[str, Any]:
    try:
        return run_transport.renew_lease(
            run_id, _device_token(body.owner_id), lease_seconds=body.lease_seconds,
        )
    except run_transport.LeaseFenced as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/runs/flush")
def flush_runs(body: IdentityRemove) -> dict[str, Any]:
    return run_transport.flush_wal(body.owner_id, _device_token(body.owner_id))


async def _transport_loop() -> None:
    while True:
        def maintain() -> None:
            try:
                run_transport.maintain_transport()
            finally:
                local_agent_store.close_thread_connection()

        await asyncio.to_thread(maintain)
        await asyncio.sleep(20)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    local_agent_store.init_db()
    task = asyncio.create_task(_transport_loop())
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        server_client.close()
        local_agent_ipc.clear_token()
        local_agent_store.close_thread_connection()


app = FastAPI(
    title="AgentMate Local Agent Core", version="1.0.0", lifespan=lifespan,
    docs_url=None, redoc_url=None, openapi_url=None,
)
app.add_middleware(LocalAgentIpcMiddleware)
app.include_router(router)
