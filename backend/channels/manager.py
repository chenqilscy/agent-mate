"""渠道管理器（WB-086/087）—— 多助理 · 多渠道运行时。

取代 WB-072 的单一全局桥接：为每个「启用且类型可用」的渠道起一个独立 poller（Telegram：
一个长轮询 loop，各自 token / 游标）。入站消息 → 按渠道鉴权 → 路由到其助理 → 用该助理的
loadout / 工作空间 / mode 驱动真实 run_chat → 原渠道回复。

App 面向：assistants / channels 的读态（**绝不回传 token**）+ 从 App 驱动某助理（say）+
配置变更后 refresh() 协调 poller。CRUD 走 db.py。
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from agent import runtime
from channels import telegram_api as tg
from storage import db
from storage.models import LOCAL_USER_ID

log = logging.getLogger("workbuddy.channels")

POLL_TIMEOUT = 30
RUN_TIMEOUT = 300
_BACKOFF = 5

_pollers: dict[str, asyncio.Task] = {}       # channel_id -> poll task
_running_token: dict[str, str] = {}          # channel_id -> token the poller was started with
_busy: set[str] = set()                       # "channel_id:chat_id" 处理中，防同 chat 并发
_bot_cache: dict[str, tuple[float, Optional[str]]] = {}  # token -> (at, username)

# 渠道类型注册表：决定前端「新增渠道」能选什么、每类型可用与否（不造假——只 Telegram available）。
CHANNEL_TYPES = [
    {"type": "telegram", "label": "Telegram", "available": True},
    {"type": "wecom", "label": "企业微信", "available": False},
    {"type": "whatsapp", "label": "WhatsApp", "available": False},
    {"type": "email", "label": "邮件", "available": False},
]


# ---- 助理会话 -----------------------------------------------------------

def ensure_assistant_session(a: dict) -> str:
    """助理的共享会话（App + 各渠道同写一份 transcript），没有则建并回写。"""
    sid = a.get("session_id")
    if sid and db.get_session(sid):
        return sid
    session = db.create_session(owner_id=a["owner_id"], title=(a.get("name") or "助理")[:26], kind="assistant")
    db.update_assistant(a["id"], session_id=session.id)
    return session.id


# ---- 驱动 agent ---------------------------------------------------------

def _workspace_spec(a: dict) -> str:
    ws = a.get("workspace") or "default"
    return f"dedicated:{a['id']}" if ws == "dedicated" else ws


async def _run_agent(a: dict, session_id: str, text: str) -> str:
    user = db.get_user(a["owner_id"]) or db.get_user(LOCAL_USER_ID)
    session = db.get_session(session_id)
    if user is None or session is None:
        return "（本机用户或会话缺失，无法处理。）"
    before = {m.id for m in db.list_messages(session_id)}
    mode = a.get("mode") or "exec"

    async def _drive() -> None:
        async for _ in runtime.run_chat(
            session, user, text,
            model=(a.get("model") or None),
            plan=(mode == "plan"), ask=(mode == "ask"),
            experts=a.get("experts") or [], skills=a.get("skills") or [], connectors=a.get("connectors") or [],
            system_extra=(a.get("instruction") or None),
            workspace=_workspace_spec(a),
        ):
            pass

    try:
        await asyncio.wait_for(_drive(), timeout=RUN_TIMEOUT)
    except asyncio.TimeoutError:
        return "（处理超时，请把任务拆小一点再试。）"
    except Exception as e:  # noqa: BLE001 — 单条消息失败不该杀掉 poller
        log.exception("驱动 agent 失败")
        return f"（处理失败：{str(e)[:300]}）"
    for m in reversed(db.list_messages(session_id)):
        if m.role == "assistant" and m.id not in before and (m.content or "").strip():
            return m.content
    return "（助手这次没有产生文本回复。）"


# ---- Telegram 渠道：鉴权 + 路由 + 轮询 ---------------------------------

def _tg_token(ch: dict) -> str:
    return (ch.get("config", {}).get("bot_token") or "").strip()


def _is_start(text: str) -> bool:
    t = (text or "").strip()
    return t == "/start" or t.startswith("/start@") or t.startswith("/start ")


def _authorize_tg(ch: dict, chat_id: str) -> Optional[str]:
    """按渠道白名单 + /start 配对，返回会话 id（必要时配对绑定）；无权返回 None。"""
    existing = db.get_chat_session(ch["id"], chat_id)
    if existing:
        return existing["session_id"]
    allow = (ch.get("config", {}).get("chat_id") or "").strip()
    if allow:
        if str(chat_id) != allow:
            return None
    else:
        if db.first_chat_binding(ch["id"]) is not None:
            return None
    a = db.get_assistant(ch["assistant_id"])
    if a is None:
        return None
    session_id = ensure_assistant_session(a)
    db.bind_chat(ch["id"], str(chat_id), session_id, a["owner_id"])
    log.info("渠道 %s 绑定 chat=%s → session=%s", ch["id"], chat_id, session_id)
    return session_id


async def _handle_tg_update(ch_id: str, upd: dict) -> None:
    ch = db.get_channel(ch_id)
    if ch is None:
        return
    token = _tg_token(ch)
    msg = upd.get("message") or upd.get("edited_message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    text = msg.get("text")
    if chat_id is None:
        return
    session_id = _authorize_tg(ch, str(chat_id))
    if session_id is None:
        log.info("渠道 %s 忽略未授权 chat=%s", ch_id, chat_id)
        return
    if not text:
        await tg.send_message(token, chat_id, "目前我只能处理文字消息哦。")
        return
    if _is_start(text):
        a = db.get_assistant(ch["assistant_id"])
        nm = a["name"] if a else "助理"
        await tg.send_message(token, chat_id, f"已连接「{nm}」✅ 直接发消息给我，我会用你本机的 agent 来处理。")
        return
    key = f"{ch_id}:{chat_id}"
    if key in _busy:
        await tg.send_message(token, chat_id, "我还在处理上一条，稍等它完成～")
        return
    _busy.add(key)
    try:
        a = db.get_assistant(ch["assistant_id"])
        reply = await _run_agent(a, session_id, text) if a else "（助理不存在）"
        await tg.send_message(token, chat_id, reply)
    finally:
        _busy.discard(key)


async def _tg_poll_loop(ch_id: str) -> None:
    ch = db.get_channel(ch_id)
    if ch is None:
        return
    token = _tg_token(ch)
    offset = ch.get("update_offset") or None
    ok, res = await tg.get_me(token)
    log.info("渠道 %s Telegram 启动：%s", ch_id, res.get("username") if ok and isinstance(res, dict) else res)
    dok, dres = await tg.delete_webhook(token)
    if not dok:
        log.warning("渠道 %s deleteWebhook 失败：%s", ch_id, dres)
    while True:
        try:
            ok, res = await tg.get_updates(token, offset=offset, timeout=POLL_TIMEOUT)
            if not ok:
                log.warning("渠道 %s getUpdates 失败：%s", ch_id, res)
                await asyncio.sleep(_BACKOFF)
                continue
            updates = res or []
            if updates:
                offset = updates[-1]["update_id"] + 1
                db.set_channel_update_offset(ch_id, offset)
                for upd in updates:
                    await _handle_tg_update(ch_id, upd)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — 任何异常都不该让轮询退出
            log.exception("渠道 %s 轮询异常", ch_id)
            await asyncio.sleep(_BACKOFF)


# ---- poller 协调 --------------------------------------------------------

def _channel_should_run(ch: dict) -> bool:
    if not ch.get("enabled") or ch["type"] != "telegram" or not _tg_token(ch):
        return False
    a = db.get_assistant(ch["assistant_id"])
    return bool(a and a.get("enabled"))


def _is_running(ch_id: str) -> bool:
    t = _pollers.get(ch_id)
    return t is not None and not t.done()


async def _stop_poller(ch_id: str) -> None:
    _running_token.pop(ch_id, None)
    t = _pollers.pop(ch_id, None)
    if t is not None:
        t.cancel()
        try:
            await t
        except BaseException:  # noqa: BLE001
            pass


async def refresh() -> None:
    """协调 poller 集合与 DB 期望态：启新、停删、换 token 重启。启动 + 每次配置变更后调。"""
    want: dict[str, str] = {ch["id"]: _tg_token(ch) for ch in db.list_all_channels() if _channel_should_run(ch)}
    for cid in list(_pollers.keys()):
        if cid not in want or not _is_running(cid) or _running_token.get(cid) != want.get(cid):
            await _stop_poller(cid)
    for cid, tok in want.items():
        if not _is_running(cid):
            _running_token[cid] = tok
            _pollers[cid] = asyncio.create_task(_tg_poll_loop(cid))


async def stop() -> None:
    for cid in list(_pollers.keys()):
        await _stop_poller(cid)


# ---- App 面向（供路由）--------------------------------------------------

async def _bot_username(token: str) -> Optional[str]:
    if not token:
        return None
    hit = _bot_cache.get(token)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    ok, res = await tg.get_me(token)
    uname = res.get("username") if ok and isinstance(res, dict) else None
    _bot_cache[token] = (time.time(), uname)
    return uname


def channel_public(ch: dict) -> dict:
    """渠道对外结构：**绝不含 token 值**，只 has_token；含运行态与绑定 chat。"""
    return {
        "id": ch["id"],
        "assistant_id": ch["assistant_id"],
        "type": ch["type"],
        "enabled": ch["enabled"],
        "running": _is_running(ch["id"]),
        "has_token": bool(_tg_token(ch)),
        "chat_id": (ch.get("config", {}).get("chat_id") or "") if ch["type"] == "telegram" else "",
        "bound_chat_id": (db.first_chat_binding(ch["id"]) or {}).get("chat_id"),
    }


def assistant_public(a: dict, *, with_messages: bool = False) -> dict:
    """助理对外结构：配置 + 其渠道（脱敏）+ 可选 transcript。"""
    out = {
        "id": a["id"], "name": a["name"], "avatar": a.get("avatar") or "",
        "instruction": a.get("instruction") or "", "model": a.get("model") or "",
        "mode": a.get("mode") or "exec", "workspace": a.get("workspace") or "default",
        "experts": a.get("experts") or [], "skills": a.get("skills") or [], "connectors": a.get("connectors") or [],
        "enabled": a.get("enabled", True), "session_id": a.get("session_id"),
        "channels": [channel_public(ch) for ch in db.list_channels(a["id"])],
    }
    if with_messages:
        sid = a.get("session_id")
        out["messages"] = [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
            for m in (db.list_messages(sid) if sid else [])
        ]
    return out


async def say(assistant_id: str, text: str) -> dict:
    """从 App 驱动某助理（与其渠道共享会话）。"""
    a = db.get_assistant(assistant_id)
    if a is None:
        return {"error": "助理不存在"}
    text = (text or "").strip()
    session_id = ensure_assistant_session(a)
    if not text:
        return {"session_id": session_id, "reply": ""}
    reply = await _run_agent(a, session_id, text)
    return {"session_id": session_id, "reply": reply}


# ---- 兼容层：旧 /channels/telegram 端点（WB-077 前端在 S2 落地前仍可用）-------
# 映射到「主助理」（第一条）+ 其第一条 Telegram 渠道。

def _primary_assistant() -> Optional[dict]:
    al = db.list_assistants(LOCAL_USER_ID)
    return al[0] if al else None


def _primary_tg_channel(a: dict) -> Optional[dict]:
    for ch in db.list_channels(a["id"]):
        if ch["type"] == "telegram":
            return ch
    return None


async def compat_status() -> dict:
    a = _primary_assistant()
    if a is None:
        return {"configured": False, "enabled": False, "running": False, "connected": False,
                "bot_username": None, "bound_chat_id": None, "session_id": None,
                "name": "", "persona": "", "model": "", "enabled_override": None, "messages": []}
    ch = _primary_tg_channel(a)
    token = _tg_token(ch) if ch else ""
    uname = await _bot_username(token) if token else None
    running = _is_running(ch["id"]) if ch else False
    sid = a.get("session_id")
    messages = [
        {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
        for m in (db.list_messages(sid) if sid else [])
    ]
    return {
        "configured": bool(token),
        "enabled": bool(ch and ch["enabled"] and a["enabled"]),
        "running": running,
        "connected": bool(running and uname),
        "bot_username": uname,
        "bound_chat_id": (db.first_chat_binding(ch["id"]) or {}).get("chat_id") if ch else None,
        "session_id": sid,
        "name": a["name"], "persona": a.get("instruction") or "", "model": a.get("model") or "",
        "enabled_override": (1 if (ch and ch["enabled"]) else 0),
        "messages": messages,
    }


async def compat_config(patch: dict) -> dict:
    a = _primary_assistant()
    token = (patch.get("token") or "").strip()
    if a is None:
        a = db.create_assistant(owner_id=LOCAL_USER_ID, name=(patch.get("name") or "WorkBuddy 助理"))
    ch = _primary_tg_channel(a) or db.create_channel(assistant_id=a["id"], type="telegram", config={}, enabled=False)
    aupd: dict = {}
    if patch.get("name") is not None:
        aupd["name"] = patch["name"]
    if patch.get("persona") is not None:
        aupd["instruction"] = patch["persona"]
    if patch.get("model") is not None:
        aupd["model"] = patch["model"]
    if aupd:
        db.update_assistant(a["id"], **aupd)
    db.update_channel(ch["id"], config={"bot_token": token} if token else None, enabled=patch.get("enabled"))
    await refresh()
    return await compat_status()


def compat_unbind() -> None:
    a = _primary_assistant()
    if a is None:
        return
    ch = _primary_tg_channel(a)
    if ch:
        db.clear_channel_chats(ch["id"])


async def compat_say(text: str) -> dict:
    a = _primary_assistant()
    if a is None:
        return {"session_id": None, "reply": "（未配置助理）"}
    return await say(a["id"], text)
