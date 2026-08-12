"""Server Asset object-byte protocol (WB-436)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import asset_object_store as objects
import business_store
import db
from auth import CurrentAccount
from models import Account, can_write


router = APIRouter(prefix="/api/assets", tags=["asset-objects"])


def _asset(asset_id: str, account: Account, *, write: bool = False) -> dict[str, Any]:
    asset = business_store.get_record("business_assets", asset_id)
    if not asset:
        raise HTTPException(404, "asset not found")
    project_id = asset.get("project_id")
    if project_id:
        role = db.project_access_role(str(project_id), account.id)
        if role is None:
            raise HTTPException(404, "asset not found")
        if write and (db.project_is_archived(str(project_id)) or not can_write(role)):
            raise HTTPException(403, "project is read-only")
    elif asset["owner_id"] != account.id:
        raise HTTPException(404, "asset not found")
    return asset


def _error(exc: Exception) -> None:
    if isinstance(exc, KeyError):
        raise HTTPException(404, "asset upload not found") from exc
    if isinstance(exc, objects.ObjectConflict):
        raise HTTPException(409, str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(400, str(exc)) from exc
    raise exc


class UploadStart(BaseModel):
    asset_id: str = Field(min_length=1, max_length=200)
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


@router.post("/uploads")
def start_upload(body: UploadStart, account: Account = CurrentAccount) -> dict[str, Any]:
    asset = _asset(body.asset_id, account, write=True)
    try:
        return {
            "upload": objects.begin_upload(
                asset, actor_id=account.id,
                expected_size=body.size, expected_sha256=body.sha256,
            ),
        }
    except Exception as exc:
        _error(exc)
        raise


@router.get("/uploads/{upload_id}")
def get_upload(upload_id: str, account: Account = CurrentAccount) -> dict[str, Any]:
    try:
        return {"upload": objects.upload_status(upload_id, account.id)}
    except Exception as exc:
        _error(exc)
        raise


@router.put("/uploads/{upload_id}/parts/{part_number}")
async def upload_part(
    upload_id: str, part_number: int, request: Request,
    part_sha256: str = Header(alias="X-Part-SHA256"), account: Account = CurrentAccount,
) -> dict[str, Any]:
    data = await request.body()
    if len(data) > settings_part_limit():
        raise HTTPException(413, "upload part is too large")
    try:
        return {"part": objects.put_part(upload_id, account.id, part_number, data, part_sha256)}
    except Exception as exc:
        _error(exc)
        raise


def settings_part_limit() -> int:
    from config import settings
    return settings.ASSET_UPLOAD_PART_BYTES


@router.post("/uploads/{upload_id}/complete")
def finish_upload(upload_id: str, account: Account = CurrentAccount) -> dict[str, Any]:
    try:
        return objects.complete_upload(upload_id, account.id)
    except Exception as exc:
        _error(exc)
        raise


@router.delete("/uploads/{upload_id}")
def cancel_upload(upload_id: str, account: Account = CurrentAccount) -> dict[str, bool]:
    if not objects.abort_upload(upload_id, account.id):
        raise HTTPException(404, "active upload not found")
    return {"aborted": True}


@router.post("/{asset_id}/download-grant")
def download_grant(asset_id: str, account: Account = CurrentAccount) -> dict[str, Any]:
    asset = _asset(asset_id, account)
    try:
        return objects.create_download_grant(asset)
    except Exception as exc:
        _error(exc)
        raise


@router.get("/{asset_id}/content")
def download_content(
    asset_id: str,
    asset_token: str = Header(default="", alias="X-Asset-Token"),
    download: bool = Query(default=True),
):
    if not asset_token:
        raise HTTPException(401, "asset download grant required")
    try:
        grant, path = objects.authorize_download(asset_id, asset_token)
    except KeyError as exc:
        raise HTTPException(401, "asset download grant is invalid or expired") from exc
    except Exception as exc:
        _error(exc)
        raise
    disposition = "attachment" if download else "inline"
    return FileResponse(
        path, media_type="application/octet-stream", filename=str(grant["name"]),
        content_disposition_type=disposition,
        headers={"X-Asset-SHA256": str(grant["sha256"]), "X-Asset-Version": str(grant["object_version_id"])},
    )
