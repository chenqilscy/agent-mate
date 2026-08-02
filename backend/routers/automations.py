"""Automations — scheduled / triggered agent runs (M6+ capability build).

A saved automation is a prompt + a trigger (interval, daily or Webhook). The scheduler
(agent/scheduler.py) fires it on time through the real agent; this router is the
CRUD + run-now surface. Owner-scoped like every other resource (WB-013).
"""
from __future__ import annotations

import time
import hashlib
import hmac
import json
import re

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from agent import scheduler
from project_health_service import ProjectHealthNotFound
from agent.sandbox import project_root
from auth.deps import current_user
from storage import db

router = APIRouter(prefix="/api", tags=["automations"])

TRIGGER_KINDS = {"interval", "daily", "health_daily", "webhook"}
WEBHOOK_MAX_BODY = 64 * 1024
WEBHOOK_CLOCK_SKEW_SEC = 300
_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")


class CreateAutomationBody(BaseModel):
    name: str
    prompt: str
    trigger_kind: str = "interval"
    interval_min: int = 60
    at_time: str = "09:00"
    project_id: str | None = None
    model: str | None = None
    enabled: bool = True
    timeout_sec: int = 300
    max_attempts: int = 3
    retry_backoff_sec: int = 30
    max_total_tokens: int = 0
    notify_policy: str = "failure,recovery"
    concurrency_policy: str = "skip"


class UpdateAutomationBody(BaseModel):
    name: str | None = None
    prompt: str | None = None
    trigger_kind: str | None = None
    interval_min: int | None = None
    at_time: str | None = None
    project_id: str | None = None
    model: str | None = None
    enabled: bool | None = None
    timeout_sec: int | None = None
    max_attempts: int | None = None
    retry_backoff_sec: int | None = None
    max_total_tokens: int | None = None
    notify_policy: str | None = None
    concurrency_policy: str | None = None


class RunAutomationBody(BaseModel):
    idempotency_key: str | None = None


class ReplayAutomationFireBody(BaseModel):
    idempotency_key: str | None = None


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
    d["next_run_label"] = (
        "等待 Webhook" if a.enabled and a.trigger_kind == "webhook"
        else _in(a.next_run_at) if a.enabled else "已停用"
    )
    d["last_run_label"] = _ago(a.last_run_at) if a.last_run_at else "尚未运行"
    return d


def _fire_view(fire) -> dict:
    data = fire.to_dict()
    data.pop("input_payload", None)
    return data


def _validate(kind: str, interval_min: int, at_time: str) -> None:
    if kind not in TRIGGER_KINDS:
        raise HTTPException(400, "trigger_kind must be 'interval', 'daily', 'health_daily' or 'webhook'")
    if kind == "interval" and interval_min < 1:
        raise HTTPException(400, "interval_min must be >= 1")
    if kind in {"daily", "health_daily"}:
        try:
            hh, mm = (int(x) for x in at_time.split(":", 1))
            assert 0 <= hh < 24 and 0 <= mm < 60
        except (ValueError, AssertionError):
            raise HTTPException(400, "at_time must be HH:MM")


def _validate_governance(data: dict) -> None:
    for key, lo, hi in (
        ("timeout_sec", 1, 3600), ("max_attempts", 1, 10),
        ("retry_backoff_sec", 1, 86400), ("max_total_tokens", 0, 10_000_000),
    ):
        value = data.get(key)
        if value is not None and not lo <= int(value) <= hi:
            raise HTTPException(400, f"{key} must be between {lo} and {hi}")
    if data.get("concurrency_policy") not in {None, "skip"}:
        raise HTTPException(400, "concurrency_policy must be 'skip'")
    if data.get("notify_policy") is not None:
        values = {x.strip() for x in str(data["notify_policy"]).split(",") if x.strip()}
        if not values <= {"failure", "recovery", "success"}:
            raise HTTPException(400, "notify_policy contains an unsupported event")


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
    _validate_governance(body.model_dump())
    if body.trigger_kind == "health_daily" and not body.project_id:
        raise HTTPException(400, "health_daily requires project_id")
    if body.project_id and db.project_access_role(body.project_id, user.id) is None:
        raise HTTPException(404, "project not found")
    a = db.create_automation(
        owner_id=user.id, name=name, prompt=prompt, trigger_kind=body.trigger_kind,
        interval_min=body.interval_min, at_time=body.at_time,
        project_id=body.project_id, model=body.model, enabled=body.enabled,
        timeout_sec=body.timeout_sec, max_attempts=body.max_attempts,
        retry_backoff_sec=body.retry_backoff_sec, max_total_tokens=body.max_total_tokens,
        notify_policy=body.notify_policy, concurrency_policy=body.concurrency_policy,
    )
    return _view(a)


