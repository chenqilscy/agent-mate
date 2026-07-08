"""Channels —— 多助理 + 多渠道管理接口（WB-086/087/088/089）。

`/api/assistants*`：多助理 + 渠道的 CRUD；`/api/channels/types`：渠道类型注册表。
渠道是机器级 local-first 特性，绑定本机固定 LOCAL_USER；token 存 DB、write-only、绝不回传前端。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from channels import manager
from storage import db
from storage.models import LOCAL_USER_ID

router = APIRouter(prefix="/api", tags=["channels"])


class SayBody(BaseModel):
    text: str = Field(max_length=200_000)


# ---- 渠道类型注册表 -----------------------------------------------------

@router.get("/channels/types")
def channel_types() -> dict:
    return {"types": manager.CHANNEL_TYPES}


# ---- 多助理 CRUD（WB-087）----------------------------------------------

class AssistantBody(BaseModel):
    name: str | None = Field(default=None, max_length=60)
    avatar: str | None = Field(default=None, max_length=8)
    instruction: str | None = Field(default=None, max_length=8000)
    model: str | None = Field(default=None, max_length=120)
    mode: str | None = None            # exec | plan | ask
    workspace: str | None = Field(default=None, max_length=200)  # default | project:<id> | dedicated
    experts: list[str] | None = Field(default=None, max_length=50)
    skills: list[str] | None = Field(default=None, max_length=50)
    connectors: list[str] | None = Field(default=None, max_length=50)
    enabled: bool | None = None


class ChannelBody(BaseModel):
    type: str | None = None            # 创建时必填（telegram）
    config: dict | None = None         # 类型相关（telegram: 可含 chat_id 白名单）
    token: str | None = Field(default=None, max_length=200)  # write-only 便捷字段 → config.bot_token
    enabled: bool | None = None


_VALID_MODES = {"exec", "plan", "ask"}


def _owned_assistant(assistant_id: str) -> dict:
    a = db.get_assistant(assistant_id)
    if a is None or a["owner_id"] != LOCAL_USER_ID:
        raise HTTPException(404, "assistant not found")
    return a


@router.get("/assistants")
def list_assistants() -> dict:
    return {"assistants": [manager.assistant_public(a) for a in db.list_assistants(LOCAL_USER_ID)]}


@router.post("/assistants")
async def create_assistant(body: AssistantBody) -> dict:
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    mode = body.mode if body.mode in _VALID_MODES else "exec"
    a = db.create_assistant(
        owner_id=LOCAL_USER_ID, name=name, avatar=body.avatar, instruction=body.instruction,
        model=body.model, mode=mode, workspace=(body.workspace or "default"),
        experts=body.experts or [], skills=body.skills or [], connectors=body.connectors or [],
        enabled=True if body.enabled is None else body.enabled,
    )
    await manager.refresh()
    return manager.assistant_public(a, with_messages=True)


@router.get("/assistants/{assistant_id}")
def get_assistant(assistant_id: str) -> dict:
    return manager.assistant_public(_owned_assistant(assistant_id), with_messages=True)


@router.patch("/assistants/{assistant_id}")
async def update_assistant(assistant_id: str, body: AssistantBody) -> dict:
    _owned_assistant(assistant_id)
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if "mode" in patch and patch["mode"] not in _VALID_MODES:
        patch.pop("mode")
    db.update_assistant(assistant_id, **patch)
    await manager.refresh()
    return manager.assistant_public(db.get_assistant(assistant_id), with_messages=True)


@router.delete("/assistants/{assistant_id}")
async def delete_assistant(assistant_id: str) -> dict:
    _owned_assistant(assistant_id)
    db.delete_assistant(assistant_id)
    await manager.refresh()
    return {"ok": True}


@router.post("/assistants/{assistant_id}/say")
async def assistant_say(assistant_id: str, body: SayBody) -> dict:
    _owned_assistant(assistant_id)
    return await manager.say(assistant_id, body.text)


@router.post("/assistants/{assistant_id}/channels")
async def add_channel(assistant_id: str, body: ChannelBody) -> dict:
    _owned_assistant(assistant_id)
    ctype = (body.type or "").strip()
    if not any(t["type"] == ctype and t["available"] for t in manager.CHANNEL_TYPES):
        raise HTTPException(400, "unsupported or unavailable channel type")
    config = dict(body.config or {})
    if body.token and body.token.strip():
        config["bot_token"] = body.token.strip()
    ch = db.create_channel(assistant_id=assistant_id, type=ctype, config=config,
                           enabled=False if body.enabled is None else body.enabled)
    await manager.refresh()
    return manager.channel_public(ch)


@router.patch("/assistants/{assistant_id}/channels/{channel_id}")
async def update_channel(assistant_id: str, channel_id: str, body: ChannelBody) -> dict:
    _owned_assistant(assistant_id)
    ch = db.get_channel(channel_id)
    if ch is None or ch["assistant_id"] != assistant_id:
        raise HTTPException(404, "channel not found")
    config = dict(body.config or {})
    if body.token and body.token.strip():
        config["bot_token"] = body.token.strip()
    db.update_channel(channel_id, config=(config or None), enabled=body.enabled)
    await manager.refresh()
    return manager.channel_public(db.get_channel(channel_id))


@router.delete("/assistants/{assistant_id}/channels/{channel_id}")
async def delete_channel(assistant_id: str, channel_id: str) -> dict:
    _owned_assistant(assistant_id)
    ch = db.get_channel(channel_id)
    if ch is None or ch["assistant_id"] != assistant_id:
        raise HTTPException(404, "channel not found")
    db.delete_channel(channel_id)
    await manager.refresh()
    return {"ok": True}


@router.post("/assistants/{assistant_id}/channels/{channel_id}/unbind")
async def unbind_channel(assistant_id: str, channel_id: str) -> dict:
    _owned_assistant(assistant_id)
    ch = db.get_channel(channel_id)
    if ch is None or ch["assistant_id"] != assistant_id:
        raise HTTPException(404, "channel not found")
    db.clear_channel_chats(channel_id)
    return manager.channel_public(db.get_channel(channel_id))
