"""Sessions — sidebar tasks/spaces + history replay (spec 5.1)."""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth.deps import current_user
from storage import db

router = APIRouter(prefix="/api", tags=["sessions"])


class CreateSessionBody(BaseModel):
    title: str
    kind: str = "chat"
    space: str | None = None
    project_id: str | None = None


class RenameBody(BaseModel):
    title: str


def _ago(ts: float) -> str:
    """Relative time label ('刚刚' / '2小时前' / '3天前')."""
    diff = max(0, time.time() - ts)
    if diff < 60:
        return "刚刚"
    if diff < 3600:
        return f"{int(diff // 60)}分钟前"
    if diff < 86400:
        return f"{int(diff // 3600)}小时前"
    return f"{int(diff // 86400)}天前"


def _session_view(s) -> dict:
    d = s.to_dict()
    d["ago"] = _ago(s.updated_at)
    return d


@router.get("/sessions")
def list_sessions(space: str | None = None) -> dict:
    user = current_user()
    sessions = db.list_sessions(user.id, space=space)
    return {"sessions": [_session_view(s) for s in sessions]}


@router.post("/sessions")
def create_session(body: CreateSessionBody) -> dict:
    user = current_user()
    s = db.create_session(
        owner_id=user.id,
        title=body.title,
        kind=body.kind,
        space=body.space,
        project_id=body.project_id,
    )
    return _session_view(s)


@router.get("/sessions/{session_id}/messages")
def get_messages(session_id: str) -> dict:
    # owner-scoped so one user can't replay another's history (WB-013).
    s = db.get_session(session_id, owner_id=current_user().id)
    if not s:
        raise HTTPException(404, "session not found")
    return {
        "session": _session_view(s),
        "messages": [m.to_dict() for m in db.list_messages(session_id)],
    }


@router.patch("/sessions/{session_id}")
def rename_session(session_id: str, body: RenameBody) -> dict:
    if not db.get_session(session_id, owner_id=current_user().id):
        raise HTTPException(404, "session not found")
    db.rename_session(session_id, body.title)
    return {"ok": True}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str) -> dict:
    if not db.get_session(session_id, owner_id=current_user().id):
        raise HTTPException(404, "session not found")
    db.delete_session(session_id)
    return {"ok": True}
