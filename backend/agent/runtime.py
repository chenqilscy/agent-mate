"""Agent Runtime — the self-authored thin loop (spec 5.3).

M2 shape: LLM output → parse tool_call → execute (real tools in the workspace
sandbox) → feed the result back → continue, turning every step into a typed SSE
event. Reasoning (when the model exposes it) streams as `think`; tool calls emit
`step`/`file_read`; writes emit `diff`; plans emit `todo`. The koda-style trace is
reproduced by REAL events, never a script.

The body stays small — messages management, tool dispatch, SSE emission, stop
signal, token accounting — so it upgrades (not rewrites) to PydanticAI later
(decision A.2). The SSE contract does not change when the loop grows up.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator

from agent import events
from agent.llm import LLMError, stream_chat
from agent.tools import get_tool, safe_run, tool_schemas
from config import settings
from storage import db
from storage.models import Session, User

SYSTEM_PROMPT = (
    "你是 WorkBuddy，一个运行在用户本机的智能职场助手。\n"
    "你可以使用提供的工具在工作区（沙箱目录）内操作：列目录(list_dir)、读文件(read_file)、"
    "写文件(write_file)、运行命令(run_command)、更新待办清单(update_plan)。\n"
    "工作方式：先思考再行动；多步任务先用 update_plan 拆解；需要时调用工具，逐步完成并核对结果。\n"
    "只在确有必要时使用工具——简单问答直接回答，不要空跑工具。所有路径都相对工作区根目录。\n"
    "最终回答使用 Markdown：用二级标题（##）分章节，善用列表、表格、代码块，让结构清晰。"
)

MAX_ROUNDS = 8

# Active runs → their stop signal, keyed by session id.
_stop_events: dict[str, asyncio.Event] = {}


def request_stop(session_id: str) -> bool:
    """Signal a running stream to stop. Returns True if a run was active."""
    ev = _stop_events.get(session_id)
    if ev is not None:
        ev.set()
        return True
    return False


def resolve_model(client_model: str | None) -> str:
    """Map the picker selection to a real provider model id.

    The picker labels custom entries as "Display:real-id"; we send the id after
    the colon so an explicit UI pick actually switches models. Builtin labels
    (Auto, GLM-5.2…) fall back to the authoritative .env LLM_MODEL — the picker is
    a UI affordance until multi-routing (litellm) lands (decision A.2).
    """
    if client_model and ":" in client_model:
        real = client_model.rsplit(":", 1)[-1].strip()
        if real:
            return real
    return settings.LLM_MODEL


def _approx_tokens(text: str) -> int:
    # Rough heuristic that works reasonably for mixed CN/EN text.
    return max(1, int(len(text) / 2.6))


def _trace_to_sse(item: dict[str, Any]) -> str:
    k = item.get("kind")
    if k == "think":
        return events.think(item["text"])
    if k == "step":
        return events.step(item["tool"], item["label"])
    if k == "file_read":
        return events.file_read(item["path"], item["range"])
    if k == "diff":
        return events.diff(item["op"], item["file"], item["add"], item["del"])
    if k == "todo":
        return events.todo(item["text"])
    return ""


def _build_llm_messages(session_id: str, new_user_text: str) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in db.list_messages(session_id):
        if m.role in ("user", "assistant") and m.content:
            msgs.append({"role": m.role, "content": m.content})
    msgs.append({"role": "user", "content": new_user_text})
    return msgs


def _usage_event(prompt_tokens: int, completion_tokens: int, schemas: list[dict[str, Any]]) -> str:
    used = prompt_tokens + completion_tokens
    pct = used / settings.CONTEXT_WINDOW * 100
    sys_tok = _approx_tokens(SYSTEM_PROMPT)
    tools_tok = _approx_tokens(json.dumps(schemas, ensure_ascii=False))
    detail = {
        "系统提示词": sys_tok,
        "工具及子智能体": tools_tok,
        "对话消息": max(0, prompt_tokens - sys_tok - tools_tok),
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

    Persists the user turn, runs the tool loop, persists the assistant turn with
    its full trace so history replay reproduces the trace.
    """
    session_id = session.id

    llm_messages = _build_llm_messages(session_id, user_text)
    db.add_message(session_id=session_id, role="user", content=user_text, actor=user.id)
    db.touch_session(session_id, status="running")

    stop = asyncio.Event()
    _stop_events[session_id] = stop
    yield events.status("running")

    schemas = tool_schemas()
    trace_items: list[dict[str, Any]] = []
    assistant_text = ""
    last_prompt = 0
    total_completion = 0
    stopped = False
    t0 = time.time()

    def record(item: dict[str, Any]) -> str:
        trace_items.append(item)
        return _trace_to_sse(item)

    try:
        for _round in range(MAX_ROUNDS):
            content_buf = ""
            reasoning_buf = ""
            tool_acc: dict[int, dict[str, Any]] = {}
            think_pending = True  # emit a "深度思考" marker before acting if no reasoning shown

            async for delta in stream_chat(llm_messages, model=resolve_model(model), tools=schemas):
                if stop.is_set():
                    stopped = True
                    break
                if delta.reasoning:
                    think_pending = False
                    reasoning_buf += delta.reasoning
                    while "\n" in reasoning_buf:
                        line, reasoning_buf = reasoning_buf.split("\n", 1)
                        line = line.strip()
                        if line:
                            yield record({"kind": "think", "text": line})
                if delta.content:
                    content_buf += delta.content
                    assistant_text += delta.content
                    yield events.text(delta.content)
                for tc in delta.tool_calls:
                    acc = tool_acc.setdefault(tc.index, {"id": None, "name": "", "args": ""})
                    if tc.id:
                        acc["id"] = tc.id
                    if tc.name:
                        acc["name"] = tc.name
                    acc["args"] += tc.arguments
                if delta.usage:
                    last_prompt = int(delta.usage.get("prompt_tokens") or last_prompt)
                    total_completion += int(delta.usage.get("completion_tokens") or 0)

            if stopped:
                break

            tail = reasoning_buf.strip()
            if tail:
                yield record({"kind": "think", "text": tail})

            if not tool_acc:
                break  # final answer produced, no tools → done

            # The model wants to act. Show a think marker if it gave no reasoning.
            if think_pending:
                yield record({"kind": "think", "text": "深度思考"})

            calls = []
            for idx in sorted(tool_acc):
                acc = tool_acc[idx]
                calls.append(
                    {
                        "id": acc["id"] or f"call_{idx}",
                        "type": "function",
                        "function": {"name": acc["name"], "arguments": acc["args"] or "{}"},
                    }
                )
            llm_messages.append({"role": "assistant", "content": content_buf or None, "tool_calls": calls})

            for call in calls:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool = get_tool(name)
                if tool and tool.pre:
                    pre = tool.pre(args)
                    if pre:
                        yield record(pre)
                outcome = safe_run(name, args)
                for it in outcome.trace:
                    yield record(it)
                llm_messages.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": outcome.text}
                )
            # loop again so the model can use the results
    except LLMError as e:
        yield events.error(str(e))
        db.touch_session(session_id, status="idle")
        _stop_events.pop(session_id, None)
        yield events.done()
        return
    except Exception as e:  # noqa: BLE001 — surface any hiccup to the UI
        yield events.error(f"执行出错：{e}")
        db.touch_session(session_id, status="idle")
        _stop_events.pop(session_id, None)
        yield events.done()
        return
    finally:
        _stop_events.pop(session_id, None)

    if last_prompt == 0:
        last_prompt = sum(_approx_tokens(str(m.get("content") or "")) for m in llm_messages)
    if total_completion == 0:
        total_completion = _approx_tokens(assistant_text)

    secs = max(1, round(time.time() - t0))
    message_id = None
    if assistant_text.strip() or trace_items:
        msg = db.add_message(
            session_id=session_id,
            role="assistant",
            content=assistant_text,
            actor="assistant",
            trace=trace_items,
            usage={"prompt": last_prompt, "completion": total_completion},
        )
        message_id = msg.id

    db.touch_session(session_id, status="done")

    yield _usage_event(last_prompt, total_completion, schemas)
    yield events.status("done", secs=secs)
    if stopped:
        yield events.text("\n\n_（已停止生成）_")
    yield events.done(message_id)
