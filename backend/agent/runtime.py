"""Agent Runtime — the self-authored thin loop (spec 5.3).

MVP shape: LLM output → (future: parse tool_call → execute → feed back) → continue,
turning every step into a typed SSE event. For M1 the loop streams real assistant
prose token-by-token with stop-signal support and token accounting. Tools, trace
events (think/step/diff/todo) and ask_user land in M2/M4 on this same skeleton —
the SSE contract does not change when the loop grows up (→ PydanticAI, decision A.2).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator

from agent import events
from agent.llm import Delta, LLMError, stream_chat
from config import settings
from storage import db
from storage.models import Session, User

SYSTEM_PROMPT = (
    "你是 WorkBuddy，一个运行在用户本机的智能职场助手。"
    "用简洁、专业、友好的中文回答。"
    "涉及步骤、对比或代码时优先使用 Markdown（标题、列表、表格、代码块）让结构清晰。"
)

# Active runs → their stop signal, keyed by session id.
_stop_events: dict[str, asyncio.Event] = {}


def request_stop(session_id: str) -> bool:
    """Signal a running stream to stop. Returns True if a run was active."""
    ev = _stop_events.get(session_id)
    if ev is not None:
        ev.set()
        return True
    return False


def _approx_tokens(text: str) -> int:
    # Rough heuristic that works reasonably for mixed CN/EN text.
    return max(1, int(len(text) / 2.6))


def _build_llm_messages(session_id: str, new_user_text: str) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in db.list_messages(session_id):
        if m.role in ("user", "assistant"):
            msgs.append({"role": m.role, "content": m.content})
    msgs.append({"role": "user", "content": new_user_text})
    return msgs


def resolve_model(client_model: str | None) -> str:
    """Map the picker selection to a real provider model id.

    The picker labels custom entries as "Display:real-id" (e.g.
    "DeepSeek-V4 Pro:deepseek-v4-pro"). We send the id after the colon so an
    explicit UI pick actually switches models. Builtin labels (Auto, GLM-5.2…)
    have no colon and fall back to the authoritative .env LLM_MODEL — the picker
    is a UI affordance until multi-routing (litellm) lands in M2 (decision A.2).
    """
    if client_model and ":" in client_model:
        real = client_model.rsplit(":", 1)[-1].strip()
        if real:
            return real
    return settings.LLM_MODEL


def _usage_event(prompt_tokens: int, completion_tokens: int) -> str:
    used = prompt_tokens + completion_tokens
    pct = used / settings.CONTEXT_WINDOW * 100
    detail = {
        "系统提示词": _approx_tokens(SYSTEM_PROMPT),
        "对话消息": max(0, used - _approx_tokens(SYSTEM_PROMPT)),
        "工具及子智能体": 0,
        "连接器及MCP": 0,
        "技能": 0,
    }
    return events.usage(pct=pct, used=used, detail=detail)


async def run_chat(
    session: Session,
    user: User,
    user_text: str,
    *,
    model: str | None = None,
) -> AsyncIterator[str]:
    """Async generator of SSE strings for POST /api/chat.

    Persists the user turn, streams the assistant turn, persists the result.
    """
    session_id = session.id

    # Persist the user's message and build the LLM context BEFORE registering
    # the new turn so history does not include the message twice.
    llm_messages = _build_llm_messages(session_id, user_text)
    db.add_message(
        session_id=session_id,
        role="user",
        content=user_text,
        actor=user.id,
    )
    db.touch_session(session_id, status="running")

    stop = asyncio.Event()
    _stop_events[session_id] = stop

    yield events.status("running")

    t0 = time.time()
    assistant_text = ""
    prompt_tokens = 0
    completion_tokens = 0
    stopped = False

    try:
        async for delta in stream_chat(llm_messages, model=resolve_model(model)):
            if stop.is_set():
                stopped = True
                break
            if delta.content:
                assistant_text += delta.content
                yield events.text(delta.content)
            if delta.usage:
                prompt_tokens = int(delta.usage.get("prompt_tokens") or 0)
                completion_tokens = int(delta.usage.get("completion_tokens") or 0)
    except LLMError as e:
        yield events.error(str(e))
        db.touch_session(session_id, status="idle")
        _stop_events.pop(session_id, None)
        yield events.done()
        return
    except asyncio.CancelledError:
        stopped = True
    except Exception as e:  # noqa: BLE001 — surface any provider hiccup to the UI
        yield events.error(f"执行出错：{e}")
        db.touch_session(session_id, status="idle")
        _stop_events.pop(session_id, None)
        yield events.done()
        return
    finally:
        _stop_events.pop(session_id, None)

    # Fall back to an estimate when the provider did not report usage.
    if prompt_tokens == 0:
        prompt_tokens = sum(_approx_tokens(m["content"]) for m in llm_messages)
    if completion_tokens == 0:
        completion_tokens = _approx_tokens(assistant_text)

    secs = max(1, round(time.time() - t0))

    if assistant_text.strip():
        msg = db.add_message(
            session_id=session_id,
            role="assistant",
            content=assistant_text,
            actor="assistant",
            usage={"prompt": prompt_tokens, "completion": completion_tokens},
        )
        message_id = msg.id
    else:
        message_id = None

    db.touch_session(session_id, status="done")

    yield _usage_event(prompt_tokens, completion_tokens)
    yield events.status("done", secs=secs)
    if stopped:
        yield events.text("\n\n_（已停止生成）_")
    yield events.done(message_id)
