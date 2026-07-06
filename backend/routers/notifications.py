"""Message center — real in-app notifications (M7 C4).

Rows are written by collaboration actions (a member added, role changed, removed)
and delivered to the recipient here. No polling magic on the backend: the client
lists and marks-read.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from auth.deps import current_user
from storage import db

router = APIRouter(prefix="/api", tags=["notifications"])


class ReadBody(BaseModel):
    ids: list[str] | None = None  # None → mark all read


@router.get("/notifications")
def list_notifications() -> dict:
    uid = current_user().id
    return {
        "notifications": db.list_notifications(uid),
        "unread": db.unread_notification_count(uid),
    }


@router.post("/notifications/read")
def mark_read(body: ReadBody) -> dict:
    uid = current_user().id
    db.mark_notifications_read(uid, body.ids)
    return {"ok": True, "unread": db.unread_notification_count(uid)}
