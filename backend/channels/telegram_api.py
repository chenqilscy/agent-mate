"""Telegram Bot API —— 助理渠道用的底层客户端（WB-072 / WB-087）。

WB-087：从「全局 token override」改为**每次调用显式传 token**——多助理下会同时存在多个
bot，各自 token 不同，不能有全局单例。所有函数第一个参数就是该 bot 的 token。

依赖极简（只 os + httpx），永不抛异常：网络/HTTP/API 错误一律回成 (False, <可读文本>)，
让上层轮询循环稳。token 只存后端（DB/.env），绝不回传前端（铁律#4，见 WB-077）。
"""
from __future__ import annotations

import httpx

# Telegram 单条文本上限 4096 字符；超出分片发送。
MAX_TEXT = 4096
_CONNECT_TIMEOUT = 15.0


async def api(token: str, method: str, params: dict | None = None, *, timeout: float = 20.0) -> tuple[bool, object]:
    """调用一个 Bot API 方法，返回 (ok, result_or_error_text)。永不抛异常。
    timeout 是 HTTP 读超时——长轮询的 getUpdates 需传大于其 poll timeout 的值。"""
    token = (token or "").strip()
    if not token:
        return False, "未配置 bot token。"
    url = f"https://api.telegram.org/bot{token}/{method}"
    to = httpx.Timeout(timeout, connect=_CONNECT_TIMEOUT)
    try:
        async with httpx.AsyncClient(timeout=to) as client:
            resp = await client.post(url, json=params or {})
    except httpx.HTTPError as e:
        return False, f"网络请求失败：{e}（Telegram API 在部分网络下需要代理）。"
    try:
        data = resp.json()
    except ValueError:
        return False, f"Telegram 返回了非 JSON 响应（HTTP {resp.status_code}）。"
    if not data.get("ok"):
        desc = data.get("description") or f"HTTP {resp.status_code}"
        return False, f"Telegram API 拒绝了请求：{desc}"
    return True, data.get("result")


async def get_me(token: str) -> tuple[bool, object]:
    """校验 bot token；成功时 result 含 username / first_name / id。"""
    return await api(token, "getMe", timeout=15.0)


async def delete_webhook(token: str, drop_pending: bool = False) -> tuple[bool, object]:
    """删除该 bot 已注册的 webhook。长轮询与 webhook 互斥（否则 getUpdates 409），启动先删一次。"""
    return await api(token, "deleteWebhook", {"drop_pending_updates": drop_pending}, timeout=15.0)


async def get_updates(token: str, offset: int | None = None, *, timeout: int = 30, limit: int = 100) -> tuple[bool, object]:
    """长轮询拉取更新。offset = 上次已处理 update_id + 1。"""
    params: dict = {"timeout": timeout, "limit": max(1, min(limit, 100))}
    if offset is not None:
        params["offset"] = offset
    return await api(token, "getUpdates", params, timeout=timeout + 15)


def chunk_text(text: str) -> list[str]:
    """按 4096 上限切片；空串也回一个元素，方便调用方统一处理。"""
    text = text or ""
    if not text:
        return [""]
    return [text[i : i + MAX_TEXT] for i in range(0, len(text), MAX_TEXT)]


async def send_message(token: str, chat_id: str | int, text: str) -> tuple[bool, object]:
    """向 chat 发送文本，>4096 自动分片顺序发送；返回最后一片的结果。"""
    text = (text or "").strip() or "（空消息）"
    result: tuple[bool, object] = (False, "未发送")
    for part in chunk_text(text):
        result = await api(token, "sendMessage", {"chat_id": chat_id, "text": part})
        if not result[0]:
            break
    return result
