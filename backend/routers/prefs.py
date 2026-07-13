"""用户设置 · 个性化（WB-147）。

`GET/PUT /api/settings`：回复风格 + 自定义指令，按 owner 存 `user_settings` KV。
模块名用 prefs（不叫 settings）以避开 `config.settings` 的命名冲突。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from agent.personalization import (
    CUSTOM_MAX,
    PREF_CUSTOM,
    PREF_STYLE,
    PRESET_KEYS,
    STYLE_PRESETS,
    get_personalization,
)
from auth.deps import current_user
from storage import db

router = APIRouter(prefix="/api/settings", tags=["settings"])


class PersonalizationBody(BaseModel):
    style: str | None = None
    custom_instructions: str | None = None


def _payload(owner_id: str) -> dict:
    data = get_personalization(owner_id)
    return {
        **data,
        "style_presets": [
            {"key": p["key"], "label": p["label"], "desc": p["desc"]} for p in STYLE_PRESETS
        ],
    }


@router.get("")
def get_settings() -> dict:
    return _payload(current_user().id)


@router.put("")
def put_settings(body: PersonalizationBody) -> dict:
    owner = current_user().id
    # 风格：非法值回落 default；'default' → 删键（回到未设置）。
    if body.style is not None:
        key = body.style if body.style in PRESET_KEYS else "default"
        db.set_user_setting(owner, PREF_STYLE, None if key == "default" else key)
    # 自定义指令：trim + 截断上限；空 → 删键。
    if body.custom_instructions is not None:
        text = body.custom_instructions.strip()[:CUSTOM_MAX]
        db.set_user_setting(owner, PREF_CUSTOM, text or None)
    return _payload(owner)
