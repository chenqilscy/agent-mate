"""团队计划/任务 work_items（WB-081）。

项目级看板/任务，团队共享。access-gated（owner OR 成员）；Viewer 只读、Member+ 可写。
本地 App 的 work_items 目前是本地独有；本地⇄Hub 双向同步为后续（见 WB-081 处理记录）。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db
from auth import CurrentAccount
from models import Account, Role, can_write

router = APIRouter(prefix="/api", tags=["work-items"])

_STATUSES = {"todo", "doing", "paused", "done"}


def _access(project_id: str, account: Account) -> Role:
    role = db.project_access_role(project_id, account.id)
    if role is None:
        raise HTTPException(404, "project not found")
    return role


def _require_write(project_id: str, account: Account) -> None:
    if not can_write(_access(project_id, account)):
        raise HTTPException(403, "Viewer is read-only")


@router.get("/projects/{project_id}/work-items")
def list_items(project_id: str, account: Account = CurrentAccount) -> dict:
    _access(project_id, account)
    return {"items": db.list_work_items(project_id)}


class CreateBody(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    status: str = "todo"
    source: str = "手动"
    assignee: str = ""
    description: str = ""


@router.post("/projects/{project_id}/work-items")
def create_item(project_id: str, body: CreateBody, account: Account = CurrentAccount) -> dict:
    _require_write(project_id, account)
    status = body.status if body.status in _STATUSES else "todo"
    return db.create_work_item(
        project_id=project_id, title=body.title.strip(), status=status,
        source=body.source, assignee=body.assignee, description=body.description,
    )


class UpdateBody(BaseModel):
    title: str | None = None
    status: str | None = None
    source: str | None = None
    assignee: str | None = None
    description: str | None = None
    sort: int | None = None


@router.patch("/projects/{project_id}/work-items/{wid}")
def update_item(project_id: str, wid: str, body: UpdateBody, account: Account = CurrentAccount) -> dict:
    _require_write(project_id, account)
    if body.status is not None and body.status not in _STATUSES:
        raise HTTPException(400, "invalid status")
    it = db.get_work_item(wid)
    if not it or it["project_id"] != project_id:
        raise HTTPException(404, "work item not found")
    updated = db.update_work_item(wid, **body.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(404, "work item not found")
    return updated


@router.delete("/projects/{project_id}/work-items/{wid}")
def delete_item(project_id: str, wid: str, account: Account = CurrentAccount) -> dict:
    _require_write(project_id, account)
    it = db.get_work_item(wid)
    if not it or it["project_id"] != project_id:
        raise HTTPException(404, "work item not found")
    db.delete_work_item(wid)
    return {"ok": True}
