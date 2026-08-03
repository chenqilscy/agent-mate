"""Run and Artifact delivery API (WB-242)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from auth.deps import current_user
from config import settings
from storage import db
from storage.models import Role, Run

router = APIRouter(prefix="/api", tags=["runs", "artifacts"])


class ReviewArtifactBody(BaseModel):
    status: str = Field(pattern="^(accepted|rejected|pending)$")


class RetryRunBody(BaseModel):
    idempotency_key: str | None = Field(default=None, max_length=200)


def _run_view(run: Run) -> dict:
    data = run.to_dict()
    data["artifacts"] = [artifact.to_dict() for artifact in db.list_artifacts(run.id)]
    return data


def _artifact_path(run: Run, relative_path: str) -> Path | None:
    base = settings.WORKSPACE_ROOT.resolve()
    root = (base / run.workspace).resolve()
    target = (root / relative_path).resolve()
    if root != base and base not in root.parents:
        return None
    if target != root and root not in target.parents:
        return None
    return target


def _artifact_view(artifact) -> dict:
    data = artifact.to_dict()
    run = db.get_run(artifact.run_id)
    target = _artifact_path(run, artifact.path) if run else None
    exists = bool(target and target.is_file())
    matches = False
    if exists and target:
        digest = hashlib.sha256()
        with target.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        matches = digest.hexdigest() == artifact.sha256 and target.stat().st_size == artifact.size
    data["verification"] = {"exists": exists, "hash_matches": matches}
    return data


def _get_visible_run(run_id: str) -> Run:
    run = db.get_run_for(run_id, current_user().id)
    if not run:
        raise HTTPException(404, "run not found")
    return run


def _require_review_permission(run: Run) -> None:
    user = current_user()
    if run.owner_id == user.id:
        return
    role = db.project_access_role(run.project_id, user.id) if run.project_id else None
    if role is None:
        raise HTTPException(404, "run not found")
    if role == Role.VIEWER:
        raise HTTPException(403, "只读成员不能验收产物")


@router.get("/runs")
def list_runs(
    session_id: str | None = None,
    project_id: str | None = None,
    work_item_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    user = current_user()
    runs = db.list_runs(
        user.id, session_id=session_id, project_id=project_id,
        work_item_id=work_item_id, limit=limit,
    )
    return {"runs": [_run_view(run) for run in runs]}


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    return _run_view(_get_visible_run(run_id))


@router.post("/runs/{run_id}/plan/{plan_item_id}/promote")
def promote_plan_item(
    run_id: str, plan_item_id: str, authorization: str = Header(default=""),
) -> dict:
    """Idempotently promote one durable RunPlan item into the project board."""
    run = _get_visible_run(run_id)
    _require_review_permission(run)
    if not run.project_id:
        raise HTTPException(409, "个人会话计划不能提升为项目任务")
    item = next(
        (value for value in run.plan if str(value.get("id") or "") == plan_item_id),
        None,
    )
    if not item:
        raise HTTPException(404, "plan item not found")
    linked_id = str(item.get("work_item_id") or "")
    if linked_id:
        linked = db.get_work_item(linked_id)
        if linked and linked.project_id == run.project_id:
            return {"run": _run_view(run), "work_item": linked.to_dict(), "created": False}

    # Reuse the authoritative WorkItem route so Server-origin projects keep their
    # remote write/no-local-fallback semantics instead of creating a fake mirror.
    from routers import work_items as work_items_router

    status_map = {
        "pending": "todo", "in_progress": "doing",
        "completed": "review", "blocked": "paused",
    }
    work_item = work_items_router.create_item(
        work_items_router.CreateWorkItemBody(
            project_id=run.project_id,
            title=str(item.get("title") or "")[:200],
            status=status_map.get(str(item.get("status") or ""), "todo"),
            source="RunPlan",
            description=f"由 AgentMate Run {run.id} 的执行计划提升。",
        ),
        authorization=authorization,
    )
    work_item_id = str(work_item.get("id") or "")
    if not work_item_id:
        raise HTTPException(502, "项目任务已创建但未返回 id")
    updated = db.link_run_plan_work_item(run.id, plan_item_id, work_item_id)
    return {"run": _run_view(updated), "work_item": work_item, "created": True}


@router.get("/runs/{run_id}/artifacts")
def list_run_artifacts(run_id: str) -> dict:
    run = _get_visible_run(run_id)
    return {"artifacts": [_artifact_view(item) for item in db.list_artifacts(run.id)]}


@router.post("/artifacts/{artifact_id}/review")
def review_artifact(artifact_id: str, body: ReviewArtifactBody) -> dict:
    user = current_user()
    artifact = db.get_artifact_for(artifact_id, user.id)
    if not artifact:
        raise HTTPException(404, "artifact not found")
    run = _get_visible_run(artifact.run_id)
    _require_review_permission(run)
    return _artifact_view(db.review_artifact(artifact.id, body.status, user.id))


@router.post("/runs/{run_id}/retry")
def retry_run(run_id: str, body: RetryRunBody) -> dict:
    run = _get_visible_run(run_id)
    _require_review_permission(run)
    try:
        retry, created = db.create_retry_run(run.id, run.owner_id, body.idempotency_key)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"run": _run_view(retry), "created": created}
