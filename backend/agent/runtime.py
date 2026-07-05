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
from agent.experts import persona_for
from agent.llm import LLMError, stream_chat
from agent.mcp_client import call_mcp, mcp_schema, open_connectors
from agent.sandbox import current_root, project_root, use_root
from agent.skills import skill_def
from agent.tools import ASK_USER_SCHEMA, base_tools, run_tool
from config import settings
from storage import db
from storage.models import Session, User

SYSTEM_PROMPT = (
    "你是 WorkBuddy，一个运行在用户本机的智能职场助手。\n"
    "你可以使用提供的工具在工作区（沙箱目录）内操作：列目录(list_dir)、读文件(read_file)、"
    "写文件(write_file)、运行命令(run_command)、更新待办清单(update_plan)；"
    "遇到影响方向的关键决策时用 ask_user 向用户确认。\n"
    "工作方式：先思考再行动；多步任务先用 update_plan 拆解；需要时调用工具，逐步完成并核对结果。\n"
    "只在确有必要时使用工具——简单问答直接回答，不要空跑工具。所有路径都相对工作区根目录。\n"
    "最终回答使用 Markdown：用二级标题（##）分章节，善用列表、表格、代码块，让结构清晰。"
)

# Plan mode (spec 5.3): plan, don't execute. Confirm key decisions via ask_user.
PLAN_SYSTEM_PROMPT = (
    "你是 WorkBuddy，现在处于【计划模式】。\n"
    "只做规划，不做改动：可以用 list_dir / read_file 了解现状，用 update_plan 记录步骤，"
    "遇到影响方向的关键决策时**务必用 ask_user 向用户确认**（一次最多问 3 个选择题）。\n"
    "禁止调用 write_file / run_command——这一步只产出方案，不落地。\n"
    "先探索与澄清，再输出一份清晰、可执行的实施计划（Markdown：用二级标题分章节、分步骤、标注关键取舍）。"
)

MAX_ROUNDS = 12

# Active runs → their stop signal, keyed by session id.
_stop_events: dict[str, asyncio.Event] = {}

# Suspended ask_user calls → their answer channel, keyed by session id.
_answers: dict[str, dict[str, Any]] = {}


def request_stop(session_id: str) -> bool:
    """Signal a running stream to stop. Returns True if a run was active."""
    ev = _stop_events.get(session_id)
    if ev is not None:
        ev.set()
    # Also wake a suspended ask_user so the stream can unwind.
    pending = _answers.get(session_id)
    if pending is not None:
        pending["ev"].set()
    return ev is not None or pending is not None


def submit_answers(session_id: str, answers: list[str]) -> bool:
    """Deliver the user's ask_user answers and wake the suspended agent."""
    pending = _answers.get(session_id)
    if pending is None:
        return False
    pending["answers"] = answers
    pending["ev"].set()
    return True


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
    if k == "qa":
        return events.qa_summary(item["qa"])
    return ""


def _build_llm_messages(session_id: str, new_user_text: str, system_prompt: str) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for m in db.list_messages(session_id):
        if m.role in ("user", "assistant") and m.content:
            msgs.append({"role": m.role, "content": m.content})
    msgs.append({"role": "user", "content": new_user_text})
    return msgs


