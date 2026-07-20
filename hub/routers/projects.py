"""项目 CRUD + 成员/角色（WB-061）。access = owner OR 成员；单闸 project_access_role。
Viewer 只读、Member+ 可写、Admin+ 可管成员——与本地 backend 语义一致。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db
from auth import CurrentAccount, parse_member_role
from models import Account, Role, can_manage, can_write

router = APIRouter(prefix="/api", tags=["projects"])


class CreateProjectBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    org_id: str | None = None
    instruction: str = ""
    connectors: list[str] = []
    experts: list[str] = []
    skills: list[str] = []


@router.post("/projects")
def create_project(body: CreateProjectBody, account: Account = CurrentAccount) -> dict:
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "empty project name")
    if body.org_id:
        org_r = db.org_role(body.org_id, account.id)
        if org_r is None:
            raise HTTPException(404, "org not found")  # 只能在自己有权的组织下建项目
        if not can_write(org_r):
            raise HTTPException(403, "只读组织成员不能建项目")  # WB-156
    p = db.create_project(
        name=name, owner_id=account.id, org_id=body.org_id, instruction=body.instruction,
        connectors=body.connectors, experts=body.experts, skills=db.canonical_skill_keys(body.skills),
    )
    return {**p.to_dict(), "role": Role.OWNER.value}


@router.get("/projects")
def list_projects(account: Account = CurrentAccount) -> dict:
    return {"projects": [{**p.to_dict(), "role": r.value} for p, r in db.list_projects_for(account.id)]}


def _require_access(project_id: str, account: Account) -> Role:
    role = db.project_access_role(project_id, account.id)
    if role is None:
        raise HTTPException(404, "project not found")
    return role


@router.get("/projects/{project_id}")
def get_project(project_id: str, account: Account = CurrentAccount) -> dict:
    role = _require_access(project_id, account)
    p = db.get_project(project_id)
    assert p is not None
    return {**p.to_dict(), "role": role.value}


class UpdateProjectBody(BaseModel):
    name: str | None = None
    instruction: str | None = None
    connectors: list[str] | None = None
    experts: list[str] | None = None
    skills: list[str] | None = None


@router.patch("/projects/{project_id}")
def update_project(project_id: str, body: UpdateProjectBody, account: Account = CurrentAccount) -> dict:
    role = _require_access(project_id, account)
    if not can_write(role):
        raise HTTPException(403, "Viewer is read-only")
    patch = body.model_dump(exclude_unset=True)
    if "skills" in patch:
        patch["skills"] = db.canonical_skill_keys(patch["skills"])
    p = db.update_project(project_id, **patch)
    assert p is not None
    return {**p.to_dict(), "role": role.value}


@router.get("/projects/{project_id}/members")
def project_members(project_id: str, account: Account = CurrentAccount) -> dict:
    _require_access(project_id, account)
    return {"members": db.list_project_members(project_id)}


class AddProjectMemberBody(BaseModel):
    name: str
    role: str = "Member"


@router.post("/projects/{project_id}/members")
def add_project_member(project_id: str, body: AddProjectMemberBody, account: Account = CurrentAccount) -> dict:
    if not can_manage(_require_access(project_id, account)):
        raise HTTPException(403, "requires Admin/Owner")
    role = parse_member_role(body.role)
    target = db.find_account_by_name((body.name or "").strip())
    if not target:
        raise HTTPException(404, "no such account")
    p = db.get_project(project_id)
    if p and target.id == p.owner_id:
        raise HTTPException(400, "owner is not a member")
    db.add_project_member(project_id, target.id, role)
    return {"ok": True, "member": {"account_id": target.id, "name": target.name, "role": role.value}}


class ChangeRoleBody(BaseModel):
    role: str


@router.patch("/projects/{project_id}/members/{account_id}")
def change_member_role(project_id: str, account_id: str, body: ChangeRoleBody, account: Account = CurrentAccount) -> dict:
    if not can_manage(_require_access(project_id, account)):
        raise HTTPException(403, "requires Admin/Owner")
    role = parse_member_role(body.role)
    if db.project_member_role(project_id, account_id) is None:
        raise HTTPException(404, "not a member")
    db.add_project_member(project_id, account_id, role)  # upsert = change role
    return {"ok": True, "role": role.value}


@router.delete("/projects/{project_id}/members/{account_id}")
def remove_member(project_id: str, account_id: str, account: Account = CurrentAccount) -> dict:
    role = _require_access(project_id, account)
    # 自己退出，或 Admin/Owner 移除他人。
    if account_id != account.id and not can_manage(role):
        raise HTTPException(403, "requires Admin/Owner")
    db.remove_project_member(project_id, account_id)
    return {"ok": True}
