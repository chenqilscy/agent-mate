"""Milestones —— 项目里程碑 / 迭代（WB-108）。

与 work_items 一致的打通策略：server-origin 项目走 Server 权威 + 刷新本地镜像；
Server 不可达 / 本地项目 → 纯本地（离线优先）。Viewer 只读、Member+ 可写。
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

import server_client
from auth.deps import current_user
from storage import db
from storage.models import Role

router = APIRouter(prefix="/api", tags=["milestones"])

M_STATUSES = {"open", "closed"}


def _bearer(authorization: str) -> str:
    return authorization[7:].strip() if authorization[:7].lower() == "bearer " else ""


def _server_token(project_id: str, authorization: str) -> str:
    """server-origin 镜像项目 + 已接 Server + 带 token → 返回 bearer，否则 ""（走本地）。"""
    if not server_client.server_enabled():
        return ""
    tok = _bearer(authorization)
    if not tok:
        return ""
    proj = db.get_project(project_id)
    if not proj or getattr(proj, "origin", "local") != "server":
        return ""
    return tok


def _require_project_write(project_id: str, user_id: str) -> None:
    role = db.project_access_role(project_id, user_id)
    if role is None:
        raise HTTPException(404, "project not found")
    if role == Role.VIEWER:
        raise HTTPException(403, "只读成员不能修改里程碑")


class CreateMilestoneBody(BaseModel):
    project_id: str
    name: str
    description: str = ""
    due_date: str | None = None
    status: str = "open"


class UpdateMilestoneBody(BaseModel):
    name: str | None = None
    description: str | None = None
    due_date: str | None = None
    status: str | None = None
    sort: int | None = None


@router.get("/milestones")
def list_items(project: str, authorization: str = Header(default="")) -> dict:
    user = current_user()
    if not db.get_project_for(project, user.id):
        raise HTTPException(404, "project not found")
    tok = _server_token(project, authorization)
    if tok:
        items = server_client.list_milestones(tok, project)  # None = Server 不可达
        if items is not None:
            db.mirror_server_milestones(project, items)
            return {"milestones": items}
    return {"milestones": db.list_milestones(project)}


@router.post("/milestones")
def create_item(body: CreateMilestoneBody, authorization: str = Header(default="")) -> dict:
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(400, "empty name")
    status = body.status if body.status in M_STATUSES else "open"
    user = current_user()
    _require_project_write(body.project_id, user.id)
    tok = _server_token(body.project_id, authorization)
    if tok:
        created = server_client.create_milestone(
            tok, body.project_id,
            {"name": name, "description": body.description,
             "due_date": body.due_date or "", "status": status},
        )
        if created:
            items = server_client.list_milestones(tok, body.project_id)
            if items is not None:
                db.mirror_server_milestones(body.project_id, items)
            return created
        # server-origin + Server 不可达：别造会被下次镜像抹掉的本地里程碑，如实报错（WB-158）。
        raise HTTPException(503, "Server 暂不可达，里程碑未创建，请稍后重试")
    return db.create_milestone(
        project_id=body.project_id, name=name, description=body.description,
        due_date=(body.due_date or None), status=status,
    )


@router.patch("/milestones/{mid}")
def update_item(mid: str, body: UpdateMilestoneBody, authorization: str = Header(default="")) -> dict:
    if body.status is not None and body.status not in M_STATUSES:
        raise HTTPException(400, "bad status")
    user = current_user()
    existing = db.get_milestone(mid)
    if not existing:
        raise HTTPException(404, "milestone not found")
    _require_project_write(existing["project_id"], user.id)
    tok = _server_token(existing["project_id"], authorization)
    if tok:
        patch = body.model_dump(exclude_unset=True)
        if patch:
            up = server_client.update_milestone(tok, existing["project_id"], mid, patch)
            if up:
                items = server_client.list_milestones(tok, existing["project_id"])
                if items is not None:
                    db.mirror_server_milestones(existing["project_id"], items)
                return up
            # server-origin + Server 不可达：本地改动会被下次镜像还原，如实报错（WB-158）。
            raise HTTPException(503, "Server 暂不可达，改动未保存，请稍后重试")
    updated = db.update_milestone(mid, **body.model_dump(exclude_unset=True))
    if not updated:
        raise HTTPException(404, "milestone not found")
    return updated


@router.delete("/milestones/{mid}")
def delete_item(mid: str, authorization: str = Header(default="")) -> dict:
    user = current_user()
    existing = db.get_milestone(mid)
    if not existing:
        raise HTTPException(404, "milestone not found")
    _require_project_write(existing["project_id"], user.id)
    tok = _server_token(existing["project_id"], authorization)
    if tok:
        if server_client.delete_milestone(tok, existing["project_id"], mid):
            items = server_client.list_milestones(tok, existing["project_id"])
            if items is not None:
                db.mirror_server_milestones(existing["project_id"], items)
            return {"ok": True}
        # server-origin + Server 不可达：本地删除会被下次镜像还原，如实报错（WB-158）。
        raise HTTPException(503, "Server 暂不可达，未删除，请稍后重试")
    db.delete_milestone(mid)
    return {"ok": True}
