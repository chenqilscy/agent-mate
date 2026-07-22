"""项目 CRUD + 成员/角色（WB-061）。access = owner OR 成员；单闸 project_access_role。
Viewer 只读、Member+ 可写、Admin+ 可管成员——与本地 backend 语义一致。"""
from __future__ import annotations
import time

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import db
from auth import CurrentAccount, parse_member_role
from models import Account, Role, can_manage, can_write

router = APIRouter(prefix="/api", tags=["projects"])


def _view(project, role: Role) -> dict:
    """Project downlink includes only ready project-scoped central KB bindings."""
    return {
        **project.to_dict(),
        "role": role.value,
        "knowledge_ids": db.list_ready_kb_ids(project.id),
    }


class CreateProjectBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    org_id: str | None = None
    instruction: str = Field(default="", max_length=20000)
    connectors: list[str] = Field(default_factory=list, max_length=100)
    experts: list[str] = Field(default_factory=list, max_length=100)
    skills: list[str] = Field(default_factory=list, max_length=100)


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
    skills = db.canonical_skill_keys(body.skills)
    _validate_loadout({"connectors": body.connectors, "experts": body.experts, "skills": skills})
    p = db.create_project(
        name=name, owner_id=account.id, org_id=body.org_id, instruction=body.instruction,
        connectors=body.connectors, experts=body.experts, skills=skills,
    )
    return _view(p, Role.OWNER)


@router.get("/projects")
def list_projects(include_archived: bool = Query(default=False), account: Account = CurrentAccount) -> dict:
    return {"projects": [_view(p, r) for p, r in db.list_projects_for(account.id, include_archived=include_archived)]}


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
    return _view(p, role)


class UpdateProjectBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    org_id: str | None = None
    instruction: str | None = Field(default=None, max_length=20000)
    connectors: list[str] | None = Field(default=None, max_length=100)
    experts: list[str] | None = Field(default=None, max_length=100)
    skills: list[str] | None = Field(default=None, max_length=100)


def _catalog_values(category: str) -> set[str]:
    values: set[str] = set()
    for item in db.list_catalog_items(category, scope="builtin"):
        data = item.get("data")
        if not isinstance(data, dict):
            continue
        for key in ("slug", "key", "name", "title", "value"):
            value = str(data.get(key) or "").strip()
            if value:
                values.add(value)
    return values


def _validate_loadout(patch: dict) -> None:
    categories = {"connectors": "NP_CONNS", "experts": "EXPERT_DEFS", "skills": "APP_SKILLS"}
    for key, category in categories.items():
        if key not in patch:
            continue
        allowed = _catalog_values(category)
        unknown = [value for value in patch[key] if value not in allowed]
        if unknown:
            raise HTTPException(400, f"unknown {key}: {unknown[0]}")


@router.patch("/projects/{project_id}")
def update_project(project_id: str, body: UpdateProjectBody, account: Account = CurrentAccount) -> dict:
    role = _require_access(project_id, account)
    if not can_manage(role):
        raise HTTPException(403, "requires Admin/Owner")
    if db.project_is_archived(project_id):
        raise HTTPException(409, "archived project is read-only")
    patch = body.model_dump(exclude_unset=True)
    if "name" in patch:
        patch["name"] = str(patch["name"] or "").strip()
        if not patch["name"]:
            raise HTTPException(400, "empty project name")
    if "org_id" in patch:
        if role != Role.OWNER:
            raise HTTPException(403, "only Owner can change organization")
        if patch["org_id"]:
            org_role = db.org_role(str(patch["org_id"]), account.id)
            if org_role is None or not can_write(org_role):
                raise HTTPException(404, "org not found")
    if "skills" in patch:
        patch["skills"] = db.canonical_skill_keys(patch["skills"])
    _validate_loadout(patch)
    p = db.update_project(project_id, **patch)
    assert p is not None
    return _view(p, role)


class TransferProjectBody(BaseModel):
    account_id: str = Field(min_length=1)


@router.post("/projects/{project_id}/transfer")
def transfer_project(project_id: str, body: TransferProjectBody, account: Account = CurrentAccount) -> dict:
    if _require_access(project_id, account) != Role.OWNER:
        raise HTTPException(403, "only Owner can transfer project")
    if db.project_is_archived(project_id):
        raise HTTPException(409, "restore project before transfer")
    updated = db.transfer_project_owner(project_id, account.id, body.account_id)
    if not updated:
        raise HTTPException(400, "new owner must be an existing Member or Admin")
    return _view(updated, Role.ADMIN)


@router.post("/projects/{project_id}/archive")
def archive_project(project_id: str, account: Account = CurrentAccount) -> dict:
    if _require_access(project_id, account) != Role.OWNER:
        raise HTTPException(403, "only Owner can archive project")
    updated = db.update_project(project_id, archived_at=time.time())
    assert updated is not None
    return _view(updated, Role.OWNER)


@router.post("/projects/{project_id}/restore")
def restore_project(project_id: str, account: Account = CurrentAccount) -> dict:
    if _require_access(project_id, account) != Role.OWNER:
        raise HTTPException(403, "only Owner can restore project")
    updated = db.update_project(project_id, archived_at=0)
    assert updated is not None
    return _view(updated, Role.OWNER)


class DeleteProjectBody(BaseModel):
    confirm_name: str


@router.delete("/projects/{project_id}")
def remove_project(project_id: str, body: DeleteProjectBody, account: Account = CurrentAccount) -> dict:
    if _require_access(project_id, account) != Role.OWNER:
        raise HTTPException(403, "only Owner can delete project")
    project = db.get_project(project_id)
    assert project is not None
    if not db.project_is_archived(project_id):
        raise HTTPException(409, "archive project before deletion")
    if body.confirm_name.strip() != project.name:
        raise HTTPException(400, "project name confirmation mismatch")
    counts = db.project_delete_counts(project_id)
    if counts["knowledge_bases"]:
        raise HTTPException(409, "delete project knowledge bases first")
    if not db.delete_project(project_id):
        raise HTTPException(404, "project not found")
    return {"ok": True, "deleted": counts}


@router.get("/projects/{project_id}/members")
def project_members(project_id: str, account: Account = CurrentAccount) -> dict:
    _require_access(project_id, account)
    return {"members": db.list_project_members(project_id)}


class AddProjectMemberBody(BaseModel):
    name: str
    role: str = "Member"


@router.post("/projects/{project_id}/members")
def add_project_member(project_id: str, body: AddProjectMemberBody, account: Account = CurrentAccount) -> dict:
    if db.project_is_archived(project_id):
        raise HTTPException(409, "archived project is read-only")
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
    if db.project_is_archived(project_id):
        raise HTTPException(409, "archived project is read-only")
    if not can_manage(_require_access(project_id, account)):
        raise HTTPException(403, "requires Admin/Owner")
    role = parse_member_role(body.role)
    if db.project_member_role(project_id, account_id) is None:
        raise HTTPException(404, "not a member")
    db.add_project_member(project_id, account_id, role)  # upsert = change role
    return {"ok": True, "role": role.value}


@router.delete("/projects/{project_id}/members/{account_id}")
def remove_member(project_id: str, account_id: str, account: Account = CurrentAccount) -> dict:
    if db.project_is_archived(project_id):
        raise HTTPException(409, "archived project is read-only")
    role = _require_access(project_id, account)
    # 自己退出，或 Admin/Owner 移除他人。
    if account_id != account.id and not can_manage(role):
        raise HTTPException(403, "requires Admin/Owner")
    db.remove_project_member(project_id, account_id)
    return {"ok": True}
