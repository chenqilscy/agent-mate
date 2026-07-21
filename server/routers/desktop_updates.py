"""Signed desktop update registry, rollout endpoint and telemetry (WB-257)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, Field

from auth import CurrentAccount
from models import Account
import update_store

router = APIRouter(prefix="/api", tags=["desktop-updates"])
update_store.ensure_tables()


def _admin(account: Account) -> None:
    if not account.is_platform_admin:
        raise HTTPException(403, "platform admin only")


class ArtifactBody(BaseModel):
    target: str = Field(min_length=1, max_length=40)
    arch: str = Field(min_length=1, max_length=40)
    url: str = Field(min_length=1, max_length=2000)
    signature: str = Field(min_length=32, max_length=4000)
    sha256: str = Field(min_length=64, max_length=64)
    size_bytes: int = Field(gt=0)


class ReleaseBody(BaseModel):
    version: str = Field(min_length=5, max_length=80)
    channel: Literal["stable", "beta"] = "stable"
    notes: str = Field(default="", max_length=10000)
    artifacts: list[ArtifactBody] = Field(min_length=1)


class PublishBody(BaseModel):
    rollout_percent: int = Field(default=100, ge=1, le=100)
    min_supported_version: str = Field(default="0.0.0", min_length=5, max_length=80)


class PauseBody(BaseModel):
    paused: bool = True


class RollbackBody(BaseModel):
    release_id: str = Field(min_length=1, max_length=100)


class EventBody(BaseModel):
    channel: Literal["stable", "beta"] = "stable"
    event: Literal["download_failed", "install_failed", "installed"]
    target: str = Field(default="", max_length=40)
    arch: str = Field(default="", max_length=40)
    current_version: str = Field(default="", max_length=40)
    release_id: str | None = Field(default=None, max_length=100)
    error_code: str = Field(default="", max_length=120)


@router.get("/admin/desktop-releases")
def releases(account: Account = CurrentAccount) -> dict:
    _admin(account)
    return {"releases": update_store.list_releases(), "metrics": update_store.update_metrics()}


@router.post("/admin/desktop-releases")
def create_release(body: ReleaseBody, account: Account = CurrentAccount) -> dict:
    _admin(account)
    try:
        release = update_store.create_release(
            version=body.version, channel=body.channel, notes=body.notes,
            artifacts=[item.model_dump() for item in body.artifacts], created_by=account.id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        if "UNIQUE constraint" in str(exc):
            raise HTTPException(409, "release version already exists") from exc
        raise
    return {"release": release}


@router.post("/admin/desktop-releases/{release_id}/publish")
def publish(release_id: str, body: PublishBody, account: Account = CurrentAccount) -> dict:
    _admin(account)
    try:
        return {"channel": update_store.publish_release(
            release_id, rollout_percent=body.rollout_percent,
            min_supported_version=body.min_supported_version,
        )}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/admin/desktop-update-channels/{channel}/pause")
def pause(channel: str, body: PauseBody, account: Account = CurrentAccount) -> dict:
    _admin(account)
    try:
        return {"channel": update_store.pause_channel(channel, body.paused)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/admin/desktop-update-channels/{channel}/rollback")
def rollback(channel: str, body: RollbackBody, account: Account = CurrentAccount) -> dict:
    _admin(account)
    try:
        return {"channel": update_store.rollback_channel(channel, body.release_id)}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/desktop-updates/{channel}/{target}/{arch}/{current_version}", response_model=None)
def check_update(
    channel: str, target: str, arch: str, current_version: str,
    x_agentmate_device: str = Header(default=""),
) -> dict | Response:
    try:
        result = update_store.select_update(
            channel=channel, target=target, arch=arch, current_version=current_version,
            device_id=x_agentmate_device,
        )
    except (ValueError, LookupError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return result if result is not None else Response(status_code=204)


@router.post("/desktop-updates/events", status_code=202)
def record_update_event(body: EventBody, x_agentmate_device: str = Header(default="")) -> dict:
    try:
        update_store.record_event(device_id=x_agentmate_device, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"accepted": True}
