"""Owner-scoped multi-agent DAG API (WB-258)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from agent import orchestrator
from auth.deps import current_user
from storage import db, orchestration_store as store
from storage.models import Role

router = APIRouter(prefix="/api", tags=["orchestrations"])


class CreateBody(BaseModel):
    goal: str = Field(min_length=1, max_length=50000)
    team_name: str = Field(min_length=1, max_length=120)
    project_id: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=200)
    max_nodes: int = Field(default=7, ge=3, le=10)
    max_parallel: int = Field(default=3, ge=1, le=4)
    max_total_tokens: int = Field(default=24000, ge=2000, le=120000)


@router.post("/orchestrations", status_code=202)
def create(body: CreateBody) -> dict:
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
    if item.get("artifact_id"):
        artifact = db.get_artifact_for(item["artifact_id"], user.id)
        item["artifact"] = artifact.to_dict() if artifact else None
    return {"orchestration": item}


@router.post("/orchestrations/{orchestration_id}/cancel")
def cancel(orchestration_id: str) -> dict:
    item = store.get(orchestration_id, current_user().id)
    if not item:
        raise HTTPException(404, "orchestration not found")
    if item["status"] in {"completed", "failed", "cancelled"}:
        raise HTTPException(409, "orchestration is already terminal")
    orchestrator.cancel(orchestration_id)
    return {"cancelled": True}
