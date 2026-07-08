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
from channels import email_api
from channels import telegram_api as tg
from storage import db
from storage.models import LOCAL_USER_ID

log = logging.getLogger("workbuddy.channels")

POLL_TIMEOUT = 30
EMAIL_POLL = 45       # 邮件轮询间隔（秒）
RUN_TIMEOUT = 300
_BACKOFF = 5

_pollers: dict[str, asyncio.Task] = {}       # channel_id -> poll task
_running_token: dict[str, str] = {}          # channel_id -> token the poller was started with
_busy: set[str] = set()                       # "channel_id:chat_id" 处理中，防同 chat 并发
_bot_cache: dict[str, tuple[float, Optional[str]]] = {}  # token -> (at, username)

# 渠道类型注册表：决定前端「新增渠道」能选什么、每类型可用与否（不造假——只 Telegram available）。
CHANNEL_TYPES = [
    {"type": "telegram", "label": "Telegram", "available": True},
    {"type": "email", "label": "邮件", "available": True},
    {"type": "wecom", "label": "企业微信", "available": False},
    {"type": "whatsapp", "label": "WhatsApp", "available": False},
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


# ---- Email 渠道：鉴权 + 路由 + 轮询（WB-096）---------------------------

def _authorize_email(ch: dict, from_addr: str, subject: str, body: str) -> Optional[str]:
    """按发件人白名单 + 可选暗号鉴权，返回会话 id（必要时配对绑定）；无权返回 None。
    邮件 From 可伪造 → 白名单是弱保护，暗号（subject/body 含 secret）加固。"""
    cfg = ch.get("config", {})
    secret = (cfg.get("secret") or "").strip()
    if secret and secret not in (subject or "") and secret not in (body or ""):
        return None  # 设了暗号但没带 → 忽略
    from_addr = (from_addr or "").strip().lower()
    if not from_addr:
        return None
    existing = db.get_chat_session(ch["id"], from_addr)
    if existing:
        return existing["session_id"]
    allow = [x.strip().lower() for x in (cfg.get("allow_from") or "").split(",") if x.strip()]
    if allow:
        if from_addr not in allow:
            return None
    else:
        if db.first_chat_binding(ch["id"]) is not None:
            return None  # 无白名单 → 首个发件人配对锁定
    a = db.get_assistant(ch["assistant_id"])
    if a is None:
        return None
    session_id = ensure_assistant_session(a)
    db.bind_chat(ch["id"], from_addr, session_id, a["owner_id"])
    log.info("邮件渠道 %s 绑定 %s → session=%s", ch["id"], from_addr, session_id)
    return session_id


async def _handle_email(ch_id: str, mail: dict) -> None:
    ch = db.get_channel(ch_id)
    if ch is None:
        return
    frm, subject, body = mail.get("from", ""), mail.get("subject", ""), mail.get("body", "")
    session_id = _authorize_email(ch, frm, subject, body)
    if session_id is None:
        log.info("邮件渠道 %s 忽略未授权/无暗号发件人 %s", ch_id, frm)
        return
    text = (f"【邮件主题】{subject}\n\n{body}" if subject else body).strip()
    if not text:
        return
    key = f"{ch_id}:{frm}"
    if key in _busy:
        return
    _busy.add(key)
    try:
        a = db.get_assistant(ch["assistant_id"])
        reply = await _run_agent(a, session_id, text) if a else "（助理不存在）"
        ok, info = await asyncio.to_thread(
            email_api.send_reply, ch["config"], frm, subject, reply, mail.get("message_id", "")
        )
        if not ok:
            log.warning("邮件渠道 %s 回信失败：%s", ch_id, info)
    finally:
        _busy.discard(key)


async def _email_poll_loop(ch_id: str) -> None:
    ch = db.get_channel(ch_id)
    if ch is None:
        return
    ok, info = await asyncio.to_thread(email_api.verify, ch["config"])
    log.info("邮件渠道 %s 启动（%s）：%s", ch_id, (ch["config"].get("username") or ""), info)
    while True:
        try:
            ch = db.get_channel(ch_id)  # 每轮取最新 config
            if ch is None:
                return
            mails = await asyncio.to_thread(email_api.fetch_unseen, ch["config"])
            for mail in mails:
                await _handle_email(ch_id, mail)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("邮件渠道 %s 轮询异常", ch_id)
        await asyncio.sleep(EMAIL_POLL)


# ---- poller 协调 --------------------------------------------------------

def _channel_should_run(ch: dict) -> bool:
    if not ch.get("enabled"):
        return False
    a = db.get_assistant(ch["assistant_id"])
    if not (a and a.get("enabled")):
        return False
    if ch["type"] == "telegram":
        return bool(_tg_token(ch))
    if ch["type"] == "email":
        c = ch.get("config", {})
        return bool((c.get("imap_host") or "").strip() and (c.get("username") or "").strip() and c.get("password"))
    return False


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


def _run_signature(ch: dict) -> str:
    """运行签名：变了就重启 poller（换 token / 换邮箱配置）。"""
    if ch["type"] == "telegram":
        return "tg:" + _tg_token(ch)
    if ch["type"] == "email":
        c = ch.get("config", {})
        return "em:" + "|".join(str(c.get(k, "")) for k in ("imap_host", "imap_port", "smtp_host", "smtp_port", "username", "password"))
    return ""


def _make_loop(ch: dict):
    return _email_poll_loop(ch["id"]) if ch["type"] == "email" else _tg_poll_loop(ch["id"])


async def refresh() -> None:
    """协调 poller 集合与 DB 期望态：启新、停删、配置变更重启。启动 + 每次配置变更后调。"""
    channels = {ch["id"]: ch for ch in db.list_all_channels() if _channel_should_run(ch)}
    want = {cid: _run_signature(ch) for cid, ch in channels.items()}
    for cid in list(_pollers.keys()):
        if cid not in want or not _is_running(cid) or _running_token.get(cid) != want.get(cid):
            await _stop_poller(cid)
    for cid, sig in want.items():
        if not _is_running(cid):
            _running_token[cid] = sig
            _pollers[cid] = asyncio.create_task(_make_loop(channels[cid]))


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
    """渠道对外结构，含运行态与绑定 chat。WB-093（用户显式决定）：token 在**本机**设置 UI 可见——
    后端只绑 localhost、DB 已 gitignore，token 不出本机；LLM API Key 不在此列（仍严格不进前端）。"""
    return {
        "id": ch["id"],
        "assistant_id": ch["assistant_id"],
        "type": ch["type"],
        "enabled": ch["enabled"],
        "running": _is_running(ch["id"]),
        "has_token": bool(_tg_token(ch)) if ch["type"] == "telegram" else bool((ch.get("config", {}).get("username") or "").strip()),
        "token": _tg_token(ch) if ch["type"] == "telegram" else "",
        "chat_id": (ch.get("config", {}).get("chat_id") or "") if ch["type"] == "telegram" else "",
        # 邮件渠道：回 config（本机可见，含账号/密码——延续 WB-093 本机可见）；telegram 不用 config 字段。
        "config": ch.get("config", {}) if ch["type"] == "email" else {},
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
