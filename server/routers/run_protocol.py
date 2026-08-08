"""HTTP contract for device authentication and fenced Run transport (WB-433)."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

import business_store
import db
import run_protocol_store as store
from auth import CurrentAccount
from models import Account, can_write


router = APIRouter(prefix="/api", tags=["device-runs"])


def _protocol_error(exc: Exception) -> None:
    if isinstance(exc, store.SequenceGap):
        raise HTTPException(409, {"code": "event_sequence_gap", "expected_sequence": exc.expected_sequence}) from exc
    if isinstance(exc, store.ProtocolUnauthorized):
        raise HTTPException(401, str(exc)) from exc
    if isinstance(exc, store.ProtocolConflict):
        raise HTTPException(409, str(exc)) from exc
    if isinstance(exc, KeyError):
        raise HTTPException(404, "Run not found") from exc
    raise exc


def _device(authorization: str = Header(default="")) -> store.DevicePrincipal:
    try:
        return store.authenticate_device(authorization)
    except Exception as exc:
        _protocol_error(exc)
        raise


CurrentDevice = Depends(_device)


def _validate_public_metadata(value: dict[str, Any], *, max_bytes: int = 64 * 1024) -> None:
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "metadata must be JSON serializable") from exc
    if len(encoded) > max_bytes:
        raise HTTPException(413, "metadata exceeds size limit")


class DeviceRegister(BaseModel):
    device_id: str = Field(min_length=8, max_length=200, pattern=r"^[A-Za-z0-9._:-]+$")
    name: str = Field(min_length=1, max_length=120)
    public_key: str = Field(min_length=40, max_length=100)
    protocol_version: int = Field(default=1, ge=1, le=1000)
    app_version: str = Field(default="", max_length=80)
    platform: str = Field(default="", max_length=80)
    arch: str = Field(default="", max_length=80)
    capabilities: dict[str, Any] = Field(default_factory=dict)


@router.post("/devices/register")
def register_device(body: DeviceRegister, account: Account = CurrentAccount) -> dict:
    _validate_public_metadata(body.capabilities)
    try:
        challenge = store.register_device(owner_id=account.id, **body.model_dump())
    except Exception as exc:
        _protocol_error(exc)
        raise
    return {"challenge": challenge}


class DeviceVerify(BaseModel):
    challenge_id: str = Field(min_length=1, max_length=200)
    signature: str = Field(min_length=40, max_length=200)


@router.post("/devices/{device_id}/verify")
def verify_device(device_id: str, body: DeviceVerify, account: Account = CurrentAccount) -> dict:
    try:
        auth = store.verify_device(
            owner_id=account.id, device_id=device_id,
            challenge_id=body.challenge_id, signature=body.signature,
        )
    except Exception as exc:
        _protocol_error(exc)
        raise
    return {"device": {"id": device_id}, **auth}


@router.get("/devices")
def devices(account: Account = CurrentAccount) -> dict:
    return {"devices": store.list_devices(account.id), "protocol_version": store.PROTOCOL_VERSION}


@router.delete("/devices/{device_id}")
def revoke_device(device_id: str, account: Account = CurrentAccount) -> dict:
    if not store.revoke_device(owner_id=account.id, device_id=device_id):
        raise HTTPException(404, "device not found")
    return {"revoked": True, "device_id": device_id}


class Heartbeat(BaseModel):
    capabilities: dict[str, Any] = Field(default_factory=dict)


@router.post("/agent/heartbeat")
def heartbeat(body: Heartbeat, device: store.DevicePrincipal = CurrentDevice) -> dict:
    _validate_public_metadata(body.capabilities)
    return store.heartbeat(device, body.capabilities)


class LeaseRequest(BaseModel):
    lease_seconds: int = Field(default=30, ge=5, le=300)


@router.post("/agent/runs/lease")
def lease_run(body: LeaseRequest, device: store.DevicePrincipal = CurrentDevice) -> dict:
    try:
        lease = store.lease_run(device, lease_seconds=body.lease_seconds)
    except Exception as exc:
        _protocol_error(exc)
        raise
    return {"lease": lease, "protocol_version": store.PROTOCOL_VERSION}


class LeaseRenew(BaseModel):
    lease_epoch: int = Field(ge=1)
    lease_seconds: int = Field(default=30, ge=5, le=300)


@router.post("/agent/runs/{run_id}/leases/{lease_id}/renew")
def renew_lease(
    run_id: str, lease_id: str, body: LeaseRenew,
    device: store.DevicePrincipal = CurrentDevice,
) -> dict:
    try:
        return store.renew_lease(
            device, run_id=run_id, lease_id=lease_id,
            lease_epoch=body.lease_epoch, lease_seconds=body.lease_seconds,
        )
    except Exception as exc:
        _protocol_error(exc)
        raise


class RunEvent(BaseModel):
    event_id: str = Field(min_length=8, max_length=200)
    sequence: int = Field(ge=1)
    type: str = Field(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_.-]+$")
    occurred_at: float = Field(gt=0)
    payload: dict[str, Any] = Field(default_factory=dict)
    hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")


class EventBatch(BaseModel):
    lease_epoch: int = Field(ge=1)
    events: list[RunEvent] = Field(min_length=1, max_length=100)


@router.post("/agent/runs/{run_id}/leases/{lease_id}/events")
def submit_events(
    run_id: str, lease_id: str, body: EventBatch,
    device: store.DevicePrincipal = CurrentDevice,
) -> dict:
    try:
        return store.submit_events(
            device, run_id=run_id, lease_id=lease_id, lease_epoch=body.lease_epoch,
            events=[event.model_dump() for event in body.events],
        )
    except Exception as exc:
        _protocol_error(exc)
        raise


@router.get("/agent/runs/{run_id}/leases/{lease_id}/commands")
def commands(
    run_id: str, lease_id: str, lease_epoch: int,
    device: store.DevicePrincipal = CurrentDevice,
) -> dict:
    try:
        return {"commands": store.pending_commands(
            device, run_id=run_id, lease_id=lease_id, lease_epoch=lease_epoch,
        )}
    except Exception as exc:
        _protocol_error(exc)
        raise


def _authorized_run(run_id: str, account: Account, *, write: bool) -> dict[str, Any]:
    run = business_store.get_record("business_runs", run_id)
    if run is None:
        raise HTTPException(404, "Run not found")
    project_id = run.get("project_id")
    if project_id:
        role = db.project_access_role(str(project_id), account.id)
        if role is None:
            raise HTTPException(404, "Run not found")
        if write and (db.project_is_archived(str(project_id)) or not can_write(role)):
            raise HTTPException(403, "Run is read-only")
    elif run["owner_id"] != account.id:
        raise HTTPException(404, "Run not found")
    return run


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str, account: Account = CurrentAccount) -> dict:
    run = _authorized_run(run_id, account, write=True)
    if run["owner_id"] != account.id:
        raise HTTPException(403, "only the Run owner can cancel execution")
    try:
        return {"run": store.request_cancel(run_id=run_id, owner_id=account.id)}
    except Exception as exc:
        _protocol_error(exc)
        raise


@router.get("/runs/{run_id}/events")
def run_events(
    run_id: str, after_epoch: int = 0, after_sequence: int = 0, limit: int = 500,
    account: Account = CurrentAccount,
) -> dict:
    run = _authorized_run(run_id, account, write=False)
    return {
        "run": run,
        "events": store.list_events(
            run_id=run_id, after_epoch=max(0, after_epoch),
            after_sequence=max(0, after_sequence), limit=max(1, min(1000, limit)),
        ),
    }


class AskUserAnswer(BaseModel):
    question_event_id: str = Field(min_length=8, max_length=200)
    answers: list[str] = Field(min_length=1, max_length=20)


@router.post("/runs/{run_id}/answer")
def answer_user(run_id: str, body: AskUserAnswer, account: Account = CurrentAccount) -> dict:
    run = _authorized_run(run_id, account, write=True)
    if run["owner_id"] != account.id:
        raise HTTPException(403, "only the Run owner can answer execution questions")
    try:
        return {"command": store.answer_user(
            run_id=run_id, owner_id=account.id,
            question_event_id=body.question_event_id, answers=body.answers,
        )}
    except Exception as exc:
        _protocol_error(exc)
        raise