@router.patch("/automations/{auto_id}")
def update_automation(auto_id: str, body: UpdateAutomationBody) -> dict:
    user = current_user()
    cur = db.get_automation(auto_id, user.id)
    if cur is None:
        raise HTTPException(404, "automation not found")
    if body.trigger_kind is not None or body.interval_min is not None or body.at_time is not None:
        _validate(
            body.trigger_kind or cur.trigger_kind,
            body.interval_min if body.interval_min is not None else cur.interval_min,
            body.at_time or cur.at_time,
        )
    # Send only fields the client actually set (exclude_unset) so an explicit null
    # clears a nullable column (project_id / model) while an omitted field stays put
    # (WB-037/038). Setting a workspace must resolve to a project this user can access;
    # clearing (null) skips the ownership check.
    data = body.model_dump(exclude_unset=True)
    _validate_governance(data)
    merged_kind = data.get("trigger_kind", cur.trigger_kind)
    merged_project = data.get("project_id", cur.project_id)
    if merged_kind == "health_daily" and not merged_project:
        raise HTTPException(400, "health_daily requires project_id")
    if data.get("project_id") is not None and db.project_access_role(data["project_id"], user.id) is None:
        raise HTTPException(404, "project not found")
    a = db.update_automation(auto_id, **data)
    return _view(a)


@router.delete("/automations/{auto_id}")
def delete_automation(auto_id: str) -> dict:
    user = current_user()
    if db.get_automation(auto_id, user.id) is None:
        raise HTTPException(404, "automation not found")
    db.delete_automation(auto_id)
    return {"ok": True}


@router.post("/automations/{auto_id}/run")
async def run_automation(auto_id: str, body: RunAutomationBody | None = None) -> dict:
    user = current_user()
    if db.get_automation(auto_id, user.id) is None:
        raise HTTPException(404, "automation not found")
    try:
        fire = await scheduler.run_now(auto_id, body.idempotency_key if body else None)
    except ProjectHealthNotFound:
        raise HTTPException(409, "automation project is no longer accessible") from None
    return {
        "ok": fire is not None,
        "session_id": fire.session_id if fire else None,
        "fire_id": fire.id if fire else None,
        "status": fire.status if fire else None,
    }


def _webhook_management_view(config: dict | None, automation_id: str) -> dict:
    if config is None:
        return {
            "configured": False, "automation_id": automation_id,
            "webhook_id": None, "endpoint": None, "created_at": None,
            "rotated_at": None, "deliveries": [],
        }
    return {
        "configured": True, "automation_id": automation_id,
        "webhook_id": config["id"],
        "endpoint": f"/api/webhooks/automations/{config['id']}",
        "created_at": config["created_at"], "rotated_at": config["rotated_at"],
        "deliveries": db.list_automation_webhook_deliveries(
            automation_id, config["owner_id"], limit=20
        ),
    }


def _owned_webhook_automation(auto_id: str):
    user = current_user()
    auto = db.get_automation(auto_id, user.id)
    if auto is None:
        raise HTTPException(404, "automation not found")
    if auto.trigger_kind != "webhook":
        raise HTTPException(409, "automation trigger_kind must be 'webhook'")
    return user, auto


@router.get("/automations/{auto_id}/webhook")
def get_automation_webhook(auto_id: str) -> dict:
    user, auto = _owned_webhook_automation(auto_id)
    config = db.get_automation_webhook(auto.id, user.id)
    return _webhook_management_view(config, auto.id)


@router.post("/automations/{auto_id}/webhook")
def create_automation_webhook(auto_id: str) -> dict:
    user, auto = _owned_webhook_automation(auto_id)
    if db.get_automation_webhook(auto.id, user.id) is not None:
        raise HTTPException(409, "webhook already configured; rotate it instead")
    config = db.create_automation_webhook(auto.id, user.id)
    return {**_webhook_management_view(config, auto.id), "secret": config["secret"]}


@router.post("/automations/{auto_id}/webhook/rotate")
def rotate_automation_webhook(auto_id: str) -> dict:
    user, auto = _owned_webhook_automation(auto_id)
    config = db.rotate_automation_webhook(auto.id, user.id)
    if config is None:
        raise HTTPException(404, "webhook not configured")
    return {**_webhook_management_view(config, auto.id), "secret": config["secret"]}


@router.delete("/automations/{auto_id}/webhook")
def delete_automation_webhook(auto_id: str) -> dict:
    user, auto = _owned_webhook_automation(auto_id)
    if not db.delete_automation_webhook(auto.id, user.id):
        raise HTTPException(404, "webhook not configured")
    return {"ok": True}


