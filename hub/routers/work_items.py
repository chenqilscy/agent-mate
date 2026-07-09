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
_PRIORITIES = {"", "low", "medium", "high", "urgent"}
# 记入活动流的关键字段（值变化时逐条留痕，来自真实操作）。
_TRACKED = ("status", "assignee", "priority", "due_date", "milestone_id")


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
    priority: str = ""            # '' | low | medium | high | urgent
    due_date: str = ""            # YYYY-MM-DD
    start_date: str = ""
    labels: list[str] = Field(default_factory=list)
    parent_id: str = ""           # 自引用 → 子任务
    milestone_id: str = ""


@router.post("/projects/{project_id}/work-items")
def create_item(project_id: str, body: CreateBody, account: Account = CurrentAccount) -> dict:
    _require_write(project_id, account)
    status = body.status if body.status in _STATUSES else "todo"
    priority = body.priority if body.priority in _PRIORITIES else ""
    item = db.create_work_item(
        project_id=project_id, title=body.title.strip(), status=status,
        source=body.source, assignee=body.assignee, description=body.description,
        priority=priority, due_date=body.due_date, start_date=body.start_date,
        labels=body.labels, parent_id=body.parent_id, milestone_id=body.milestone_id,
    )
    db.log_work_item_activity(project_id=project_id, work_item_id=item["id"],
                              actor=account.name, kind="created", detail=item["title"])
    return item


class UpdateBody(BaseModel):
    title: str | None = None
    status: str | None = None
    source: str | None = None
    assignee: str | None = None
    description: str | None = None
    sort: int | None = None
    priority: str | None = None
    due_date: str | None = None
    start_date: str | None = None
    labels: list[str] | None = None
    parent_id: str | None = None
    milestone_id: str | None = None


@router.patch("/projects/{project_id}/work-items/{wid}")
def update_item(project_id: str, wid: str, body: UpdateBody, account: Account = CurrentAccount) -> dict:
    _require_write(project_id, account)
    if body.status is not None and body.status not in _STATUSES:
        raise HTTPException(400, "invalid status")
    it = db.get_work_item(wid)
    if not it or it["project_id"] != project_id:
        raise HTTPException(404, "work item not found")
    changes = body.model_dump(exclude_unset=True)
    if "priority" in changes and changes["priority"] not in _PRIORITIES:
        changes["priority"] = ""    # 宽松：非法优先级归空，不打断 App 同步
    updated = db.update_work_item(wid, **changes)
    if not updated:
        raise HTTPException(404, "work item not found")
    # 活动流：关键字段变化逐条留痕
    for k in _TRACKED:
        if k in changes and str(changes[k]) != str(it.get(k, "")):
            db.log_work_item_activity(project_id=project_id, work_item_id=wid, actor=account.name,
                                      kind=k, detail=f"{it.get(k, '')}→{changes[k]}")
    return updated


@router.delete("/projects/{project_id}/work-items/{wid}")
def delete_item(project_id: str, wid: str, account: Account = CurrentAccount) -> dict:
    _require_write(project_id, account)
    it = db.get_work_item(wid)
    if not it or it["project_id"] != project_id:
        raise HTTPException(404, "work item not found")
    db.delete_work_item(wid)
    return {"ok": True}


@router.get("/projects/{project_id}/work-items/{wid}/activity")
def item_activity(project_id: str, wid: str, account: Account = CurrentAccount) -> dict:
    _access(project_id, account)
    return {"activity": db.list_work_item_activity(project_id, wid)}


@router.get("/projects/{project_id}/activity")
def project_activity(project_id: str, account: Account = CurrentAccount) -> dict:
    _access(project_id, account)
    return {"activity": db.list_work_item_activity(project_id)}
