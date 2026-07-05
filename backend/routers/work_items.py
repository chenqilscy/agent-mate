"""Work items — kanban / task list (§11 阶段 B). 计划 and 任务 share this source."""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth.deps import current_user
from storage import db

router = APIRouter(prefix="/api", tags=["work_items"])

STATUSES = {"todo", "doing", "paused", "done"}


class CreateWorkItemBody(BaseModel):
    project_id: str
    title: str
    status: str = "todo"
    source: str = "手动"


class UpdateWorkItemBody(BaseModel):
    title: str | None = None
    status: str | None = None


def _ago(ts: float) -> str:
    diff = max(0, time.time() - ts)
    if diff < 60:
        return "刚刚"
    if diff < 3600:
        return f"{int(diff // 60)}分钟前"
    if diff < 86400:
        return f"{int(diff // 3600)}小时前"
    return f"{int(diff // 86400)}天前"


def _view(wi, user) -> dict:
    d = wi.to_dict()
    d["ago"] = _ago(wi.created_at)
    d["assignee_name"] = user.name if wi.assignee == user.id else wi.assignee[:2]
    return d


@router.get("/work-items")
def list_items(project: str) -> dict:
    user = current_user()
    return {"items": [_view(wi, user) for wi in db.list_work_items(project)]}


@router.post("/work-items")
def create_item(body: CreateWorkItemBody) -> dict:
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(400, "empty title")
    status = body.status if body.status in STATUSES else "todo"
    user = current_user()
    wi = db.create_work_item(
        project_id=body.project_id, owner_id=user.id, title=title, status=status, source=body.source,
    )
    return _view(wi, user)


@router.patch("/work-items/{item_id}")
def update_item(item_id: str, body: UpdateWorkItemBody) -> dict:
    if body.status is not None and body.status not in STATUSES:
        raise HTTPException(400, "bad status")
    wi = db.update_work_item(item_id, title=body.title, status=body.status)
    if not wi:
        raise HTTPException(404, "work item not found")
    return _view(wi, current_user())


@router.delete("/work-items/{item_id}")
def delete_item(item_id: str) -> dict:
    db.delete_work_item(item_id)
    return {"ok": True}