def _usage_event(prompt_tokens: int, completion_tokens: int, schemas: list[dict[str, Any]], system_prompt: str) -> str:
    used = prompt_tokens + completion_tokens
    pct = used / settings.CONTEXT_WINDOW * 100
    sys_tok = _approx_tokens(system_prompt)
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
    plan: bool = False,
    ask: bool = False,
    experts: list[str] | None = None,
    skills: list[str] | None = None,
    connectors: list[str] | None = None,
    refs: list[dict] | None = None,
) -> AsyncIterator[str]:
    """Async generator of SSE strings for POST /api/chat.

    Persists the user turn, runs the tool loop, persists the assistant turn with
    its full trace so history replay reproduces the trace. Plan mode plans only
    (read-only tools + ask_user); Ask mode answers only (no tools). The loadout
    (experts/skills/connectors) is the project's plus any picked from the ＋ menu.
    """
    session_id = session.id
    system_prompt = PLAN_SYSTEM_PROMPT if plan else SYSTEM_PROMPT
    if ask:
        system_prompt += "\n\n# 仅问答模式\n只回答用户的问题，不要调用任何工具、不执行任何操作。"

    # Per-project workspace (§11.2): this run's tools operate in the project's own
    # checkout (or the shared default for ad-hoc chats).
    use_root(project_root(session.project_id))

    def _dedup(seq: list[str]) -> list[str]:
        return list(dict.fromkeys(seq))

    # Loadout = the project's experts/skills/connectors ∪ what the ＋ menu picked.
    proj_experts, proj_skills, proj_connectors = [], [], []
    if session.project_id:
        project = db.get_project(session.project_id)
        if project:
            if project.instruction.strip():
                system_prompt += f"\n\n# 项目背景与规范（项目：{project.name}）\n{project.instruction.strip()}"
            proj_experts, proj_skills, proj_connectors = project.experts, project.skills, project.connectors

    active_experts = _dedup(proj_experts + (experts or []))
    active_skills = _dedup(proj_skills + (skills or []))
    active_connectors = _dedup(proj_connectors + (connectors or []))

    skill_tools = []
    if active_experts:
        system_prompt += "\n\n# 专家人格（请综合以下专长作答）\n" + "\n".join(
            f"- {persona_for(n)}" for n in active_experts
        )
    if active_skills:
        lines = []
        for name in active_skills:
            instr, tools = skill_def(name)
            lines.append(f"- {name}：{instr}")
            skill_tools.extend(tools)
        system_prompt += "\n\n# 已启用技能\n" + "\n".join(lines)

    # Attached / referenced files (＋ menu) are prepended to THIS turn's LLM input
    # only — the persisted user message stays clean, so the bubble shows just the
    # typed text and history replay doesn't re-feed large file bodies.
    llm_user_text = user_text
    if refs:
        blocks = []
        for r in refs:
            name = str(r.get("name", "file"))
            body = str(r.get("content", ""))[:8000]
            blocks.append(f"【参考文件 {name}】\n{body}")
        llm_user_text = "\n\n".join(blocks) + "\n\n---\n\n" + user_text

    llm_messages = _build_llm_messages(session_id, llm_user_text, system_prompt)
    db.add_message(session_id=session_id, role="user", content=user_text, actor=user.id)
    db.touch_session(session_id, status="running")

    stop = asyncio.Event()
    _stop_events[session_id] = stop
    yield events.status("running")

    # Active toolset. Ask mode = no tools (pure Q&A). Otherwise base (plan-filtered)
    # tools + skill tools + connector (MCP) tools; connectors spawn their stdio MCP
    # servers now and are closed in `finally`.
    tools_list = [] if ask else base_tools(plan) + skill_tools
    active_tools = {t.name: t for t in tools_list}
    mcp_tools, mcp_stack = [], None
    if active_connectors and not plan and not ask:
        mcp_tools, mcp_stack = await open_connectors(
            active_connectors, env={"WORKBUDDY_NOTES_DIR": str(current_root())}
        )
    mcp_by_name = {t.qualified: t for t in mcp_tools}
    schemas = (
        [t.schema() for t in tools_list]
        + [mcp_schema(t) for t in mcp_tools]
        + ([] if ask else [ASK_USER_SCHEMA])
    )
    trace_items: list[dict[str, Any]] = []
    assistant_text = ""
    last_prompt = 0
    total_completion = 0
    stopped = False
    t0 = time.time()

    def record(item: dict[str, Any]) -> str:
        trace_items.append(item)
        return _trace_to_sse(item)

    # Show the loadout so the persona / skills / connectors that shaped this run
    # are visible.
    connector_names = sorted({t.connector for t in mcp_tools})
    if active_experts or active_skills or connector_names:
        parts = []
        if active_experts:
            parts.append("专家 " + "、".join(active_experts))
        if active_skills:
            parts.append("技能 " + "、".join(active_skills))
        if connector_names:
            parts.append("连接器 " + "、".join(connector_names))
        yield record({"kind": "step", "tool": "loadout", "label": "已加载 · " + " · ".join(parts)})

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

                if name == "ask_user":
                    # Suspend the agent until the user answers (spec 5.3). The
                    # /answer endpoint sets our event and wakes us on the SAME
                    # open SSE stream. stop also wakes us (via request_stop).
                    questions = args.get("questions") or []
                    ev = asyncio.Event()
                    _answers[session_id] = {"ev": ev, "answers": None}
                    yield events.ask_user(questions)
                    db.touch_session(session_id, status="waiting")
                    await ev.wait()
                    pending = _answers.pop(session_id, None)
                    answers = (pending or {}).get("answers")
                    db.touch_session(session_id, status="running")
                    if stop.is_set() or answers is None:
                        stopped = True
                        llm_messages.append({"role": "tool", "tool_call_id": call["id"], "content": "用户已跳过或取消本次提问。"})
                        break
                    qa = [
                        {"q": q.get("q", ""), "a": answers[i] if i < len(answers) else ""}
                        for i, q in enumerate(questions)
                    ]
                    yield record({"kind": "qa", "qa": qa})
                    result = "用户的选择：\n" + "\n".join(f"- {x['q']} → {x['a']}" for x in qa)
                    llm_messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
                    continue

                if name in mcp_by_name:
                    mt = mcp_by_name[name]
                    yield record({"kind": "step", "tool": mt.orig, "label": f"[{mt.connector}] {mt.orig}"})
                    result = await call_mcp(mt, args)
                    llm_messages.append({"role": "tool", "tool_call_id": call["id"], "content": result[:6000]})
                    continue

                tool = active_tools.get(name)
                if tool is None:
                    llm_messages.append({"role": "tool", "tool_call_id": call["id"], "content": f"未知工具：{name}"})
                    continue
                if tool.pre:
                    pre = tool.pre(args)
                    if pre:
                        yield record(pre)
                outcome = run_tool(tool, args)
                for it in outcome.trace:
                    yield record(it)
                llm_messages.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": outcome.text}
                )
            if stopped:
                break
            # loop again so the model can use the results
    except LLMError as e:
        yield events.error(str(e))
        db.touch_session(session_id, status="idle")
        _stop_events.pop(session_id, None)
        _answers.pop(session_id, None)
        yield events.done()
        return
    except Exception as e:  # noqa: BLE001 — surface any hiccup to the UI
        yield events.error(f"执行出错：{e}")
        db.touch_session(session_id, status="idle")
        _stop_events.pop(session_id, None)
        _answers.pop(session_id, None)
        yield events.done()
        return
    finally:
        _stop_events.pop(session_id, None)
        _answers.pop(session_id, None)
        if mcp_stack is not None:
            try:
                await mcp_stack.aclose()  # terminate connector MCP servers
            except Exception:  # noqa: BLE001
                pass

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

    yield _usage_event(last_prompt, total_completion, schemas, system_prompt)
    yield events.status("done", secs=secs)
    if stopped:
        yield events.text("\n\n_（已停止生成）_")
    yield events.done(message_id)
