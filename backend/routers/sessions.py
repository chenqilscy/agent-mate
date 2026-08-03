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


def _pending_question_view(run) -> dict | None:
    if not run or run.status not in {"waiting_approval", "paused"}:
        return None
    checkpoint = run.checkpoint if isinstance(run.checkpoint, dict) else {}
    if checkpoint.get("kind") != "ask_user" or not isinstance(checkpoint.get("questions"), list):
        return None
    questions = []
    for raw in checkpoint["questions"][:3]:
        if not isinstance(raw, dict):
            continue
        question = str(raw.get("q") or "").strip()[:500]
        if not question:
            continue
        options = raw.get("options") if isinstance(raw.get("options"), list) else []
        questions.append({
            "q": question,
            "options": [str(option)[:160] for option in options[:8]],
        })
    if not questions:
        return None
    return {
        "questions": questions,
        "recovery": "retry_required",
        "source": str(checkpoint.get("source") or "agent"),
    }


@router.get("/sessions")
def list_sessions(space: str | None = None) -> dict:
    user = current_user()
    sessions = db.list_sessions(user.id, space=space)
    return {"sessions": [_session_view(s) for s in sessions]}


@router.post("/sessions")
def create_session(body: CreateSessionBody) -> dict:
    user = current_user()
    # If the session targets a project, the caller must have access to it — else the
    # session becomes a back-door handle to read/write that project's workspace via
    # ?session= on the files endpoints (WB-153; mirrors chat.py + files._select_root).
    if body.project_id and db.project_access_role(body.project_id, user.id) is None:
        raise HTTPException(404, "project not found")
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
    # M7 C3: a project member may READ a teammate's execution session (owner still
    # 404s a stranger's personal session — get_session_for enforces that). Read-only:
    # driving it (chat/rename/delete) stays owner-scoped, so read_only tells the UI.
    me = current_user()
    s = db.get_session_for(session_id, me.id)
    if not s:
        raise HTTPException(404, "session not found")
    view = _session_view(s)
    owner = db.get_user(s.owner_id)
    view["owner_name"] = owner.name if owner else s.owner_id
    view["read_only"] = s.owner_id != me.id
    messages = []
    for message in db.list_messages(session_id):
        item = message.to_dict()
        run = db.get_run(message.run_id) if message.run_id else None
        item["run_status"] = run.status if run else None
        item["pending_question"] = _pending_question_view(run)
        messages.append(item)
    return {
        "session": view,
        "messages": messages,
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
