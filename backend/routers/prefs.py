"""用户设置 · 个性化（WB-147）。

`GET/PUT /api/settings`：回复风格 + 自定义指令，按 owner 存 `user_settings` KV。
模块名用 prefs（不叫 settings）以避开 `config.settings` 的命名冲突。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Literal

from agent import agent_settings
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


# ---- 智能体设置（WB-150）：工具步数上限 + 回复发散度 ------------------------

class AgentBody(BaseModel):
    max_rounds: int | None = None
    temperature: float | None = None


@router.get("/agent")
def get_agent_settings() -> dict:
    return agent_settings.get_settings(current_user().id)


@router.put("/agent")
def put_agent_settings(body: AgentBody) -> dict:
    owner = current_user().id
    agent_settings.set_settings(owner, max_rounds=body.max_rounds, temperature=body.temperature)
    return agent_settings.get_settings(owner)


# ---- 系统设置（WB-199）：只提供有真实执行链路的应用级偏好 ------------------

SYS_SCALE = "system.interface_scale"
SYS_REDUCE_MOTION = "system.reduce_motion"
SYS_DEFAULT_PERMISSION = "system.default_permission"
SYS_STARTUP_PAGE = "system.startup_page"


class SystemBody(BaseModel):
    interface_scale: Literal[90, 95, 100, 105, 110] | None = None
    reduce_motion: bool | None = None
    default_permission: Literal["default", "full"] | None = None
    startup_page: Literal["home", "projects", "knowledge", "automation"] | None = None


def _system_payload(owner_id: str) -> dict:
    raw_scale = db.get_user_setting(owner_id, SYS_SCALE)
    try:
        scale = int(raw_scale or "100")
    except ValueError:
        scale = 100
    if scale not in {90, 95, 100, 105, 110}:
        scale = 100
    permission = db.get_user_setting(owner_id, SYS_DEFAULT_PERMISSION) or "default"
    startup = db.get_user_setting(owner_id, SYS_STARTUP_PAGE) or "home"
    return {
        "interface_scale": scale,
        "reduce_motion": db.get_user_setting(owner_id, SYS_REDUCE_MOTION) == "1",
        "default_permission": permission if permission in {"default", "full"} else "default",
        "startup_page": startup if startup in {"home", "projects", "knowledge", "automation"} else "home",
    }


@router.get("/system")
def get_system_settings() -> dict:
    return _system_payload(current_user().id)


@router.put("/system")
def put_system_settings(body: SystemBody) -> dict:
    owner = current_user().id
    if body.interface_scale is not None:
        db.set_user_setting(owner, SYS_SCALE, None if body.interface_scale == 100 else str(body.interface_scale))
    if body.reduce_motion is not None:
        db.set_user_setting(owner, SYS_REDUCE_MOTION, "1" if body.reduce_motion else None)
    if body.default_permission is not None:
        db.set_user_setting(owner, SYS_DEFAULT_PERMISSION, None if body.default_permission == "default" else body.default_permission)
    if body.startup_page is not None:
        db.set_user_setting(owner, SYS_STARTUP_PAGE, None if body.startup_page == "home" else body.startup_page)
    return _system_payload(owner)
