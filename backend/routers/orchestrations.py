"""Owner-scoped multi-agent DAG API (WB-258)."""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent import events, orchestrator
from auth.deps import current_user
from storage import db, orchestration_store as store
from storage.models import Role

router = APIRouter(prefix="/api", tags=["orchestrations"])
TERMINAL = {"completed", "failed", "cancelled"}
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _with_artifact(item: dict, user_id: str) -> dict:
    if item.get("artifact_id"):
        artifact = db.get_artifact_for(item["artifact_id"], user_id)
        item["artifact"] = artifact.to_dict() if artifact else None
    return item


class CreateBody(BaseModel):
    goal: str = Field(min_length=1, max_length=50000)
    team_name: str = Field(min_length=1, max_length=120)
    project_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=200)
    max_nodes: int = Field(default=7, ge=3, le=10)
    max_parallel: int = Field(default=3, ge=1, le=4)
    max_total_tokens: int = Field(default=24000, ge=2000, le=120000)


@router.post("/orchestrations", status_code=202)
async def create(body: CreateBody) -> dict:
    user = current_user()
    team = orchestrator.resolve_team(body.team_name)
    if not team:
        raise HTTPException(404, "expert team not found")
    if body.project_id:
        role = db.project_access_role(body.project_id, user.id)
        if role is None:
            raise HTTPException(404, "project not found")
        if role == Role.VIEWER:
            raise HTTPException(403, "只读成员不能发起多 Agent 执行")
    item, created = store.create(
        owner_id=user.id, project_id=body.project_id, team_name=body.team_name,
        goal=body.goal.strip(), idempotency_key=body.idempotency_key,
        max_nodes=body.max_nodes, max_parallel=body.max_parallel,
        max_total_tokens=body.max_total_tokens,
    )
    if created:
        orchestrator.start(item["id"], user, team)
    return {"orchestration": item, "created": created}


@router.get("/orchestrations")
def list_orchestrations(limit: int = Query(default=50, ge=1, le=200)) -> dict:
    return {"orchestrations": store.list_for(current_user().id, limit)}


@router.get("/orchestrations/{orchestration_id}")
def get(orchestration_id: str) -> dict:
    user = current_user()
    item = store.get(orchestration_id, user.id)
    if not item:
        raise HTTPException(404, "orchestration not found")
    return {"orchestration": _with_artifact(item, user.id)}


@router.get("/orchestrations/{orchestration_id}/events")
async def stream_events(orchestration_id: str, request: Request):
    """Push authoritative snapshots on change; comments keep proxies from timing out."""
    user = current_user()
    if not store.get(orchestration_id, user.id):
        raise HTTPException(404, "orchestration not found")

    async def event_stream():
        last_updated = -1.0
        last_heartbeat = time.monotonic()
        while not await request.is_disconnected():
            current_version = store.version(orchestration_id, user.id)
            if not current_version:
                yield events.error("orchestration not found")
                return
            updated, status = current_version
            if updated != last_updated:
                item = store.get(orchestration_id, user.id)
                if not item:
                    yield events.error("orchestration not found")
                    return
                item = _with_artifact(item, user.id)
                yield events.sse("orchestration", {"orchestration": item})
                last_updated = updated
                last_heartbeat = time.monotonic()
                if status in TERMINAL:
                    yield events.done()
                    return
            elif time.monotonic() - last_heartbeat >= 15:
                yield ": keep-alive\n\n"
                last_heartbeat = time.monotonic()
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/orchestrations/{orchestration_id}/cancel")
async def cancel(orchestration_id: str) -> dict:
    user = current_user()
    item = store.get(orchestration_id, user.id)
    if not item:
        raise HTTPException(404, "orchestration not found")
    if item["status"] in TERMINAL:
        raise HTTPException(409, "orchestration is already terminal")
    await orchestrator.cancel_and_wait(orchestration_id)
    current = store.get(orchestration_id, user.id)
    if not current:
        raise HTTPException(404, "orchestration not found")
    return {"cancelled": current["status"] == "cancelled", "orchestration": _with_artifact(current, user.id)}