@router.post("/webhooks/automations/{webhook_id}", status_code=202)
async def receive_automation_webhook(webhook_id: str, request: Request) -> dict:
    """Service-to-service ingress authenticated by a signed raw request body."""
    config = db.get_automation_webhook_by_id(webhook_id, include_secret=True)
    timestamp_raw = request.headers.get("x-agentmate-timestamp", "")
    signature = request.headers.get("x-agentmate-signature", "")
    idempotency_key = request.headers.get("x-agentmate-idempotency-key", "").strip()
    if config is None:
        raise HTTPException(401, "invalid webhook signature")
    try:
        timestamp = int(timestamp_raw)
    except ValueError:
        raise HTTPException(401, "invalid webhook signature")
    if abs(time.time() - timestamp) > WEBHOOK_CLOCK_SKEW_SEC:
        raise HTTPException(401, "invalid webhook signature")
    if not _IDEMPOTENCY_RE.fullmatch(idempotency_key):
        raise HTTPException(400, "invalid X-AgentMate-Idempotency-Key")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > WEBHOOK_MAX_BODY:
        raise HTTPException(413, "webhook body exceeds 64 KiB")
    raw = await request.body()
    if len(raw) > WEBHOOK_MAX_BODY:
        raise HTTPException(413, "webhook body exceeds 64 KiB")
    expected = hmac.new(
        config["secret"].encode("utf-8"), timestamp_raw.encode("ascii") + b"." + raw,
        hashlib.sha256,
    ).hexdigest()
    supplied = signature[3:] if signature.startswith("v1=") else ""
    if len(supplied) != 64 or not hmac.compare_digest(expected, supplied):
        raise HTTPException(401, "invalid webhook signature")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(400, "webhook body must be UTF-8 JSON")
    if not isinstance(payload, dict):
        raise HTTPException(400, "webhook body must be a JSON object")
    auto = db.get_automation(config["automation_id"], config["owner_id"])
    if auto is None or auto.trigger_kind != "webhook" or not auto.enabled:
        raise HTTPException(409, "webhook automation is unavailable")

    body_digest = hashlib.sha256(raw).hexdigest()
    delivery, created, conflict = db.register_automation_webhook_delivery(
        webhook_id=config["id"], automation_id=auto.id, owner_id=auto.owner_id,
        idempotency_key=idempotency_key, payload_sha256=body_digest,
    )
    if conflict:
        raise HTTPException(409, "idempotency key was already used with different content")
    if delivery["fire_id"]:
        fire = db.get_automation_fire(delivery["fire_id"], auto.owner_id)
        if fire is not None:
            return {
                "ok": True, "duplicate": True, "delivery_id": delivery["id"],
                "fire_id": fire.id, "session_id": fire.session_id, "status": fire.status,
            }
    fire, fire_created = await scheduler.run_webhook(
        auto.id, config["id"], idempotency_key, payload
    )
    if fire is None:
        db.update_automation_webhook_delivery(
            delivery["id"], status="received", error_code="automation_busy"
        )
        raise HTTPException(409, "automation is busy; retry this delivery later")
    db.update_automation_webhook_delivery(
        delivery["id"], status="accepted", fire_id=fire.id, error_code=None
    )
    return {
        "ok": True, "duplicate": not created or not fire_created,
        "delivery_id": delivery["id"], "fire_id": fire.id,
        "session_id": fire.session_id, "status": fire.status,
    }


@router.get("/automation-fires")
def list_automation_fires(
    status: str | None = Query(default=None), automation_id: str | None = Query(default=None),
) -> dict:
    user = current_user()
    statuses = {item.strip() for item in status.split(",")} if status else None
    return {
        "fires": [
            _fire_view(fire) for fire in db.list_automation_fires(
                user.id, statuses=statuses, automation_id=automation_id
            )
        ]
    }


@router.post("/automation-fires/{fire_id}/replay")
async def replay_automation_fire(
    fire_id: str, body: ReplayAutomationFireBody | None = None,
) -> dict:
    user = current_user()
    if db.get_automation_fire(fire_id, user.id) is None:
        raise HTTPException(404, "automation fire not found")
    fire = await scheduler.replay_fire(
        fire_id, user.id, body.idempotency_key if body else None
    )
    if fire is None:
        raise HTTPException(409, "only dead-letter or ignored fires can be replayed")
    return {"ok": True, "fire": _fire_view(fire)}


@router.post("/automation-fires/{fire_id}/ignore")
def ignore_automation_fire(fire_id: str) -> dict:
    user = current_user()
    try:
        fire = db.ignore_automation_fire(fire_id, user.id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if fire is None:
        raise HTTPException(404, "automation fire not found")
    return {"ok": True, "fire": _fire_view(fire)}


def _run_view(s) -> dict:
    """A run (automation session) as the UI wants it: the session dict + a relative
    label + the workspace path it ran in (WB-043 detail modal)."""
    d = s.to_dict()
    d["ago"] = _ago(s.created_at)  # when this run fired
    d["workspace"] = str(project_root(s.project_id))
    return d


@router.get("/automations/{auto_id}/runs")
def list_automation_runs(auto_id: str) -> dict:
    """Every session this automation produced, newest first — the run-history that
    the sidebar deliberately hides (WB-035). Owner-scoped like the rest."""
    user = current_user()
    if db.get_automation(auto_id, user.id) is None:
        raise HTTPException(404, "automation not found")
    return {"runs": [_run_view(s) for s in db.list_automation_runs(auto_id, user.id)]}


@router.get("/automation-runs")
def list_all_automation_runs() -> dict:
    """Cross-automation run feed for the 运行记录 tab (WB-043) — every automation run
    this owner produced, newest first, owner-scoped and capped."""
    user = current_user()
    return {"runs": [_run_view(s) for s in db.list_all_automation_runs(user.id)]}
