"""Channels —— 助理外部渠道的前端接口（WB-072 / WB-077）。

给助理页提供真实的渠道状态 + 真实会话历史 + 页面内配置（名字/人格/模型/开关/绑定/token），
并允许从 App 驱动同一个助手（与 Telegram 共用同一助理会话）。渠道是机器级 local-first 特性，
绑定在本机固定 LOCAL_USER 上，故这里不按登录用户过滤——App 与 Telegram 看到同一份助理对话。

安全（WB-077）：bot token 存 DB、write-only——任何响应都**绝不回传 token 值**，只用
`configured` 布尔表示是否已配。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from channels import telegram_bridge
from storage import db

router = APIRouter(prefix="/api/channels", tags=["channels"])


async def _with_messages(st: dict) -> dict:
    """给状态字典补上助理会话的真实 transcript（三个端点统一返回完整 channel 结构）。"""
    sid = st.get("session_id")
    messages = []
    if sid:
        messages = [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
            for m in db.list_messages(sid)
        ]
    return {**st, "messages": messages}


@router.get("/telegram")
async def telegram_channel() -> dict:
    return await _with_messages(await telegram_bridge.status())


class SayBody(BaseModel):
    text: str = Field(max_length=200_000)


@router.post("/telegram/say")
async def telegram_say(body: SayBody) -> dict:
    return await telegram_bridge.say(body.text)


class ConfigBody(BaseModel):
    # 助理设置（WB-077）。token 为 write-only：只在非空时写入，且绝不回传。enabled 可空。
    name: str | None = Field(default=None, max_length=60)
    persona: str | None = Field(default=None, max_length=4000)
    model: str | None = Field(default=None, max_length=120)
    enabled: bool | None = None
    token: str | None = Field(default=None, max_length=200)


@router.patch("/telegram/config")
async def telegram_config(body: ConfigBody) -> dict:
    patch: dict = {}
    if body.name is not None:
        patch["name"] = body.name.strip()
    if body.persona is not None:
        patch["persona"] = body.persona.strip()
    if body.model is not None:
        patch["model"] = body.model.strip()
    if body.enabled is not None:
        patch["enabled"] = 1 if body.enabled else 0
    # token 仅在用户实际输入了非空值时更新（留空 = 不改）；绝不回传其值。
    if body.token and body.token.strip():
        patch["bot_token"] = body.token.strip()
    return await _with_messages(await telegram_bridge.set_config(patch))


@router.post("/telegram/unbind")
async def telegram_unbind() -> dict:
    telegram_bridge.unbind()
    return await _with_messages(await telegram_bridge.status())
