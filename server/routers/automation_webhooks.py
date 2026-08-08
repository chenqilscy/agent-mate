"""Server-owned signed webhook ingress for Server automation definitions."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time

from fastapi import APIRouter, HTTPException, Request

import automation_scheduler
import automation_webhook_store as store
import business_store
import db
from auth import CurrentAccount
from models import Account


router = APIRouter(prefix="/api", tags=["automation-webhooks"])
WEBHOOK_MAX_BODY = 64 * 1024
WEBHOOK_CLOCK_SKEW_SEC = 300
_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$")


def _automation(automation_id: str, account: Account) -> dict:
    automation = business_store.get_record("business_automations", automation_id)
    if automation is None or str(automation.get("owner_id")) != account.id:
        raise HTTPException(404, "automation not found")
    if str(automation.get("trigger_kind")) != "webhook":
        raise HTTPException(409, "automation trigger_kind must be 'webhook'")
    return automation


def _management_view(config: dict | None, automation_id: str) -> dict:
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
        "deliveries": store.list_deliveries(automation_id, str(config["owner_id"])),
    }


@router.get("/automations/{automation_id}/webhook")
def get_webhook(automation_id: str, account: Account = CurrentAccount) -> dict:
    automation = _automation(automation_id, account)
    return _management_view(store.get(automation["id"], account.id), automation["id"])


@router.post("/automations/{automation_id}/webhook")
def create_webhook(automation_id: str, account: Account = CurrentAccount) -> dict:
    automation = _automation(automation_id, account)
    if store.get(automation["id"], account.id) is not None:
        raise HTTPException(409, "webhook already configured; rotate it instead")
    config = store.create(automation["id"], account.id)
    return {**_management_view(config, automation["id"]), "secret": config["secret"]}


@router.post("/automations/{automation_id}/webhook/rotate")
def rotate_webhook(automation_id: str, account: Account = CurrentAccount) -> dict:
    automation = _automation(automation_id, account)
    config = store.rotate(automation["id"], account.id)
    if config is None:
        raise HTTPException(404, "webhook not configured")
    return {**_management_view(config, automation["id"]), "secret": config["secret"]}


@router.delete("/automations/{automation_id}/webhook")
def delete_webhook(automation_id: str, account: Account = CurrentAccount) -> dict:
    automation = _automation(automation_id, account)
    if not store.delete(automation["id"], account.id):
        raise HTTPException(404, "webhook not configured")
    return {"ok": True}


@router.post("/webhooks/automations/{webhook_id}", status_code=202)
async def receive_webhook(webhook_id: str, request: Request) -> dict:
    """Validate one signed delivery and enqueue its Server Run."""
    timestamp_raw = request.headers.get("x-agentmate-timestamp", "")
    signature = request.headers.get("x-agentmate-signature", "")
    idempotency_key = request.headers.get("x-agentmate-idempotency-key", "").strip()
    try:
        timestamp = int(timestamp_raw)
    except ValueError:
        raise HTTPException(401, "invalid webhook signature") from None
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

    try:
        config = store.get_by_id(webhook_id, include_secret=True)
    except Exception as exc:  # noqa: BLE001 - fail closed without leaking key state
        raise HTTPException(503, "webhook verifier unavailable") from exc
    if config is None:
        raise HTTPException(401, "invalid webhook signature")
    expected = hmac.new(
        str(config["secret"]).encode("utf-8"), timestamp_raw.encode("ascii") + b"." + raw,
        hashlib.sha256,
    ).hexdigest()
    supplied = signature[3:] if signature.startswith("v1=") else ""
    if len(supplied) != 64 or not hmac.compare_digest(expected, supplied):
        raise HTTPException(401, "invalid webhook signature")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(400, "webhook body must be UTF-8 JSON") from None
    if not isinstance(payload, dict):
        raise HTTPException(400, "webhook body must be a JSON object")

    automation = business_store.get_record("business_automations", str(config["automation_id"]))
    if (
        automation is None
        or str(automation.get("owner_id")) != str(config["owner_id"])
        or str(automation.get("trigger_kind")) != "webhook"
        or not bool(automation.get("enabled"))
    ):
        raise HTTPException(409, "webhook automation is unavailable")
    digest = hashlib.sha256(raw).hexdigest()
    delivery, created, conflict = store.register_delivery(
        webhook_id=webhook_id, automation_id=str(automation["id"]),
        owner_id=str(automation["owner_id"]), idempotency_key=idempotency_key,
        payload_sha256=digest,
    )
    if conflict:
        raise HTTPException(409, "idempotency key was already used with different content")
    if delivery.get("fire_id"):
        row = db.get_conn().execute(
            "SELECT * FROM business_automation_fires WHERE id=? AND owner_id=?",
            (delivery["fire_id"], automation["owner_id"]),
        ).fetchone()
        if row is not None:
            return {
                "ok": True, "duplicate": True, "delivery_id": delivery["id"],
                "fire_id": row["id"], "session_id": row["session_id"], "status": row["status"],
            }

    fire_key = "webhook:" + hashlib.sha256(
        f"{webhook_id}:{idempotency_key}".encode("utf-8"),
    ).hexdigest()
    result = automation_scheduler.enqueue_automation(
        automation, fire_key=fire_key, planned_at=time.time(), input_payload=payload,
    )
    if result.get("skipped"):
        store.update_delivery(delivery["id"], status="received", error_code="automation_busy")
        raise HTTPException(409, "automation is busy; retry this delivery later")
    fire = result["fire"]
    store.update_delivery(delivery["id"], status="accepted", fire_id=fire["id"])
    return {
        "ok": True, "duplicate": not created or bool(result.get("duplicate")),
        "delivery_id": delivery["id"], "fire_id": fire["id"],
        "session_id": fire["session_id"], "status": fire["status"],
    }
