"""Public external-event relay and service-account management (WB-361)."""
from __future__ import annotations

import hashlib
import hmac
import json
import time

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

import relay_store
from auth import CurrentAccount, bearer_token
from models import Account

router = APIRouter(prefix="/api", tags=["relay"])
MAX_BODY = 64 * 1024
CLOCK_SKEW_SECONDS = 300


class ServiceAccountBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scopes: list[str] = Field(default=["relay:write", "relay:read"], min_length=1, max_length=4)


@router.get("/integrations/service-accounts")
def list_service_accounts(account: Account = CurrentAccount) -> dict:
    return {"service_accounts": relay_store.list_service_accounts(account.id)}


@router.post("/integrations/service-accounts")
def create_service_account(body: ServiceAccountBody, account: Account = CurrentAccount) -> dict:
    try:
        service, token = relay_store.create_service_account(account.id, body.name.strip(), body.scopes)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"service_account": service, "token": token}


@router.post("/integrations/service-accounts/{service_id}/rotate")
def rotate_service_account(service_id: str, account: Account = CurrentAccount) -> dict:
    result = relay_store.rotate_service_account(service_id, account.id)
    if result is None:
        raise HTTPException(404, "service account not found")
    service, token = result
    return {"service_account": service, "token": token}


@router.delete("/integrations/service-accounts/{service_id}")
def revoke_service_account(service_id: str, account: Account = CurrentAccount) -> dict:
    if not relay_store.revoke_service_account(service_id, account.id):
        raise HTTPException(404, "service account not found")
    return {"ok": True}


def _service_token(authorization: str, required_scope: str) -> tuple[str, dict]:
    token = bearer_token(authorization)
    service = relay_store.resolve_service_token(token, required_scope)
    if service is None:
        raise HTTPException(401, "invalid service credentials")
    return token, service


def _verify_signature(token: str, timestamp_raw: str, signature: str, raw: bytes) -> None:
    try:
        timestamp = int(timestamp_raw)
    except ValueError as exc:
        raise HTTPException(401, "invalid service signature") from exc
    if abs(time.time() - timestamp) > CLOCK_SKEW_SECONDS:
        raise HTTPException(401, "invalid service signature")
    expected = hmac.new(
        token.encode("utf-8"), timestamp_raw.encode("ascii") + b"." + raw, hashlib.sha256,
    ).hexdigest()
    supplied = signature[3:] if signature.startswith("v1=") else ""
    if len(supplied) != 64 or not hmac.compare_digest(expected, supplied):
        raise HTTPException(401, "invalid service signature")


@router.post("/relay/events", status_code=202)
async def receive_event(
    request: Request,
    authorization: str = Header(default=""),
    x_agentmate_timestamp: str = Header(default=""),
    x_agentmate_signature: str = Header(default=""),
) -> dict:
    token, service = _service_token(authorization, "relay:write")
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY:
        raise HTTPException(413, "relay body exceeds 64 KiB")
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise HTTPException(413, "relay body exceeds 64 KiB")
    _verify_signature(token, x_agentmate_timestamp, x_agentmate_signature, raw)
    if not relay_store.consume_rate_limit(service["id"]):
        raise HTTPException(429, "service rate limit exceeded")
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "relay body must be UTF-8 JSON") from exc
    if not isinstance(body, dict) or not isinstance(body.get("payload"), dict):
        raise HTTPException(400, "payload must be a JSON object")
    event_key = str(body.get("event_key") or "").strip()
    device_id = str(body.get("device_id") or "").strip()
    automation_id = str(body.get("automation_id") or "").strip()
    if not automation_id or len(automation_id) > 120:
        raise HTTPException(400, "invalid automation_id")
    try:
        event, created, conflict = relay_store.create_event(
            service, event_key=event_key, device_id=device_id, automation_id=automation_id,
            payload=body["payload"], payload_sha256=hashlib.sha256(raw).hexdigest(),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    if conflict:
        raise HTTPException(409, "event_key already used with different target or content")
    return {"event": event, "duplicate": not created}


@router.get("/relay/events/{event_id}")
def get_event(
    event_id: str, authorization: str = Header(default=""),
) -> dict:
    _, service = _service_token(authorization, "relay:read")
    event = relay_store.event_view(event_id, service["id"])
    if event is None:
        raise HTTPException(404, "relay event not found")
    return {"event": event}


class PullBody(BaseModel):
    device_id: str = Field(min_length=8, max_length=120)
    device_name: str = Field(default="", max_length=80)
    limit: int = Field(default=10, ge=1, le=25)


@router.post("/relay/pull")
def pull_events(body: PullBody, account: Account = CurrentAccount) -> dict:
    try:
        relay_store.register_device(account.id, body.device_id, body.device_name)
        events = relay_store.lease_events(account.id, body.device_id, body.limit)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"events": events}


@router.get("/relay/devices")
def list_devices(account: Account = CurrentAccount) -> dict:
    return {"devices": relay_store.list_devices(account.id)}


class AckBody(BaseModel):
    device_id: str = Field(min_length=8, max_length=120)
    lease_token: str = Field(min_length=16, max_length=200)
    status: str = Field(pattern="^(succeeded|failed)$")
    error_code: str = Field(default="", max_length=80)
    error_message: str = Field(default="", max_length=500)


@router.post("/relay/events/{event_id}/ack")
def acknowledge_event(event_id: str, body: AckBody, account: Account = CurrentAccount) -> dict:
    event = relay_store.acknowledge(
        event_id, account.id, body.device_id, body.lease_token,
        status=body.status, error_code=body.error_code, error_message=body.error_message,
    )
    if event is None:
        raise HTTPException(409, "relay lease is invalid or expired")
    return {"event": event}
