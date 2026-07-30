"""邀请码（WB-061）：Admin+ 为项目生成邀请码；被邀请者接受后加为项目成员（角色由邀请指定）。"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import db
from auth import CurrentAccount, parse_member_role
import platform_settings
from models import Account, can_manage

router = APIRouter(prefix="/api", tags=["invites"])


class CreateInviteBody(BaseModel):
    role: str = "Member"


@router.post("/projects/{project_id}/invites")
def create_invite(project_id: str, body: CreateInviteBody, account: Account = CurrentAccount) -> dict:
    role_here = db.project_access_role(project_id, account.id)
    if role_here is None:
        raise HTTPException(404, "project not found")
    if not can_manage(role_here):
        raise HTTPException(403, "requires Admin/Owner")
    if db.project_is_archived(project_id):
        raise HTTPException(409, "archived project is read-only")
    role = parse_member_role(body.role)
    inv = db.create_invite(
        project_id=project_id, role=role, created_by=account.id,
        ttl=int(platform_settings.effective("collaboration.invite_ttl_seconds")),
    )
    return inv.to_dict()


@router.get("/invites/{code}")
def get_invite(code: str, account: Account = CurrentAccount) -> dict:
    inv = db.get_invite_by_code(code)
    if not inv:
        raise HTTPException(404, "invite not found")
    p = db.get_project(inv.project_id)
    return {**inv.to_dict(), "project_name": p.name if p else None, "accepted": inv.accepted_by is not None}


@router.post("/invites/{code}/accept")
def accept_invite(code: str, account: Account = CurrentAccount) -> dict:
    inv = db.get_invite_by_code(code)
    if not inv:
        raise HTTPException(404, "invite not found")
    if inv.expires_at and time.time() > inv.expires_at:
        raise HTTPException(410, "invite expired")
    # 单次使用：一个邀请码接受一次即作废，否则泄漏后可被反复用于自助入项目（WB-156）。
    if inv.accepted_by is not None:
        raise HTTPException(409, "邀请码已被使用")
    p = db.get_project(inv.project_id)
    if not p:
        raise HTTPException(404, "project no longer exists")
    if p.archived_at:
        raise HTTPException(409, "project is archived")
    if account.id == p.owner_id:
        raise HTTPException(400, "you already own this project")
    if not db.accept_invite_once(inv.id, inv.project_id, account.id, inv.role):
        # Another request consumed the invite after our read.
        raise HTTPException(409, "邀请码已被使用")
    return {"ok": True, "project_id": inv.project_id, "role": inv.role.value}
