"""Message center — real in-app notifications (M7 C4).

Rows are written by collaboration actions (a member added, role changed, removed)
and delivered to the recipient here. No polling magic on the backend: the client
lists and marks-read.
"""
from __future__ import annotations

from fastapi import APIRouter, Header
from pydantic import BaseModel

from auth.deps import current_user
import server_client
from storage import db

router = APIRouter(prefix="/api", tags=["notifications"])


class ReadBody(BaseModel):
    ids: list[str] | None = None  # None → mark all read


def _bearer(authorization: str) -> str:
    return authorization[7:].strip() if authorization[:7].lower() == "bearer " else ""


@router.get("/notifications")
def list_notifications(authorization: str = Header(default="")) -> dict:
    uid = current_user().id
    local_items = db.list_notifications(uid)
    remote = server_client.server_notifications(_bearer(authorization)) if server_client.server_enabled() else None
    remote_items = remote.get("notifications", []) if isinstance(remote, dict) else []
    items = sorted(
        [*local_items, *remote_items],
        key=lambda item: float(item.get("created_at") or 0), reverse=True,
    )[:100]
    return {
        "notifications": items,
        "unread": db.unread_notification_count(uid) + (
            int(remote.get("unread") or 0) if isinstance(remote, dict) else 0
        ),
    }


@router.post("/notifications/read")
def mark_read(body: ReadBody, authorization: str = Header(default="")) -> dict:
    uid = current_user().id
    db.mark_notifications_read(uid, body.ids)
    token = _bearer(authorization)
    remote_ok = True
    if server_client.server_enabled() and token:
        remote_ok = server_client.mark_server_notifications(token, body.ids)
    remote = server_client.server_notifications(token) if server_client.server_enabled() and token else None
    return {
        "ok": remote_ok,
        "unread": db.unread_notification_count(uid) + (
            int(remote.get("unread") or 0) if isinstance(remote, dict) else 0
        ),
    }
