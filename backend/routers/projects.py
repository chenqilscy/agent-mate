"""Projects — new-project flow persisted (spec 5.1). Members/connectors auth is M7."""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth.deps import current_user
from storage import db
from storage.models import Role

router = APIRouter(prefix="/api", tags=["projects"])

# Roles allowed to manage members / edit project settings.
_MANAGE_ROLES = {Role.OWNER, Role.ADMIN}


def _require_access(project_id: str, user_id: str) -> Role:
    """Return the caller's effective role in the project, or 404 if no access."""
    role = db.project_access_role(project_id, user_id)
    if role is None:
        raise HTTPException(404, "project not found")
    return role


def _require_manage(project_id: str, user_id: str) -> Role:
    role = _require_access(project_id, user_id)
    if role not in _MANAGE_ROLES:
        raise HTTPException(403, "需要管理员或所有者权限")
    return role


def _member_role(raw: str) -> Role:
    """Validate an assignable membership role (Owner is not assignable)."""
    try:
        r = Role(raw)
    except ValueError:
        raise HTTPException(400, "无效角色")
    if r == Role.OWNER:
        raise HTTPException(400, "不能指派所有者角色")
    return r


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


class AddMemberBody(BaseModel):
    name: str
    role: str = "Member"


class UpdateMemberBody(BaseModel):
    role: str


def _ago(ts: float) -> str:
    diff = max(0, time.time() - ts)
    if diff < 60:
        return "刚刚"
    if diff < 3600:
        return f"{int(diff // 60)}分钟前"
    if diff < 86400:
        return f"{int(diff // 3600)}小时前"
    return f"{int(diff // 86400)}天前"


def _view(p, role: Role | None = None) -> dict:
    d = p.to_dict()
    d["ago"] = _ago(p.created_at)
    if role is not None:
        # The caller's role in this project — the UI uses it for a badge and to
        # gate management actions (Owner/Admin can manage members & settings).
        d["role"] = role.value
    return d


@router.get("/projects")
def list_projects() -> dict:
    user = current_user()
    # Owned + projects shared to the caller (M7 C2), each with their role.
    return {"projects": [_view(p, role) for (p, role) in db.list_projects_for(user.id)]}


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
    return _view(p, Role.OWNER)


@router.get("/projects/{project_id}")
def get_project(project_id: str) -> dict:
    # Access = owner OR member (M7 C2); a project you can't see 404s, not leaks config.
    role = _require_access(project_id, current_user().id)
    p = db.get_project(project_id)
    assert p is not None
    return _view(p, role)


@router.patch("/projects/{project_id}")
def update_project(project_id: str, body: UpdateProjectBody) -> dict:
    role = _require_manage(project_id, current_user().id)
    updated = db.update_project(
        project_id,
        name=body.name,
        instruction=body.instruction,
        connectors=body.connectors,
        experts=body.experts,
        skills=body.skills,
    )
    return _view(updated, role)


@router.get("/projects/{project_id}/sessions")
def project_sessions(project_id: str) -> dict:
    _require_access(project_id, current_user().id)
    rows = db.list_project_sessions(project_id)
    return {"sessions": [{**s.to_dict(), "ago": _ago(s.updated_at)} for s in rows]}


# ---- members (M7 C2) ----------------------------------------------------

@router.get("/projects/{project_id}/members")
def list_members(project_id: str) -> dict:
    _require_access(project_id, current_user().id)
    return {"members": db.list_project_members(project_id)}


@router.post("/projects/{project_id}/members")
def add_member(project_id: str, body: AddMemberBody) -> dict:
    _require_manage(project_id, current_user().id)
    role = _member_role(body.role)
    found = db.get_user_by_name((body.name or "").strip())
    if not found:
        raise HTTPException(404, "用户不存在")
    target = found[0]
    p = db.get_project(project_id)
    if p and target.id == p.owner_id:
        raise HTTPException(400, "该用户已是项目所有者")
    db.add_project_member(project_id, target.id, role)
    return {"members": db.list_project_members(project_id)}


@router.patch("/projects/{project_id}/members/{user_id}")
def update_member(project_id: str, user_id: str, body: UpdateMemberBody) -> dict:
    _require_manage(project_id, current_user().id)
    role = _member_role(body.role)
    if db.project_member_role(project_id, user_id) is None:
        raise HTTPException(404, "成员不存在")
    db.add_project_member(project_id, user_id, role)  # upsert = change role
    return {"members": db.list_project_members(project_id)}


@router.delete("/projects/{project_id}/members/{user_id}")
def remove_member(project_id: str, user_id: str) -> dict:
    me = current_user()
    # Leaving (removing yourself) needs only access; removing others needs manage.
    if user_id == me.id:
        _require_access(project_id, me.id)
    else:
        _require_manage(project_id, me.id)
    db.remove_project_member(project_id, user_id)
    return {"ok": True}
