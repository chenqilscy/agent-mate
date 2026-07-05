"""Projects — new-project flow persisted (spec 5.1). Members/connectors auth is M7."""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth.deps import current_user
from storage import db

router = APIRouter(prefix="/api", tags=["projects"])


class CreateProjectBody(BaseModel):
    name: str
    instruction: str = ""
    connectors: list[str] = []
    experts: list[str] = []
    skills: list[str] = []


class UpdateProjectBody(BaseModel):
    name: str | None = None
    instruction: str | None = None
    connectors: list[str] | None = None
    experts: list[str] | None = None
    skills: list[str] | None = None


def _ago(ts: float) -> str:
    diff = max(0, time.time() - ts)
    if diff < 60:
        return "刚刚"
    if diff < 3600:
        return f"{int(diff // 60)}分钟前"
    if diff < 86400:
        return f"{int(diff // 3600)}小时前"
    return f"{int(diff // 86400)}天前"


def _view(p) -> dict:
    d = p.to_dict()
    d["ago"] = _ago(p.created_at)
    return d


@router.get("/projects")
def list_projects() -> dict:
    user = current_user()
    return {"projects": [_view(p) for p in db.list_projects(user.id)]}


@router.post("/projects")
def create_project(body: CreateProjectBody) -> dict:
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(400, "empty project name")
    user = current_user()
    p = db.create_project(
        owner_id=user.id,
        name=name,
        instruction=body.instruction,
        connectors=body.connectors,
        experts=body.experts,
        skills=body.skills,
    )
    return _view(p)


@router.get("/projects/{project_id}")
def get_project(project_id: str) -> dict:
    p = db.get_project(project_id)
    if not p:
        raise HTTPException(404, "project not found")
    return _view(p)


@router.patch("/projects/{project_id}")
def update_project(project_id: str, body: UpdateProjectBody) -> dict:
    p = db.get_project(project_id)
    if not p:
        raise HTTPException(404, "project not found")
    updated = db.update_project(
        project_id,
        name=body.name,
        instruction=body.instruction,
        connectors=body.connectors,
        experts=body.experts,
        skills=body.skills,
    )
    return _view(updated)


@router.get("/projects/{project_id}/sessions")
def project_sessions(project_id: str) -> dict:
    rows = db.list_project_sessions(project_id)
    return {"sessions": [{**s.to_dict(), "ago": _ago(s.updated_at)} for s in rows]}
