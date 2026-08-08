"""Minimal Local Agent Core application and protected loopback IPC (WB-434)."""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field, SecretStr
from starlette.responses import JSONResponse

import local_agent_ipc
import local_agent_store
import run_transport
import server_client
from agent import worker_health
from agent import sandbox
from agent import server_run_worker
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
        # Non-secret bootstrap metadata for Desktop's direct business channel.
        # The webview receives no IPC token and cannot turn this status command
        # into a generic privileged loopback proxy.
        "server_api_url": settings.AGENTMATE_SERVER_URL,
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


class RunInputStage(BaseModel):
    owner_id: str = Field(min_length=8, max_length=200)
    request_key: str = Field(min_length=8, max_length=200, pattern=r"^[A-Za-z0-9._:-]+$")
    refs: list[dict[str, Any]] = Field(default_factory=list, max_length=50)


@router.put("/run-inputs")
def stage_run_input(body: RunInputStage) -> dict[str, Any]:
    user_token = local_agent_store.get_server_identity(body.owner_id)
    if not user_token:
        raise HTTPException(401, "No valid Server identity is bound to this Local Agent")
    if not run_transport.ensure_device(body.owner_id, user_token):
        raise HTTPException(503, "Local Agent device registration is unavailable")
    try:
        local_agent_store.stage_run_input(body.owner_id, body.request_key, {"refs": body.refs})
    except ValueError as exc:
        raise HTTPException(413, str(exc)) from exc
    return {
        "staged": True, "request_key": body.request_key,
        "device_id": run_transport.device_id(body.owner_id),
    }


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


# ---- WB-436 Asset working copies ------------------------------------------

def _identity(owner_id: str) -> str:
    token = local_agent_store.get_server_identity(owner_id)
    if not token:
        raise HTTPException(401, "No valid Server identity is bound to this Local Agent")
    return token


def _server_failure(exc: Exception) -> None:
    if isinstance(exc, server_client.ServerRejected):
        raise HTTPException(exc.status_code, exc.detail) from exc
    raise exc


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def _workspace_path(project_id: str, relative_path: str) -> Path:
    root = sandbox.project_root(project_id or None)
    try:
        return sandbox.resolve_in_sandbox(relative_path, root)
    except sandbox.SandboxError as exc:
        raise HTTPException(400, str(exc)) from exc


class AssetCommitBody(BaseModel):
    owner_id: str = Field(min_length=8, max_length=200)
    project_id: str = Field(default="", max_length=200)
    session_id: str = Field(default="", max_length=200)
    run_id: str = Field(default="", max_length=200)
    local_path: str = Field(min_length=1, max_length=4096)
    kind: str = Field(default="asset", max_length=80)
    external: bool = False
    explicit_external_upload: bool = False


