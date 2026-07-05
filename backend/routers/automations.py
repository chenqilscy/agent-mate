"""Automations — scheduled / triggered agent runs (M6+ capability build).

A saved automation is a prompt + a trigger (interval or daily). The scheduler
(agent/scheduler.py) fires it on time through the real agent; this router is the
CRUD + run-now surface. Owner-scoped like every other resource (WB-013).
"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent import scheduler
from auth.deps import current_user
from storage import db

router = APIRouter(prefix="/api", tags=["automations"])

TRIGGER_KINDS = {"interval", "daily"}


class CreateAutomationBody(BaseModel):
    name: str
    prompt: str
    trigger_kind: str = "interval"
    interval_min: int = 60
    at_time: str = "09:00"
    project_id: str | None = None
    model: str | None = None
    enabled: bool = True


class UpdateAutomationBody(BaseModel):
    name: str | None = None
    prompt: str | None = None
    trigger_kind: str | None = None
    interval_min: int | None = None
    at_time: str | None = None
    project_id: str | None = None
    model: str | None = None
    enabled: bool | None = None


def _ago(ts: float) -> str:
    diff = max(0, time.time() - ts)
    if diff < 60:
        return "刚刚"
    if diff < 3600:
        return f"{int(diff // 60)}分钟前"
    if diff < 86400:
        return f"{int(diff // 3600)}小时前"
    return f"{int(diff // 86400)}天前"


def _in(ts: float) -> str:
    diff = ts - time.time()
    if diff <= 0:
        return "即将"
    if diff < 3600:
        return f"{int(diff // 60) + 1}分钟后"
    if diff < 86400:
        return f"{int(diff // 3600)}小时后"
    return f"{int(diff // 86400)}天后"


def _view(a) -> dict:
    d = a.to_dict()
    d["next_run_label"] = _in(a.next_run_at) if a.enabled else "已停用"
    d["last_run_label"] = _ago(a.last_run_at) if a.last_run_at else "尚未运行"
    return d


def _validate(kind: str, interval_min: int, at_time: str) -> None:
    if kind not in TRIGGER_KINDS:
        raise HTTPException(400, "trigger_kind must be 'interval' or 'daily'")
    if kind == "interval" and interval_min < 1:
        raise HTTPException(400, "interval_min must be >= 1")
    if kind == "daily":
        try:
            hh, mm = (int(x) for x in at_time.split(":", 1))
            assert 0 <= hh < 24 and 0 <= mm < 60
        except (ValueError, AssertionError):
            raise HTTPException(400, "at_time must be HH:MM")


@router.get("/automations")
def list_automations() -> dict:
    user = current_user()
    return {"automations": [_view(a) for a in db.list_automations(user.id)]}


@router.post("/automations")
def create_automation(body: CreateAutomationBody) -> dict:
    user = current_user()
    name = (body.name or "").strip()
    prompt = (body.prompt or "").strip()
    if not name or not prompt:
        raise HTTPException(400, "name and prompt are required")
    _validate(body.trigger_kind, body.interval_min, body.at_time)
    if body.project_id and db.get_project(body.project_id, user.id) is None:
        raise HTTPException(404, "project not found")
    a = db.create_automation(
        owner_id=user.id, name=name, prompt=prompt, trigger_kind=body.trigger_kind,
        interval_min=body.interval_min, at_time=body.at_time,
        project_id=body.project_id, model=body.model, enabled=body.enabled,
    )
    return _view(a)


@router.patch("/automations/{auto_id}")
def update_automation(auto_id: str, body: UpdateAutomationBody) -> dict:
    user = current_user()
    if db.get_automation(auto_id, user.id) is None:
        raise HTTPException(404, "automation not found")
    if body.trigger_kind is not None or body.interval_min is not None or body.at_time is not None:
        cur = db.get_automation(auto_id, user.id)
        _validate(
            body.trigger_kind or cur.trigger_kind,
            body.interval_min if body.interval_min is not None else cur.interval_min,
            body.at_time or cur.at_time,
        )
    # Switching the bound workspace must resolve to a project this user owns (like
    # create). exclude_none below means clearing (project_id=None) is a no-op here —
    # phase one supports set/switch, not unbind (WB-036).
    if body.project_id is not None and db.get_project(body.project_id, user.id) is None:
        raise HTTPException(404, "project not found")
    a = db.update_automation(auto_id, **body.model_dump(exclude_none=True))
    return _view(a)


@router.delete("/automations/{auto_id}")
def delete_automation(auto_id: str) -> dict:
    user = current_user()
    if db.get_automation(auto_id, user.id) is None:
        raise HTTPException(404, "automation not found")
    db.delete_automation(auto_id)
    return {"ok": True}


@router.post("/automations/{auto_id}/run")
async def run_automation(auto_id: str) -> dict:
    user = current_user()
    if db.get_automation(auto_id, user.id) is None:
        raise HTTPException(404, "automation not found")
    session_id = await scheduler.run_now(auto_id)
    return {"ok": session_id is not None, "session_id": session_id}


@router.get("/automations/{auto_id}/runs")
def list_automation_runs(auto_id: str) -> dict:
    """Every session this automation produced, newest first — the run-history that
    the sidebar deliberately hides (WB-035). Owner-scoped like the rest."""
    user = current_user()
    if db.get_automation(auto_id, user.id) is None:
        raise HTTPException(404, "automation not found")
    runs = []
    for s in db.list_automation_runs(auto_id, user.id):
        d = s.to_dict()
        d["ago"] = _ago(s.created_at)  # when this run fired
        runs.append(d)
    return {"runs": runs}
