"""组织 / 团队（WB-061）。owner 由 orgs.owner_id 记；成员 Admin/Member/Viewer 在 org_members。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db
from auth import CurrentAccount, parse_member_role
from models import Account, Role, can_manage

router = APIRouter(prefix="/api", tags=["orgs"])


class CreateOrgBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.post("/orgs")
def create_org(body: CreateOrgBody, account: Account = CurrentAccount) -> dict:
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "empty org name")
    o = db.create_org(name=name, owner_id=account.id)
    return {**o.to_dict(), "role": Role.OWNER.value}


@router.get("/orgs")
def list_orgs(account: Account = CurrentAccount) -> dict:
    return {"orgs": [{**o.to_dict(), "role": r.value} for o, r in db.list_orgs_for(account.id)]}


@router.get("/orgs/{org_id}/members")
def org_members(org_id: str, account: Account = CurrentAccount) -> dict:
    if db.org_role(org_id, account.id) is None:
        raise HTTPException(404, "org not found")
    return {"members": db.list_org_members(org_id)}


class AddOrgMemberBody(BaseModel):
    name: str  # 按账号名加入
    role: str = "Member"


@router.post("/orgs/{org_id}/members")
def add_org_member(org_id: str, body: AddOrgMemberBody, account: Account = CurrentAccount) -> dict:
    if not can_manage(db.org_role(org_id, account.id)):
        raise HTTPException(403, "requires Admin/Owner")
    role = parse_member_role(body.role)
    target = db.find_account_by_name((body.name or "").strip())
    if not target:
        raise HTTPException(404, "no such account")
    org = db.get_org(org_id)
    if org and target.id == org.owner_id:
        raise HTTPException(400, "owner is not a member")
    db.add_org_member(org_id, target.id, role)
    return {"ok": True, "member": {"account_id": target.id, "name": target.name, "role": role.value}}


class OrgModelPolicyBody(BaseModel):
    allowlist: list[str] = Field(default=[], max_length=50)
    fallback_chain: list[str] = Field(default=[], max_length=50)
    daily_soft_tokens: int = Field(default=0, ge=0, le=1_000_000_000)
    daily_hard_tokens: int = Field(default=0, ge=0, le=1_000_000_000)
    monthly_soft_tokens: int = Field(default=0, ge=0, le=1_000_000_000)
    monthly_hard_tokens: int = Field(default=0, ge=0, le=1_000_000_000)
    daily_soft_cost: float = Field(default=0, ge=0, le=1_000_000_000)
    daily_hard_cost: float = Field(default=0, ge=0, le=1_000_000_000)
    monthly_soft_cost: float = Field(default=0, ge=0, le=1_000_000_000)
    monthly_hard_cost: float = Field(default=0, ge=0, le=1_000_000_000)
    currency: str = Field(default="USD", min_length=1, max_length=8)
    provider_health_ttl_seconds: int = Field(default=900, ge=60, le=86400)
    credential_max_age_days: int = Field(default=90, ge=0, le=3650)


@router.get("/orgs/model-policies")
def list_model_policies(account: Account = CurrentAccount) -> dict:
    return {"policies": db.list_org_model_policies_for(account.id)}


@router.get("/orgs/{org_id}/model-policy")
def get_model_policy(org_id: str, account: Account = CurrentAccount) -> dict:
    if db.org_role(org_id, account.id) is None:
        raise HTTPException(404, "org not found")
    return db.get_org_model_policy(org_id) or {
        "org_id": org_id, "policy": OrgModelPolicyBody().model_dump(),
        "revision": 0, "updated_by": "", "updated_at": 0,
    }


@router.put("/orgs/{org_id}/model-policy")
def set_model_policy(
    org_id: str, body: OrgModelPolicyBody, account: Account = CurrentAccount,
) -> dict:
    if not can_manage(db.org_role(org_id, account.id)):
        raise HTTPException(403, "requires Admin/Owner")
    policy = body.model_dump()
    policy["allowlist"] = list(dict.fromkeys(value.strip() for value in policy["allowlist"] if value.strip()))
    policy["fallback_chain"] = list(dict.fromkeys(value.strip() for value in policy["fallback_chain"] if value.strip()))
    policy["currency"] = policy["currency"].strip().upper()
    return db.set_org_model_policy(org_id, policy, account.id)
