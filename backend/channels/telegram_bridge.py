"""Telegram 助理渠道 —— 长轮询桥接（WB-072）。

Local-first：后端跑在 localhost，收不到 Telegram webhook 回调（没有公网地址），所以
用 getUpdates **长轮询**主动拉——和 Telegram 连接器已在用的出站调用一个路子，后台任务
形态与 agent/scheduler.py 完全同构。

每个被授权的 Telegram chat 映射到**一个长期 WorkBuddy 会话**（kind=assistant），对话有
连续性。收到的文本驱动**真实** agent 工具循环（runtime.run_chat）headless 执行，再把
助手回复发回。

安全：白名单 + /start 配对。只有绑定的那个 chat 能驱动 agent（它能读写工作区沙箱、跑命令）。
默认关：仅当 TELEGRAM_BOT_TOKEN 已配 **且** TELEGRAM_ASSISTANT=1 时才由 main.py 启动。
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from agent import runtime
from channels import telegram_api as tg
from config import settings
from storage import db
from storage.models import LOCAL_USER_ID

log = logging.getLogger("workbuddy.telegram")

CHANNEL = "telegram"
POLL_TIMEOUT = 30            # 长轮询挂起秒数（服务器端 hold 住请求）
RUN_TIMEOUT = 300           # 单条消息驱动的 agent 运行超时（5 分钟）
_BACKOFF = 5                # 出错/网络抖动后的退避秒数

_task: Optional[asyncio.Task] = None
_busy: set[str] = set()      # 正在处理中的 chat_id —— 同一 chat 串行，不并发驱动同一会话


def _owner_id() -> str:
    # 桥接是机器级后台服务：会话归本机固定本地用户（local-first）。Telegram chat 是「人」，
    # WorkBuddy 会话 owner 是「本机主人」。
    return LOCAL_USER_ID


def ensure_assistant_session(owner_id: str) -> str:
    """返回该 owner 的助理会话 id，没有则创建。App 助理页与 Telegram 共用同一条会话
    （WB-072 Slice 2），两个入口写同一份 transcript。"""
    existing = db.get_assistant_session(owner_id)
    if existing:
        return existing.id
    session = db.create_session(owner_id=owner_id, title="Telegram 助理", kind="assistant")
    return session.id


def _authorize_and_get_session(chat_id: str) -> Optional[str]:
    """判定该 chat 是否有权，并返回其（必要时新建并绑定的）会话 id；无权返回 None。

    策略：白名单 + /start 配对。
    - 已有绑定 → 已授权，直接返回其 session。
    - .env 设了 TELEGRAM_CHAT_ID → 只认它；相符则首次接触即建会话绑定，不符则拒。
    - 未设 → 首个接触的 chat 配对为主人并锁定；此后其它 chat 一律拒。
    """
    existing = db.get_channel_session(CHANNEL, chat_id)
    if existing:
        return existing["session_id"]

    env_chat = tg.default_chat()
    if env_chat:
        if str(chat_id) != env_chat:
            return None  # 固定了主人，且不是这个 chat
    else:
        if db.first_channel_binding(CHANNEL) is not None:
            return None  # 已配对给别人，锁定

    session_id = ensure_assistant_session(_owner_id())  # 复用 App/Telegram 共享的助理会话
    db.bind_channel(CHANNEL, str(chat_id), session_id, _owner_id())
    log.info("Telegram 助理已绑定 chat_id=%s → session=%s", chat_id, session_id)
    return session_id


def _is_start(text: str) -> bool:
    t = (text or "").strip()
    return t == "/start" or t.startswith("/start@") or t.startswith("/start ")


async def _run_agent(session_id: str, text: str) -> str:
    """在既有会话里 headless 驱动一轮 agent，返回本轮新产生的助手回复文本。"""
    user = db.get_user(_owner_id())
    session = db.get_session(session_id)
    if user is None or session is None:
        return "（本机用户或会话缺失，无法处理。）"

    before = {m.id for m in db.list_messages(session_id)}

    async def _drive() -> None:
        async for _ in runtime.run_chat(session, user, text):
            pass

    try:
        await asyncio.wait_for(_drive(), timeout=RUN_TIMEOUT)
    except asyncio.TimeoutError:
        return "（处理超时，请把任务拆小一点再试。）"
    except Exception as e:  # noqa: BLE001 — 单条消息失败不该杀掉桥接
        log.exception("Telegram 驱动 agent 失败")
        return f"（处理失败：{str(e)[:300]}）"

    # 取本轮新出现的最后一条助手消息（run_chat 已把它持久化）。
    for m in reversed(db.list_messages(session_id)):
        if m.role == "assistant" and m.id not in before and (m.content or "").strip():
            return m.content
    return "（助手这次没有产生文本回复。）"


async def _handle_message(chat_id: str, text: str) -> None:
    session_id = _authorize_and_get_session(chat_id)
    if session_id is None:
        log.info("忽略未授权 chat_id=%s", chat_id)
        return

    # /start：仅确认连通，不把字面量 "/start" 丢给 agent。
    if _is_start(text):
        await tg.send_message(
            chat_id,
            "已连接 WorkBuddy 助理 ✅ 直接发消息给我，我会用你本机的 agent 来处理。",
        )
        return

    if chat_id in _busy:
        await tg.send_message(chat_id, "我还在处理上一条，稍等它完成～")
        return
    _busy.add(chat_id)
    try:
        reply = await _run_agent(session_id, text)
        await tg.send_message(chat_id, reply)
    finally:
        _busy.discard(chat_id)


async def _handle_update(upd: dict) -> None:
    msg = upd.get("message") or upd.get("edited_message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    text = msg.get("text")
    if chat_id is None:
        return
    if not text:
        # 非文本消息（图片/贴纸等）暂不支持，给个明确提示而不是静默。
        if _authorize_and_get_session(str(chat_id)) is not None:
            await tg.send_message(chat_id, "目前我只能处理文字消息哦。")
        return
    await _handle_message(str(chat_id), text)


async def _loop() -> None:
    # 从上次游标续拉（重启不重复驱动 agent）。首次启动 offset=None 会取待处理 backlog；
    # 处理前先推进并持久化游标（at-most-once：宁可硬崩溃丢一条，也不重复执行副作用）。
    offset = db.get_channel_offset(CHANNEL)
    ok, res = await tg.get_me()
    if ok and isinstance(res, dict):
        log.info("Telegram 助理桥接已启动：@%s", res.get("username") or res.get("id"))
    else:
        log.warning("Telegram getMe 失败（token 可能无效）：%s", res)
    # 长轮询与 webhook 互斥：若该 bot 之前设过 webhook，getUpdates 会 409。启动先删一次。
    dok, dres = await tg.delete_webhook()
    if not dok:
        log.warning("deleteWebhook 失败（如已有 webhook 未清，长轮询可能 409）：%s", dres)

    while True:
        try:
            ok, res = await tg.get_updates(offset=offset, timeout=POLL_TIMEOUT)
            if not ok:
                log.warning("getUpdates 失败：%s", res)
                await asyncio.sleep(_BACKOFF)
                continue
            updates = res or []
            if updates:
                # updates 按 update_id 升序；先确认游标再逐条处理。
                offset = updates[-1]["update_id"] + 1
                db.set_channel_offset(CHANNEL, offset)
                for upd in updates:
                    await _handle_update(upd)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — 任何异常都不该让轮询循环退出
            log.exception("Telegram 轮询循环异常")
            await asyncio.sleep(_BACKOFF)


# ---- App 助理页接口（Slice 2）------------------------------------------------
# 助理页与 Telegram 共用同一助理会话；这里给前端提供「渠道状态 + 从 App 驱动同一助手」。

_bot_cache: dict = {"username": None, "at": 0.0}  # getMe 结果缓存，避免每次状态轮询都打 API


async def _bot_username() -> Optional[str]:
    if not tg.token():
        return None
    now = time.time()
    if _bot_cache["username"] and now - _bot_cache["at"] < 60:
        return _bot_cache["username"]
    ok, res = await tg.get_me()
    if ok and isinstance(res, dict):
        _bot_cache["username"] = res.get("username")
        _bot_cache["at"] = now
        return _bot_cache["username"]
    return None


async def status() -> dict:
    """渠道状态给前端助理页。不创建会话（仅打开视图不该冒出空会话）。"""
    configured = bool(tg.token())
    enabled = settings.telegram_assistant_enabled
    binding = db.first_channel_binding(CHANNEL)
    session = db.get_assistant_session(_owner_id())
    uname = await _bot_username() if configured else None
    return {
        "configured": configured,
        "enabled": enabled,
        "connected": bool(enabled and uname),
        "bot_username": uname,
        "bound_chat_id": binding["chat_id"] if binding else None,
        "session_id": session.id if session else None,
    }


async def say(text: str) -> dict:
    """从 App 助理页驱动同一助手（与 Telegram 共享会话）。返回本轮回复文本。"""
    text = (text or "").strip()
    session_id = ensure_assistant_session(_owner_id())
    if not text:
        return {"session_id": session_id, "reply": ""}
    reply = await _run_agent(session_id, text)
    return {"session_id": session_id, "reply": reply}


async def start() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())


async def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except BaseException:  # noqa: BLE001 — 吞掉关停时的 CancelledError
            pass
        _task = None
