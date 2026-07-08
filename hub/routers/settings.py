"""平台设置（WB-095）—— 平台管理员维护服务端凭据/配置。

目前：SkillHub API key（供取数带 Bearer / 企业 registry / 未来发布）。
安全：GET 只回**打码**状态（configured + hint），**绝不回传全 key**（铁律#4）；key 只落 Hub 服务端 SQLite。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import db
from auth import CurrentAccount
from models import Account

router = APIRouter(prefix="/api", tags=["settings"])

_SKILLHUB_KEY = "skillhub_api_key"


def _require_admin(account: Account) -> None:
    if not account.is_platform_admin:
        raise HTTPException(403, "platform admin only")


def _hint(key: str) -> str:
    """打码：保留前 8 + 后 4，看得出是哪把 key、认不出全值。"""
    key = (key or "").strip()
    return (key[:8] + "…" + key[-4:]) if len(key) > 14 else ("(已配置)" if key else "")


@router.get("/settings")
def get_settings(account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    sk = db.get_setting(_SKILLHUB_KEY) or ""
    kind = "enterprise" if sk.startswith("sk-ent-") else ("community" if sk.startswith("skh_") else ("" if not sk else "other"))
    return {"skillhub_api_key": {"configured": bool(sk), "hint": _hint(sk), "kind": kind}}


class SkillhubKeyBody(BaseModel):
    key: str


@router.put("/settings/skillhub-key")
def set_skillhub_key(body: SkillhubKeyBody, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    key = (body.key or "").strip()
    if not key:
        raise HTTPException(400, "empty key")
    db.set_setting(_SKILLHUB_KEY, key)
    return {"ok": True, "hint": _hint(key)}


@router.delete("/settings/skillhub-key")
def clear_skillhub_key(account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    db.delete_setting(_SKILLHUB_KEY)
    return {"ok": True}
