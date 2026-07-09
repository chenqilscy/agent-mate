"""项目里程碑 / 迭代 milestones（WB-105）。

项目级里程碑，团队共享。access-gated（owner OR 成员）；Viewer 只读、Member+ 可写。
work_items 通过 milestone_id 归属某里程碑；删除里程碑会解绑其下任务（不删任务）。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db
from auth import CurrentAccount
from models import Account, Role, can_write

router = APIRouter(prefix="/api", tags=["milestones"])

_STATUSES = {"open", "closed"}


def _access(project_id: str, account: Account) -> Role:
    role = db.project_access_role(project_id, account.id)
    if role is None:
        raise HTTPException(404, "project not found")
    return role


def _require_write(project_id: str, account: Account) -> None:
    if not can_write(_access(project_id, account)):
        raise HTTPException(403, "Viewer is read-only")


@router.get("/projects/{project_id}/milestones")
def list_items(project_id: str, account: Account = CurrentAccount) -> dict:
    _access(project_id, account)
    return {"milestones": db.list_milestones(project_id)}


class CreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    due_date: str = ""            # YYYY-MM-DD
    status: str = "open"


@router.post("/projects/{project_id}/milestones")
def create_item(project_id: str, body: CreateBody, account: Account = CurrentAccount) -> dict:
    _require_write(project_id, account)
    status = body.status if body.status in _STATUSES else "open"
    return db.create_milestone(
        project_id=project_id, name=body.name.strip(),
        description=body.description, due_date=body.due_date, status=status,
    )


class UpdateBody(BaseModel):
    name: str | None = None
    description: str | None = None
    due_date: str | None = None
    status: str | None = None
    sort: int | None = None


@router.patch("/projects/{project_id}/milestones/{mid}")
def update_item(project_id: str, mid: str, body: UpdateBody, account: Account = CurrentAccount) -> dict:
    _require_write(project_id, account)
    if body.status is not None and body.status not in _STATUSES:
        raise HTTPException(400, "invalid status")
    it = db.get_milestone(mid)
    if not it or it["project_id"] != project_id:
        raise HTTPException(404, "milestone not found")
    updated = db.update_milestone(mid, **body.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(404, "milestone not found")
    return updated


@router.delete("/projects/{project_id}/milestones/{mid}")
def delete_item(project_id: str, mid: str, account: Account = CurrentAccount) -> dict:
    _require_write(project_id, account)
    it = db.get_milestone(mid)
    if not it or it["project_id"] != project_id:
        raise HTTPException(404, "milestone not found")
    db.delete_milestone(mid)
    return {"ok": True}
