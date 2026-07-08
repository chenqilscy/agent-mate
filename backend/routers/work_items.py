"""Work items — kanban / task list (§11 阶段 B). 计划 and 任务 share this source."""
from __future__ import annotations

import time

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

import hub_client
from auth.deps import current_user
from storage import db
from storage.models import Role

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


# ---- Hub 代理（WB-091）：hub-origin 项目的 work_items 走 Hub 权威（团队共享）----
# 读时把 Hub 结果镜像进本地（离线兜底 + 让 update/delete 能按 id 定位 project）；
# 写时代理到 Hub 再刷新镜像。Hub 不可达 → 回退纯本地（离线优先，铁律 6 回退）。

def _bearer(authorization: str) -> str:
    return authorization[7:].strip() if authorization[:7].lower() == "bearer " else ""


def _hub_token(project_id: str, authorization: str) -> str:
    """该项目是否应走 Hub 代理：hub-origin 镜像项目 + 已接 Hub + 请求带 token → 返回 bearer，否则 ""。"""
    if not hub_client.hub_enabled():
        return ""
    tok = _bearer(authorization)
    if not tok:
        return ""
    proj = db.get_project(project_id)
    if not proj or getattr(proj, "origin", "local") != "hub":
        return ""
    return tok


def _hub_view(it: dict) -> dict:
    """Hub work_item → 前端期望的视图形状（补齐本地专有字段：owner_id/due_date/attachments）。"""
    ca = it.get("created_at") or 0
    return {
        "id": it.get("id"), "project_id": it.get("project_id"), "owner_id": "",
        "title": it.get("title", ""), "status": it.get("status", "todo"),
        "source": it.get("source", "手动"), "assignee": it.get("assignee", ""),
        "description": it.get("description", ""), "due_date": None, "attachments": [],
        "created_at": ca, "updated_at": it.get("updated_at") or ca,
        "ago": _ago(ca), "assignee_name": (it.get("assignee", "") or "")[:2],
    }


def _require_project_write(project_id: str, user_id: str) -> None:
    """Members (Owner/Admin/Member) may write a project's items; Viewer is read-only;
    non-members 404 (M7 C2)."""
    role = db.project_access_role(project_id, user_id)
    if role is None:
        raise HTTPException(404, "project not found")
    if role == Role.VIEWER:
        raise HTTPException(403, "只读成员不能修改任务")


@router.get("/work-items")
def list_items(project: str, authorization: str = Header(default="")) -> dict:
    user = current_user()
    # Any member (incl. Viewer) can see a project's items (M7 C2).
    if not db.get_project_for(project, user.id):
        raise HTTPException(404, "project not found")
    tok = _hub_token(project, authorization)
    if tok:
        items = hub_client.list_work_items(tok, project)  # None = Hub 不可达
        if items is not None:
            db.mirror_hub_work_items(project, items)       # 刷新本地镜像
            return {"items": [_hub_view(it) for it in items]}
    return {"items": [_view(wi, user) for wi in db.list_work_items(project)]}


@router.post("/work-items")
def create_item(body: CreateWorkItemBody, authorization: str = Header(default="")) -> dict:
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(400, "empty title")
    status = body.status if body.status in STATUSES else "todo"
    user = current_user()
    _require_project_write(body.project_id, user.id)
    tok = _hub_token(body.project_id, authorization)
    if tok:
        created = hub_client.create_work_item(
            tok, body.project_id,
            {"title": title, "status": status, "source": body.source,
             "description": (body.description or "").strip()},
        )
        if created:
            items = hub_client.list_work_items(tok, body.project_id)
            if items is not None:
                db.mirror_hub_work_items(body.project_id, items)  # 让新项本地可定位
            return _hub_view(created)
        # Hub 不可达 → 回退本地
    wi = db.create_work_item(
        project_id=body.project_id, owner_id=user.id, title=title, status=status, source=body.source,
        description=(body.description or "").strip(), due_date=(body.due_date or None),
        attachments=_clean_attachments(body.attachments),
    )
    return _view(wi, user)


@router.patch("/work-items/{item_id}")
def update_item(item_id: str, body: UpdateWorkItemBody, authorization: str = Header(default="")) -> dict:
    if body.status is not None and body.status not in STATUSES:
        raise HTTPException(400, "bad status")
    user = current_user()
    # Items belong to the project, not the creator: any writer-member may edit any
    # item in a shared project (M7 C2), so gate by project role, not item owner.
    existing = db.get_work_item(item_id)
    if not existing:
        raise HTTPException(404, "work item not found")
    _require_project_write(existing.project_id, user.id)
    tok = _hub_token(existing.project_id, authorization)
    if tok:
        fs = body.model_fields_set
        patch = {k: getattr(body, k) for k in ("title", "status", "description") if k in fs and getattr(body, k) is not None}
        if patch:
            up = hub_client.update_work_item(tok, existing.project_id, item_id, patch)
            if up:
                items = hub_client.list_work_items(tok, existing.project_id)
                if items is not None:
                    db.mirror_hub_work_items(existing.project_id, items)
                return _hub_view(up)
        # Hub 不可达 → 回退本地
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
def delete_item(item_id: str, authorization: str = Header(default="")) -> dict:
    existing = db.get_work_item(item_id)
    if not existing:
        raise HTTPException(404, "work item not found")
    _require_project_write(existing.project_id, current_user().id)
    tok = _hub_token(existing.project_id, authorization)
    if tok:
        if hub_client.delete_work_item(tok, existing.project_id, item_id):
            items = hub_client.list_work_items(tok, existing.project_id)
            if items is not None:
                db.mirror_hub_work_items(existing.project_id, items)
            return {"ok": True}
        # Hub 不可达 → 回退本地
    db.delete_work_item(item_id)
    return {"ok": True}
