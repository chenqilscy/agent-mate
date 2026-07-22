"""Platform-admin setting registry and audit endpoints (WB-291)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db
import platform_settings
import weknora
from auth import CurrentAccount
from models import Account

router = APIRouter(prefix="/api/admin/settings", tags=["platform-settings"])


def _admin(account: Account) -> None:
    if not account.is_platform_admin:
        raise HTTPException(403, "platform admin only")


class UpdateBody(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    clear: list[str] = Field(default_factory=list, max_length=50)


class TestBody(BaseModel):
    group: str = Field(min_length=1, max_length=60)


def _payload() -> dict[str, Any]:
    return {
        "items": platform_settings.public_registry(),
        "deployment_only": sorted(platform_settings.DEPLOYMENT_ONLY_KEYS),
        "audit": db.list_platform_settings_audit(),
    }


@router.get("")
def get_platform_settings(account: Account = CurrentAccount) -> dict[str, Any]:
    _admin(account)
    return _payload()


@router.put("")
def put_platform_settings(body: UpdateBody, account: Account = CurrentAccount) -> dict[str, Any]:
    _admin(account)
    overlap = set(body.values) & set(body.clear)
    if overlap:
        raise HTTPException(400, f"同一设置不能同时保存和清除：{', '.join(sorted(overlap))}")
    if not body.values and not body.clear:
        raise HTTPException(400, "没有要保存的设置。")
    try:
        for key, value in body.values.items():
            platform_settings.validate(key, value)
        for key in body.clear:
            platform_settings.definition(key)
        for key, value in body.values.items():
            platform_settings.set_value(key, value, actor_id=account.id)
        for key in body.clear:
            platform_settings.clear_value(key, actor_id=account.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _payload()


@router.post("/test")
def test_platform_settings(body: TestBody, account: Account = CurrentAccount) -> dict[str, Any]:
    _admin(account)
    if body.group != "knowledge":
        raise HTTPException(400, f"设置组不支持连接测试：{body.group}")
    try:
        info = weknora.system_info()
        models = weknora.list_models()
    except weknora.WeKnoraError as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "version": str(info.get("version") or ""),
        "embedding_models": sum(
            1 for model in models if str(model.get("type", "")).lower() == "embedding"
        ),
    }
