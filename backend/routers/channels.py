"""Channels —— 助理外部渠道的前端接口（WB-072 Slice 2）。

给助理页提供真实的渠道状态 + 真实会话历史，并允许从 App 驱动同一个助手（与 Telegram
共用同一助理会话）。渠道是机器级 local-first 特性，绑定在本机固定 LOCAL_USER 上，故这里
不按登录用户过滤——App 与 Telegram 在同一台机器上看到同一份助理对话。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from channels import telegram_bridge
from storage import db

router = APIRouter(prefix="/api/channels", tags=["channels"])


@router.get("/telegram")
async def telegram_channel() -> dict:
    st = await telegram_bridge.status()
    sid = st.get("session_id")
    messages = []
    if sid:
        messages = [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
            for m in db.list_messages(sid)
        ]
    return {**st, "messages": messages}


class SayBody(BaseModel):
    text: str = Field(max_length=200_000)


@router.post("/telegram/say")
async def telegram_say(body: SayBody) -> dict:
    return await telegram_bridge.say(body.text)
