"""团队时间线（WB-062 Phase 3）：本地执行产出上行的接收端 + 队友读取端。

只存元数据 + 可选摘要（append-only，去重）；access-gated——非项目成员既不能上报也不能读。
绝不接收/存储凭据或工作区文件（本地侧保证不放进 payload，Hub 侧字段也只有 title/summary）。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import db
from auth import CurrentAccount
from models import Account

router = APIRouter(prefix="/api", tags=["timeline"])


class TimelineEventBody(BaseModel):
    kind: str = "session"
    title: str = ""
    summary: str = ""
    ext_id: str | None = None  # 本地会话 id，用于去重


@router.post("/projects/{project_id}/timeline")
def post_event(project_id: str, body: TimelineEventBody, account: Account = CurrentAccount) -> dict:
    if db.project_access_role(project_id, account.id) is None:
        raise HTTPException(404, "project not found")
    created = db.add_timeline_event(
        project_id=project_id, actor_id=account.id, actor_name=account.name,
        kind=body.kind, title=body.title, summary=body.summary, ext_id=body.ext_id,
    )
    return {"ok": True, "created": created}


@router.get("/projects/{project_id}/timeline")
def get_timeline(project_id: str, account: Account = CurrentAccount) -> dict:
    if db.project_access_role(project_id, account.id) is None:
        raise HTTPException(404, "project not found")
    return {"events": db.list_timeline(project_id)}