@router.post("/assets/commit")
def commit_asset(body: AssetCommitBody) -> dict[str, Any]:
    if body.external:
        if not body.explicit_external_upload:
            raise HTTPException(409, "external files require explicit upload consent")
        supplied_path = Path(body.local_path).expanduser()
        if not supplied_path.is_absolute():
            raise HTTPException(400, "external file path must be absolute")
        path = supplied_path.resolve()
        source_kind = "external"
        local_key = str(path)
    else:
        path = _workspace_path(body.project_id, body.local_path)
        source_kind = "workspace"
        local_key = sandbox.relpath(path, sandbox.project_root(body.project_id or None))
    if not path.is_file():
        raise HTTPException(404, "local working-copy file not found")
    size, sha256 = _hash_file(path)
    prior = next(
        (
            item for item in local_agent_store.list_working_copies(body.owner_id)
            if item["source_kind"] == source_kind and item["relative_path"] == local_key
            and item["sha256"] == sha256 and int(item["size"]) == size
        ),
        None,
    )
    # A byte-identical working copy from another Run is not the same delivery:
    # each Server Run needs its own immutable Asset row/work_item association.
    reusable = prior if prior and str(prior.get("run_id") or "") == body.run_id else None
    copy = local_agent_store.upsert_working_copy(
        owner_id=body.owner_id, relative_path=local_key, source_kind=source_kind,
        project_id=body.project_id, run_id=body.run_id, asset_id=str((reusable or {}).get("asset_id") or ""),
        state="local-only", size=size, sha256=sha256,
        upload_id=str((reusable or {}).get("upload_id") or ""),
        object_version_id=str((reusable or {}).get("object_version_id") or ""),
    )
    if reusable and reusable["state"] == "committed" and reusable.get("object_version_id"):
        return {"working_copy": copy, "duplicate": True}

    token = _identity(body.owner_id)
    asset_id = str(copy.get("asset_id") or "")
    try:
        if not asset_id:
            created = server_client.create_server_asset(
                token,
                {
                    "project_id": body.project_id or None,
                    "session_id": body.session_id or None,
                    "run_id": body.run_id or None,
                    "kind": body.kind,
                    "name": path.name,
                    "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                    "size": size,
                    "sha256": sha256,
                    "source_tool": "local-agent.explicit-upload" if body.external else "local-agent.workspace-commit",
                },
                # The working-copy row is path-scoped and survives across Runs,
                # while each Run must create its own immutable delivery Asset.
                # Therefore the Server idempotency scope must include run_id.
                "working-copy:" + hashlib.sha256(
                    f"{copy['id']}:{body.run_id or 'manual'}:{sha256}".encode("utf-8")
                ).hexdigest(),
            )
            if not created:
                raise HTTPException(503, "AgentMate Server is unavailable; working copy remains local-only")
            asset_id = str(created["asset"]["id"])
        started = server_client.begin_asset_upload(token, asset_id, size, sha256)
        if not started:
            local_agent_store.upsert_working_copy(
                owner_id=body.owner_id, relative_path=local_key, source_kind=source_kind,
                project_id=body.project_id, run_id=body.run_id, asset_id=asset_id,
                state="uploading", size=size, sha256=sha256,
            )
            raise HTTPException(503, "AgentMate Server is unavailable; upload can be resumed")
        upload = started["upload"]
        upload_id = str(upload["id"])
        copy = local_agent_store.upsert_working_copy(
            owner_id=body.owner_id, relative_path=local_key, source_kind=source_kind,
            project_id=body.project_id, run_id=body.run_id, asset_id=asset_id,
            state="uploading", size=size, sha256=sha256, upload_id=upload_id,
            object_version_id=str(upload.get("object_version_id") or ""),
        )
        if upload["state"] != "committed":
            status = server_client.asset_upload_status(token, upload_id) if upload.get("resumed") else started
            if not status:
                raise HTTPException(503, "AgentMate Server is unavailable; upload can be resumed")
            received = {
                int(part["part_number"])
                for part in status.get("upload", {}).get("parts", [])
            }
            part_size = int(upload["part_size"])
            with path.open("rb") as source:
                part_number = 0
                while chunk := source.read(part_size):
                    if part_number not in received:
                        part_hash = hashlib.sha256(chunk).hexdigest()
                        if not server_client.upload_asset_part(
                            token, upload_id, part_number, chunk, part_hash,
                        ):
                            raise HTTPException(503, "AgentMate Server is unavailable; upload can be resumed")
                    part_number += 1
            completed = server_client.complete_asset_upload(token, upload_id)
            if not completed:
                raise HTTPException(503, "AgentMate Server is unavailable; upload can be resumed")
            object_version = completed["object_version"]
        else:
            object_version = {"id": upload["object_version_id"]}
        copy = local_agent_store.upsert_working_copy(
            owner_id=body.owner_id, relative_path=local_key, source_kind=source_kind,
            project_id=body.project_id, run_id=body.run_id, asset_id=asset_id,
            state="committed", size=size, sha256=sha256, upload_id=upload_id,
            object_version_id=str(object_version["id"]),
        )
        return {"working_copy": copy, "duplicate": bool(upload.get("deduplicated"))}
    except HTTPException:
        raise
    except Exception as exc:
        _server_failure(exc)
        raise


class AssetDownloadBody(BaseModel):
    owner_id: str = Field(min_length=8, max_length=200)
    project_id: str = Field(default="", max_length=200)
    relative_path: str = Field(min_length=1, max_length=4096)


@router.post("/assets/{asset_id}/download")
def download_asset(asset_id: str, body: AssetDownloadBody) -> dict[str, Any]:
    token = _identity(body.owner_id)
    target = _workspace_path(body.project_id, body.relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.agentmate-download")
    try:
        grant = server_client.create_asset_download_grant(token, asset_id)
        if not grant:
            raise HTTPException(503, "AgentMate Server is unavailable")
        headers = server_client.download_asset_to_file(token, asset_id, str(grant["token"]), temporary)
        if not headers:
            raise HTTPException(503, "AgentMate Server is unavailable")
        size, sha256 = _hash_file(temporary)
        version = grant["object_version"]
        if size != int(version["size"]) or sha256 != str(version["sha256"]):
            temporary.unlink(missing_ok=True)
            raise HTTPException(409, "downloaded object failed size or sha256 verification")
        os.replace(temporary, target)
        copy = local_agent_store.upsert_working_copy(
            owner_id=body.owner_id,
            relative_path=sandbox.relpath(target, sandbox.project_root(body.project_id or None)),
            source_kind="workspace", project_id=body.project_id, asset_id=asset_id,
            state="committed", size=size, sha256=sha256,
            object_version_id=str(version["id"]),
        )
        return {"working_copy": copy}
    except HTTPException:
        temporary.unlink(missing_ok=True)
        raise
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        _server_failure(exc)
        raise


@router.get("/assets/working-copies")
def working_copies(owner_id: str) -> dict[str, Any]:
    _identity(owner_id)
    return {"working_copies": local_agent_store.list_working_copies(owner_id)}


@router.delete("/assets/working-copies/{copy_id}")
def cleanup_working_copy(copy_id: str, owner_id: str, delete_file: bool = False) -> dict[str, Any]:
    copy = local_agent_store.get_working_copy(copy_id, owner_id)
    if not copy:
        raise HTTPException(404, "working copy not found")
    if copy["source_kind"] == "external" and delete_file:
        raise HTTPException(409, "Local Agent never deletes an external original")
    deleted = False
    if delete_file:
        path = _workspace_path(str(copy["project_id"]), str(copy["relative_path"]))
        if path.is_file():
            path.unlink()
            deleted = True
    local_agent_store.delete_working_copy(
        copy_id, owner_id, action="working-copy.cleanup.file" if deleted else "working-copy.cleanup.metadata",
    )
    return {"cleaned": True, "file_deleted": deleted}


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
    task = asyncio.create_task(server_run_worker.run_forever())
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
