"""Work items — kanban / task list (§11 阶段 B). 计划 and 任务 share this source."""
from __future__ import annotations

import time

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth.deps import current_user
from storage import db

router = APIRouter(prefix="/api", tags=["work_items"])

STATUSES = {"todo", "doing", "paused", "done"}
MAX_ATTACHMENTS = 20


def _clean_attachments(raw: Any) -> list[dict]:
    """只保留 {name, kind, path} 形状的引用，防止塞进任意 JSON。不复制文件、只存引用。"""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for a in raw[:MAX_ATTACHMENTS]:
        if not isinstance(a, dict):
            continue
        name = str(a.get("name", "")).strip()[:200]
        if not name:
            continue
        kind = a.get("kind") if a.get("kind") in ("local", "asset") else "local"
        path = a.get("path")
        out.append({"name": name, "kind": kind, "path": str(path)[:500] if path else None})
    return out


class CreateWorkItemBody(BaseModel):
    project_id: str
    title: str
    status: str = "todo"
    source: str = "手动"
    description: str = ""
    due_date: str | None = None
    attachments: list[dict] = []


class UpdateWorkItemBody(BaseModel):
    title: str | None = None
    status: str | None = None
    description: str | None = None
    due_date: str | None = None
    attachments: list[dict] | None = None


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
    # Only list a project's items if the caller owns the project (WB-013).
    if not db.get_project(project, owner_id=user.id):
        raise HTTPException(404, "project not found")
    return {"items": [_view(wi, user) for wi in db.list_work_items(project)]}


@router.post("/work-items")
def create_item(body: CreateWorkItemBody) -> dict:
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(400, "empty title")
    status = body.status if body.status in STATUSES else "todo"
    user = current_user()
    # Only create in a project the caller owns (WB-013).
    if not db.get_project(body.project_id, owner_id=user.id):
        raise HTTPException(404, "project not found")
    wi = db.create_work_item(
        project_id=body.project_id, owner_id=user.id, title=title, status=status, source=body.source,
        description=(body.description or "").strip(), due_date=(body.due_date or None),
        attachments=_clean_attachments(body.attachments),
    )
    return _view(wi, user)


@router.patch("/work-items/{item_id}")
def update_item(item_id: str, body: UpdateWorkItemBody) -> dict:
    if body.status is not None and body.status not in STATUSES:
        raise HTTPException(400, "bad status")
    user = current_user()
    if not db.get_work_item(item_id, owner_id=user.id):
        raise HTTPException(404, "work item not found")
    # due_date is nullable: an explicit `due_date: null` clears it; omitting leaves it.
    fields = body.model_fields_set
    wi = db.update_work_item(
        item_id,
        title=body.title,
        status=body.status,
        description=body.description,
        due_date=body.due_date if "due_date" in fields else None,
        clear_due_date="due_date" in fields and body.due_date is None,
        attachments=_clean_attachments(body.attachments) if body.attachments is not None else None,
    )
    if not wi:
        raise HTTPException(404, "work item not found")
    return _view(wi, user)


@router.delete("/work-items/{item_id}")
def delete_item(item_id: str) -> dict:
    if not db.get_work_item(item_id, owner_id=current_user().id):
        raise HTTPException(404, "work item not found")
    db.delete_work_item(item_id)
    return {"ok": True}
