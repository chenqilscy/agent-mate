"""Telegram — a built-in local MCP server (stdio) that talks to the Telegram Bot API.

Lets the agent send and read Telegram messages through a bot. Same shape as the
other built-in connectors (notes / clock / search): one FastMCP server, launched
in-process — so it works in dev and in a frozen bundle, no Node/npx needed.

Unlike those, it needs one credential: TELEGRAM_BOT_TOKEN (from @BotFather). The
token is read from the environment AT CALL TIME (never baked in, never sent to
the frontend — hard-line #4), and the connector is gated by `requires` in
mcp_client.py so a run without the token is skipped with a clear reason.

Tools are `async` and use httpx.AsyncClient: this server runs in-process on the
backend's event loop, so a blocking network call would stall every other SSE
stream (WB-002) — awaiting keeps the loop free.

Run standalone: `python telegram.py` (speaks MCP on stdio).
"""
from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("telegram")

# Telegram caps message text at 4096 chars; refuse oversized sends with a clear
# message rather than letting the API reject them opaquely.
_MAX_TEXT = 4096
_TIMEOUT = 20.0


def _token() -> str:
    # Read at call time (not import) so the server picks up backend/.env whether
    # it runs in-process (env already loaded) or as a spawned subprocess.
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def _default_chat() -> str:
    return os.environ.get("TELEGRAM_CHAT_ID", "").strip()


async def _api(method: str, params: dict | None = None) -> tuple[bool, object]:
    """Call one Telegram Bot API method. Returns (ok, result_or_error_message).

    Never raises: network / HTTP / API errors come back as (False, <human text>)
    so a broken call degrades to a readable tool result instead of crashing chat.
    """
    token = _token()
    if not token:
        return False, "未配置 TELEGRAM_BOT_TOKEN（应在 backend/.env 设置）。"
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
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


@mcp.tool()
async def get_me() -> str:
    """校验 bot 身份与 token 是否有效，返回 bot 的用户名与显示名。"""
    ok, res = await _api("getMe")
    if not ok:
        return str(res)
    name = res.get("first_name") or ""
    username = res.get("username") or ""
    handle = f"@{username}" if username else "(无用户名)"
    return f"Bot 有效：{name} {handle}（id={res.get('id')}）。"


@mcp.tool()
async def send_message(text: str, chat_id: str = "") -> str:
    """向指定 Telegram 会话发送一条文本消息。

    chat_id 留空则回退到 backend/.env 的 TELEGRAM_CHAT_ID。chat_id 可以是数字会话 ID，
    也可以是形如 @channelusername 的频道用户名。若不知道 chat_id，先让对方给 bot 发一条
    消息，再用 get_updates 查看其 chat_id。
    """
    text = (text or "").strip()
    if not text:
        return "消息内容为空，未发送。"
    if len(text) > _MAX_TEXT:
        return f"消息过长（{len(text)} 字符，上限 {_MAX_TEXT}），未发送。"
    target = (chat_id or "").strip() or _default_chat()
    if not target:
        return "缺少 chat_id：请提供，或在 backend/.env 配置 TELEGRAM_CHAT_ID。"
    ok, res = await _api("sendMessage", {"chat_id": target, "text": text})
    if not ok:
        return str(res)
    mid = res.get("message_id")
    return f"已发送到会话 {target}（message_id={mid}）。"


@mcp.tool()
async def get_updates(limit: int = 10) -> str:
    """拉取 bot 最近收到的消息（getUpdates），用于获知对方 chat_id 与回复内容。

    返回每条消息的 发送人 / chat_id / 文本。注意：Telegram 只保留约 24 小时内、且未被
    webhook 消费的更新；若 bot 设置了 webhook，此接口会为空。
    """
    limit = max(1, min(int(limit or 10), 100))
    ok, res = await _api("getUpdates", {"limit": limit})
    if not ok:
        return str(res)
    if not res:
        return "（暂无新消息。让对方先给 bot 发一条消息后再试。）"
    lines: list[str] = []
    for upd in res:
        msg = upd.get("message") or upd.get("channel_post") or {}
        chat = msg.get("chat") or {}
        frm = msg.get("from") or {}
        who = frm.get("username") or frm.get("first_name") or chat.get("title") or "未知"
        text = (msg.get("text") or "(非文本消息)").strip()
        lines.append(f"[{who}] chat_id={chat.get('id')}: {text[:300]}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
