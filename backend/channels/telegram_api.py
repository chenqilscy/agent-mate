"""Telegram Bot API —— 助理渠道用的底层客户端（WB-072）。

和 `mcp_servers/telegram.py` 里的小客户端同源，但有两点不同，所以单独放一份而不共用：
1. **长轮询感知的超时**：getUpdates 会被 Telegram 服务器挂起 `timeout` 秒才返回，
   所以 HTTP 读超时必须 > 该 timeout，否则长轮询会被客户端提前掐断（连接器那份固定 20s，
   不适合长轮询）。
2. **依赖极简**（只 os + httpx）：不拉入 app 包树，保持与「独立 stdio 子进程」形态的 MCP
   连接器解耦。

永不抛异常：网络/HTTP/API 错误一律回成 (False, <可读文本>)，让桥接循环稳。
token 在**调用时**读环境变量（铁律 #4：只存后端 .env，绝不进前端/其它子进程）。
"""
from __future__ import annotations

import os

import httpx

# Telegram 单条文本上限 4096 字符；超出分片发送。
MAX_TEXT = 4096
_CONNECT_TIMEOUT = 15.0


# DB 里配置的 token（WB-077）由桥接在启动/改配置时灌进来，优先于 .env。放这里而不 import db，
# 是为了保持本模块依赖极简（只 os+httpx），与「独立 stdio 子进程」形态的 MCP 连接器解耦。
_token_override: Optional[str] = None


def set_token_override(tok: Optional[str]) -> None:
    global _token_override
    _token_override = (tok or "").strip() or None


def token() -> str:
    return (_token_override or os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()


def default_chat() -> str:
    return os.environ.get("TELEGRAM_CHAT_ID", "").strip()


async def api(method: str, params: dict | None = None, *, timeout: float = 20.0) -> tuple[bool, object]:
    """调用一个 Bot API 方法，返回 (ok, result_or_error_text)。永不抛异常。

    timeout 是 HTTP 读超时——长轮询的 getUpdates 需要传大于其 poll timeout 的值。
    """
    tok = token()
    if not tok:
        return False, "未配置 TELEGRAM_BOT_TOKEN（应在 backend/.env 设置）。"
    url = f"https://api.telegram.org/bot{tok}/{method}"
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


async def get_me() -> tuple[bool, object]:
    """校验 bot token；成功时 result 含 username / first_name / id。"""
    return await api("getMe", timeout=15.0)


async def delete_webhook(drop_pending: bool = False) -> tuple[bool, object]:
    """删除该 bot 上已注册的 webhook。长轮询与 webhook 互斥——若之前设过 webhook，
    getUpdates 会 409。桥接改用长轮询，故启动时先无条件删一次（无 webhook 时也安全）。
    drop_pending=True 会丢弃积压更新（这里默认保留，避免误删用户离线时发的消息）。"""
    return await api("deleteWebhook", {"drop_pending_updates": drop_pending}, timeout=15.0)


async def get_updates(offset: int | None = None, *, timeout: int = 30, limit: int = 100) -> tuple[bool, object]:
    """长轮询拉取更新。offset = 上次已处理 update_id + 1（Telegram 据此确认/删除旧更新）。"""
    params: dict = {"timeout": timeout, "limit": max(1, min(limit, 100))}
    if offset is not None:
        params["offset"] = offset
    # 读超时给足余量，别把服务器端挂起的长轮询提前掐断。
    return await api("getUpdates", params, timeout=timeout + 15)


def chunk_text(text: str) -> list[str]:
    """按 4096 上限切片；空串也回一个元素，方便调用方统一处理。"""
    text = text or ""
    if not text:
        return [""]
    return [text[i : i + MAX_TEXT] for i in range(0, len(text), MAX_TEXT)]


async def send_message(chat_id: str | int, text: str) -> tuple[bool, object]:
    """向 chat 发送文本，>4096 自动分片顺序发送；返回最后一片的结果。"""
    text = (text or "").strip() or "（空消息）"
    result: tuple[bool, object] = (False, "未发送")
    for part in chunk_text(text):
        result = await api("sendMessage", {"chat_id": chat_id, "text": part})
        if not result[0]:
            break
    return result
