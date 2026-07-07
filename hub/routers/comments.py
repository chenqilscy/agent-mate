"""项目评论 + @提及 + 在线状态（WB-065 v1，REST + 客户端轮询；实时推送作后续增强）。

全部 access-gated——非项目成员既不能评论/读评论，也看不到在线状态。@提及解析出被提及的**项目成员**，
给 TA 建一条 Hub 通知（复用 M7 C4 通知理念，落 Hub 供跨机可见）。
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db
from auth import CurrentAccount
from models import Account

router = APIRouter(prefix="/api", tags=["collab"])

# @提及：@ 后接非空白/非常见标点的一串（支持中文名）。
_MENTION = re.compile(r"@([^\s@,，。！!？?：:；;]+)")


class CommentBody(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


@router.post("/projects/{project_id}/comments")
def post_comment(project_id: str, body: CommentBody, account: Account = CurrentAccount) -> dict:
    if db.project_access_role(project_id, account.id) is None:
        raise HTTPException(404, "project not found")
    text = body.body.strip()
    c = db.add_comment(project_id=project_id, author_id=account.id, author_name=account.name, body=text)
    # @提及 → 给被提及的项目成员建通知（去重、不通知自己、仅限项目成员）。
    members = {m["name"]: m["account_id"] for m in db.list_project_members(project_id)}
    notified: set[str] = set()
    for name in _MENTION.findall(text):
        aid = members.get(name)
        if aid and aid != account.id and aid not in notified:
            db.add_notification(
                account_id=aid, kind="mention", title=f"{account.name} 在评论中提到了你",
                body=text[:200], project_id=project_id, actor_name=account.name,
            )
            notified.add(aid)
    return {**c, "mentioned": len(notified)}


@router.get("/projects/{project_id}/comments")
def get_comments(project_id: str, account: Account = CurrentAccount) -> dict:
    if db.project_access_role(project_id, account.id) is None:
        raise HTTPException(404, "project not found")
    return {"comments": db.list_comments(project_id)}


@router.get("/projects/{project_id}/presence")
def get_presence(project_id: str, account: Account = CurrentAccount) -> dict:
    if db.project_access_role(project_id, account.id) is None:
        raise HTTPException(404, "project not found")
    return {"presence": db.list_presence(project_id)}
