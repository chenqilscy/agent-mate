"""安全中心（WB-152）：命令安全策略（黑名单）+ 审计日志，按 owner 隔离。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agent import security
from auth.deps import current_user
from storage import db

router = APIRouter(prefix="/api/security", tags=["security"])


class PolicyBody(BaseModel):
    command_blocklist: list[str] = Field(default_factory=list)


@router.get("/policy")
def get_policy() -> dict:
    return {"command_blocklist": security.get_command_blocklist(current_user().id)}


@router.put("/policy")
def put_policy(body: PolicyBody) -> dict:
    owner = current_user().id
    saved = security.set_command_blocklist(owner, body.command_blocklist)
    return {"command_blocklist": saved}


@router.get("/audit")
def get_audit() -> dict:
    return {"items": db.list_audit(current_user().id, limit=100)}


@router.post("/audit/clear")
def clear_audit() -> dict:
    return {"ok": True, "removed": db.clear_audit(current_user().id)}
