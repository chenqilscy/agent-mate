"""Hub 消息中心（WB-065）：读通知 + 标记已读。@提及等事件落这里，客户端轮询。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

import db
from auth import CurrentAccount
from models import Account

router = APIRouter(prefix="/api", tags=["notifications"])


@router.get("/notifications")
def list_notifs(account: Account = CurrentAccount) -> dict:
    return {
        "notifications": db.list_notifications(account.id),
        "unread": db.unread_notification_count(account.id),
    }


class MarkReadBody(BaseModel):
    ids: list[str] | None = None


@router.post("/notifications/read")
def mark_read(body: MarkReadBody, account: Account = CurrentAccount) -> dict:
    db.mark_notifications_read(account.id, body.ids)
    return {"ok": True}
