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
from contextlib import aclosing
from datetime import datetime, timezone
import json
import time
from typing import Any, AsyncIterator

from agent import events
from agent import agent_settings, memory, security, skills_store, telemetry, weknora
from agent.experts import expert_for
from agent.personalization import build_personalization_prompt
from agent.llm import LLMError, stream_chat
from agent.mcp_client import call_mcp, mcp_schema, open_connectors
from agent.sandbox import current_root, resolve_in_sandbox, use_root, workspace_root
from agent.skill_resources import RESOURCE_TOOLS, has_active_resources, set_active_skill_resources
from agent.skills import canonical_skill_keys, skill_display_name, skill_runtime_def
from agent.tool_execution import (
    ToolExecutionCancelled, ToolExecutionTimeout, execute_async_call, execute_tool,
)
from agent.tools import (
    ASK_USER_SCHEMA,
    base_tools,
    knowledge_add,
    knowledge_retrieve,
    plan_filter,
    set_knowledge_context,
    set_work_context,
    ToolOutcome,
    work_item_tools,
)
from config import settings
import server_client
from storage import db, provider_seed
from storage.models import Session, User


class RuntimeBudgetExceeded(RuntimeError):
    """Raised before another tool/LLM round once the configured token cap is reached."""

SYSTEM_PROMPT = (
    "你是 AgentMate，一个运行在用户本机的智能工作伙伴。\n"
    "你可以使用提供的工具在工作区（沙箱目录）内操作：列目录(list_dir)、读文件(read_file)、"
    "写文件(write_file)、生成并校验 DOCX/XLSX/PPTX/PDF、使用浏览器导航/读取/安全交互、"
    "运行命令(run_command)、更新待办清单(update_plan)；"
    "遇到影响方向的关键决策时用 ask_user 向用户确认。\n"
    "工作方式：先思考再行动；多步任务先用 update_plan 拆解；需要时调用工具，逐步完成并核对结果。\n"
    "只在确有必要时使用工具——简单问答直接回答，不要空跑工具。所有路径都相对工作区根目录。\n"
    "最终回答使用 Markdown：用二级标题（##）分章节，善用列表、表格、代码块，让结构清晰。"
)

# Plan mode (spec 5.3): plan, don't execute. Confirm key decisions via ask_user.
PLAN_SYSTEM_PROMPT = (
    "你是 AgentMate，现在处于【计划模式】。\n"
    "只做规划，不做改动：可以用 list_dir / read_file 了解现状，用 update_plan 记录步骤，"
    "遇到影响方向的关键决策时**务必用 ask_user 向用户确认**（一次最多问 3 个选择题）。\n"
    "禁止调用 write_file / run_command——这一步只产出方案，不落地。\n"
    "先探索与澄清，再输出一份清晰、可执行的实施计划（Markdown：用二级标题分章节、分步骤、标注关键取舍）。"
)

MAX_ROUNDS = 12

# Attached-refs limits (WB-010): a single turn can't blow up context/memory.
# WB-025: raised so a mid-size document actually goes through — front-end
# EFFECTIVE_REF_LIMIT (Composer.tsx) mirrors MAX_REF_BODY, and truncation is now
# surfaced (chip「已截断」+ the injected marker below) instead of silent.
MAX_REFS = 10                # at most this many referenced files per turn
MAX_REF_BODY = 1_000_000     # chars kept from each ref's body (== front EFFECTIVE_REF_LIMIT)
MAX_REFS_TOTAL = 4_000_000   # chars across all ref bodies combined
MAX_REF_NAME = 120           # chars kept from a ref's display name

# Active runs are keyed by a per-run id, not session id (WB-015): two runs on the
# same session (e.g. a second message while one is suspended on ask_user) must not
# clobber each other's stop/answer channels. `_session_runs` maps a session to its
# live run ids so the /stop and /answer endpoints (which only know the session id)
# can still route to the right run.
_stop_events: dict[str, asyncio.Event] = {}          # run_id → stop event
_answers: dict[str, dict[str, Any]] = {}             # run_id → answer channel
_session_runs: dict[str, set[str]] = {}              # session_id → {run_id}


def _register_run(session_id: str, run_id: str, stop: asyncio.Event) -> None:
    _stop_events[run_id] = stop
    _session_runs.setdefault(session_id, set()).add(run_id)


def _unregister_run(session_id: str, run_id: str) -> None:
    _stop_events.pop(run_id, None)
    _answers.pop(run_id, None)
    runs = _session_runs.get(session_id)
    if runs is not None:
        runs.discard(run_id)
        if not runs:
            _session_runs.pop(session_id, None)


def request_stop(session_id: str) -> bool:
    """Signal a session's running stream(s) to stop. Returns True if any was active."""
    hit = False
    for run_id in list(_session_runs.get(session_id, set())):
        ev = _stop_events.get(run_id)
        if ev is not None:
            ev.set()
            hit = True
        # Also wake a suspended ask_user so the stream can unwind.
        pending = _answers.get(run_id)
        if pending is not None:
            pending["ev"].set()
            hit = True
    return hit


def submit_answers(session_id: str, answers: list[str]) -> bool:
    """Deliver ask_user answers to whichever of the session's runs is waiting."""
    for run_id in list(_session_runs.get(session_id, set())):
        pending = _answers.get(run_id)
        if pending is not None:
            pending["answers"] = answers
            pending["ev"].set()
            return True
    return False


def resolve_model_config(
    owner_id: str, client_model: str | None
) -> tuple[str, str | None, str | None, str]:
    """Map the picker selection to a concrete (model_id, api_base, api_key, chat_path).

    Resolution order (WB-136: the default no longer reads .env — it is a user choice):
      0. Empty selection「跟随默认」→ the owner's DB default model (set in「模型管理」).
         No default configured → raise, honestly (no silent .env fallback).
      1. Built-in provider pick `@{provider}:{model}` (WB-128) → the provider's
         base_url/chat_path (provider_seed) + the owner's key for that provider.
      2. DB custom model matched by display name (WB-124) → its own base/key
         (blank base/key intentionally means「用后端 .env 凭据」, that model's own design).
      3. Legacy "Display:real-id" custom labels → the id after the colon.
      4. Anything else (unknown provider / key revoked / model deleted) → raise,
         so the user picks a valid default instead of silently running .env's model.
    api_base/api_key None means "use the .env default" (see llm.stream_chat) — only
    custom/legacy models opt into that; the account default resolves to a real ref.
    """
    default_path = provider_seed.DEFAULT_CHAT_PATH
    if not client_model:
        client_model = db.get_default_model(owner_id)
        if not client_model:
            raise LLMError(
                "还没有设置默认模型：请在「模型管理」里给某个模型点「设为默认」，"
                "或直接在模型菜单里选一个模型。"
            )
    if client_model.startswith("@") and ":" in client_model:
        pid, _, mid = client_model[1:].partition(":")
        prov = provider_seed.PROVIDERS_BY_ID.get(pid)
        key = db.get_provider_key(owner_id, pid) if prov else None
        if prov and mid and key:
            # 有效 base/path = 用户覆盖（WB-129）∨ 预置默认。
            cfg = db.get_provider_config(owner_id, pid) or {}
            base = cfg.get("base_url") or prov["base_url"]
            path = cfg.get("chat_path") or prov.get("chat_path") or default_path
            return mid, base, key, path
        # provider unknown / model empty / no key → 落到下方诚实报错
    else:
        row = db.get_custom_model_by_name(owner_id, client_model, include_secrets=True)
        if row and row.get("model_id"):
            return row["model_id"], row.get("api_base"), row.get("api_key"), default_path
        real = parse_legacy_model_id(client_model)
        if real:
            return real, None, None, default_path
    raise LLMError(
        f"模型「{client_model}」当前不可用（可能厂商 Key 已撤销、或模型已删除）。"
        "请在「模型管理」里重新选择默认模型，或在模型菜单里换一个。"
    )


def parse_legacy_model_id(selection: str) -> str | None:
    """Parse old `Display:real-id` values without truncating colon-bearing IDs."""
    label, sep, model_id = selection.partition(":")
    if not sep:
        return None
    # `vendor/model:variant` is already a bare provider model id. A legacy label
    # precedes the first colon and therefore does not contain the provider path.
    if "/" in label:
        return selection.strip() or None
    return model_id.strip() or None


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
    if k == "artifact":
        return events.artifact(
            item["name"], item["size"], item["path"], artifact_id=item["id"],
            run_id=item["run_id"], sha256=item["sha256"], mime_type=item["mime_type"],
            acceptance_status=item.get("acceptance_status", "pending"),
        )
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
    knowledge_ids: list[str] | None = None,
    refs: list[dict] | None = None,
    system_extra: str | None = None,
    workspace: str | None = None,
    idempotency_key: str | None = None,
    retry_of: str | None = None,
    max_total_tokens: int = 0,
    max_output_tokens: int = 0,
) -> AsyncIterator[str]:
    """Trace one user turn, delegating the unchanged SSE loop to the inner runner."""
    # Server-authoritative mode contract (WB-272): old/direct clients may still
    # submit both flags. Ask is the stricter mode (zero tools), so it wins.
    plan, ask = normalize_modes(plan, ask)
    mode = "ask" if ask else ("plan" if plan else "exec")
    with telemetry.chat_observation(
        session_id=session.id,
        user_id=user.id,
        user_text=user_text,
        project_id=session.project_id,
        mode=mode,
        selected_model=model,
        refs_count=len(refs or []),
        skills_count=len(skills or []),
        connectors_count=len(connectors or []),
    ) as chat_trace:
        async for chunk in _run_chat_inner(
            session, user, user_text,
            model=model, plan=plan, ask=ask,
            experts=experts, skills=skills, connectors=connectors,
            knowledge_ids=knowledge_ids, refs=refs,
            system_extra=system_extra, workspace=workspace,
            idempotency_key=idempotency_key, retry_of=retry_of,
            max_total_tokens=max_total_tokens,
            max_output_tokens=max_output_tokens,
            chat_trace=chat_trace,
        ):
            yield chunk


def normalize_modes(plan: bool, ask: bool) -> tuple[bool, bool]:
    """Return mutually-exclusive (plan, ask) flags; Ask wins a conflict."""
    return (False, True) if ask else (bool(plan), False)


def connector_mode_skips(connectors: list[str], *, plan: bool, ask: bool) -> list[dict[str, str]]:
    """Explain connector selections that a safe mode intentionally does not load."""
    if plan and not ask:
        return [{"name": name, "reason": "计划模式不启用外部连接器"} for name in connectors]
    return []


async def _run_chat_inner(
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
    knowledge_ids: list[str] | None = None,
    refs: list[dict] | None = None,
    system_extra: str | None = None,
    workspace: str | None = None,
    idempotency_key: str | None = None,
    retry_of: str | None = None,
    max_total_tokens: int = 0,
    max_output_tokens: int = 0,
    chat_trace: telemetry.Observation,
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
    # 助理人格注入（WB-077）：外部渠道助理可在设置面板里定名字/风格，这里附加到系统提示。
    if system_extra and system_extra.strip():
        system_prompt += "\n\n# 助理设定\n" + system_extra.strip()
    # 个性化偏好（WB-147）：用户在「设置 · 个性化」定的回复风格 + 自定义指令，注入系统提示，
    # 全模式（exec/plan/ask）真生效。无偏好则空串。
    system_prompt += build_personalization_prompt(user.id)
    # 用户记忆（WB-148）：此前记住的关于用户的长期事实，注入系统提示 → 之后对话「记得」。无则空串。
    # WB-167：本地嵌入可用时按【当前这轮 user_text】的语义相关性检索 top-N（否则按强度排序）。
    system_prompt += memory.build_memory_prompt(user.id, query_text=user_text)

    # Per-project workspace (§11.2): this run's tools operate in the project's own
    # checkout (or the shared default for ad-hoc chats). WB-087: an assistant may
    # override this (dedicated / project:<id>) via the `workspace` spec.
    use_root(workspace_root(workspace, session.project_id))
    # Work-item tools (WB-030) act on THIS project's plan items as this owner.
    set_work_context(session.project_id, user.id)
    # 安全中心（WB-152）：本 owner 作为工具执行归属，run_command 据此查黑名单 + 记审计。
    security.set_security_context(user.id)
    # Skill package is machine-shared, while installation/enabled state is owner-scoped (WB-249).
    skills_store.set_owner(user.id)

    def _dedup(seq: list[str]) -> list[str]:
        return list(dict.fromkeys(seq))

    # Loadout = the project's experts/skills/connectors ∪ what the ＋ menu picked.
    proj_experts, proj_skills, proj_connectors, proj_knowledge = [], [], [], []
    if session.project_id:
        project = db.get_project(session.project_id)
        if project:
            if project.instruction.strip():
                system_prompt += f"\n\n# 项目背景与规范（项目：{project.name}）\n{project.instruction.strip()}"
            proj_experts, proj_skills, proj_connectors = project.experts, project.skills, project.connectors
            proj_knowledge = project.knowledge_ids

    active_experts = _dedup(proj_experts + (experts or []))
    # 技能身份全链路以 slug 为准；兼容旧客户端传展示名。未知即时输入保留，
    # 由下方 skills_skipped 诚实报告，持久化项目/助理则在写入时直接清理（WB-183 Phase B）。
    active_skills = canonical_skill_keys(_dedup(proj_skills + (skills or [])), keep_unknown=True)
    active_connectors = _dedup(proj_connectors + (connectors or []))
    # 项目固定知识库 ∪ 本轮临时知识库；后端合并保证执行不依赖前端内存态（WB-198）。
    active_knowledge = _dedup(proj_knowledge + (knowledge_ids or []))
    # owner + 选中库 → knowledge_* 工具读的 contextvar。ask 模式无工具，置空。
    # owner 无条件带上（WB-188）：连接配置按 owner 存 DB，且 knowledge_add 不要求挂库（WB-175），
    # 「有没有挂库」由 knowledge_ids 是否为空表达，不能靠把 owner 置 None 来表达。
    set_knowledge_context(None if ask else user.id, active_knowledge if not ask else None)

    # Tell the model about the plan-item tools when this run is inside a project
    # (WB-030). Plan mode is read-only, so it only gets the viewing tool.
    if session.project_id and not ask:
        if plan:
            system_prompt += (
                "\n\n# 项目计划项（待办）\n可用 list_work_items 查看本项目的待办及其状态与 id（计划模式下只读，不修改）。"
            )
        else:
            system_prompt += (
                "\n\n# 项目计划项（待办）\n本项目的待办可用工具管理：list_work_items 查看、"
                "set_work_item_status 更新状态。若用户把某个待办「添加到输入框」交给你处理，"
                "完成或推进后请调用 set_work_item_status 回写它的状态（如置为「完成」）。"
            )

    skill_tools = []
    skill_release_snapshots: list[dict[str, Any]] = []
    loaded_experts: list[str] = []
    experts_skipped: list[str] = []
    if active_experts:
        # 自定义专家（我的专家 · WB-049）按名称优先；公共专家按稳定 slug/兼容名称解析。
        # 未知项不编通用人格，收进 experts_skipped 并在 loadout 事件诚实报告（WB-196/231）。
        custom_personas = {e.name: e.persona for e in db.list_experts(user.id) if e.persona}
        lines: list[str] = []
        for key in active_experts:
            custom = custom_personas.get(key)
            if custom:
                lines.append(f"- {custom}")
                loaded_experts.append(key)
                continue
            spec = expert_for(key)
            if spec is None:
                experts_skipped.append(key)
                continue
            lines.append(f"- {spec['persona']}")
            loaded_experts.append(spec["name"])
        if lines:
            system_prompt += "\n\n# 专家人格（请综合以下专长作答）\n" + "\n".join(lines)
    # 技能解析（WB-179）：只注入**真解析得到**的（内置带工具包 / 已装磁盘 skill 的真实
    # SKILL.md）。解析不到的不注入、不伪造指令，收进 skills_skipped 如实告知用户
    # —— 同连接器 mcp_skipped 的范式，别做静默 no-op，更别假装技能生效了。
    skills_skipped: list[str] = []
    skills_budget_omitted: list[str] = []
    skills_truncated: list[str] = []
    skill_prompt_remaining = 12_000
    if active_skills:
        lines = []
        for name in active_skills:
            d = skill_runtime_def(name)
            if d is None:
                skills_skipped.append(name)
                continue
            instr = str(d["instructions"])
            tools = d["tools"]
            if skill_prompt_remaining <= 0:
                skills_budget_omitted.append(name)
                continue
            injected = instr[:skill_prompt_remaining]
            skill_prompt_remaining -= len(injected)
            if len(injected) < len(instr):
                skills_truncated.append(name)
                injected += f"\n[技能指令已按总预算截断：{len(injected)}/{len(instr)} 字符]"
            lines.append(f"- {name}：{injected}")
            skill_tools.extend(tools)
            skill_release_snapshots.append(dict(d["snapshot"]))
        if lines:
            system_prompt += "\n\n# 已启用技能\n" + "\n".join(lines)
            if len(lines) > 1:
                system_prompt += "\n技能指令冲突时，遵循用户明确要求 > 项目规范 > 上述 loadout 顺序，且任何技能不得放宽安全约束。"
    set_active_skill_resources(skill_release_snapshots)

    async def report_skill_runs(event: str) -> None:
        """Best-effort aggregate telemetry; never uploads prompts, files, tool args or secrets."""
        token = db.get_server_identity(user.id) or ""
        release_ids = list(dict.fromkeys(
            str(snapshot.get("release_id") or "") for snapshot in skill_release_snapshots
            if snapshot.get("release_id")
        ))
        if not token or not release_ids:
            return
        await asyncio.gather(*(
            asyncio.to_thread(server_client.record_skill_release_metric, token, release_id, event)
            for release_id in release_ids
        ))
    if has_active_resources():
        system_prompt += (
            "\n\n# Skill 资源\n需要 references 或模板时先用 skill_list_resources / "
            "skill_read_resource 按需读取；只有 templates/ 文件可用 skill_copy_template 复制到工作区。"
            "scripts/ 仅可作为文本读取，不得直接执行。"
        )

    if active_knowledge and not ask:
        system_prompt += (
            f"\n\n# 已挂载知识库（{len(active_knowledge)} 个）\n"
            "遇到需要事实性/资料性依据的问题，先用 knowledge_retrieve 检索知识库，"
            "再基于命中内容作答并注明来源；检索不到再用你自己的知识回答。"
            "需要把工作区里的文件沉淀进知识库（用户说「加入/上传/添加到知识库」）时，用 knowledge_add。"
        )
    elif weknora.configured(user.id) and not ask:
        system_prompt += (
            "\n\n# 知识库\n本机已接入知识库。用户要把工作区文件「加入/上传/添加到知识库」时，"
            "直接用 knowledge_add（无需先挂载；只有一个库时自动选，多个库用 knowledge_id 或 kb_name 指定）。"
        )

    # Attached / referenced files (＋ menu) are prepended to THIS turn's LLM input
    # only — the persisted user message stays clean, so the bubble shows just the
    # typed text and history replay doesn't re-feed large file bodies.
    llm_user_text = user_text
    if refs:
        blocks = []
        total = 0
        for r in refs[:MAX_REFS]:  # cap count
            name = str(r.get("name", "file"))[:MAX_REF_NAME]  # cap name
            budget = MAX_REFS_TOTAL - total
            if budget <= 0:
                break
            raw = str(r.get("content", ""))
            body = raw[:min(MAX_REF_BODY, budget)]  # cap per-ref + running total
            total += len(body)
            # WB-025: if we dropped part of the body, say so in-band so the model (and
            # anyone reading the trace) knows the content is partial — never silent.
            note = (
                f"\n[⚠ 内容已截断：仅注入前 {len(body)} 字符，原文共 {len(raw)} 字符]"
                if len(raw) > len(body) else ""
            )
            # A 计划「添加到输入框」ref carries the work_item id (WB-030): render it as a
            # task the agent can act on, not a plain file, and point at the status tool.
            if r.get("kind") == "todo" and r.get("itemId"):
                blocks.append(
                    f"【关联待办任务 {name}（计划项 id={r['itemId']}）】\n{body}{note}\n"
                    "（处理完成或推进后，调用 set_work_item_status(item_id, status) 回写它的状态）"
                )
            else:
                blocks.append(f"【参考文件 {name}】\n{body}{note}")
        llm_user_text = "\n\n".join(blocks) + "\n\n---\n\n" + user_text

    llm_messages = _build_llm_messages(session_id, llm_user_text, system_prompt)
    work_item_id = next(
        (str(ref.get("itemId")) for ref in (refs or []) if ref.get("kind") == "todo" and ref.get("itemId")),
        None,
    )
    try:
        workspace_key = str(current_root().resolve().relative_to(settings.WORKSPACE_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        workspace_key = "default"
    run, created = db.create_run(
        session_id=session_id, owner_id=user.id, project_id=session.project_id,
        work_item_id=work_item_id, mode="ask" if ask else ("plan" if plan else "exec"),
        workspace=workspace_key, idempotency_key=idempotency_key, retry_of=retry_of,
        permission_snapshot={
            "mode": "ask" if ask else ("plan" if plan else "exec"),
            "experts": active_experts, "skills": active_skills,
            "skill_releases": skill_release_snapshots,
            "connectors": active_connectors, "knowledge_ids": active_knowledge,
        },
    )
    run_id = run.id
    if not created:
        yield events.run(run.to_dict())
        yield events.done()
        return

    db.add_message(session_id=session_id, role="user", content=user_text, actor=user.id)
    db.touch_session(session_id, status="running")

    stop = asyncio.Event()
    _register_run(session_id, run_id, stop)
    finished_ok = False  # set once the run reaches its normal 'done' (WB-012)
    mcp_stack = None       # defined before the try so `finally` can always close it
    trace_items: list[dict[str, Any]] = []
    assistant_text = ""
    last_prompt = 0
    total_prompt = 0
    total_completion = 0
    stopped = False
    schemas: list[dict[str, Any]] = []
    tool_call_count = 0
    t0 = time.time()

    def record(item: dict[str, Any]) -> str:
        trace_items.append(item)
        return _trace_to_sse(item)

    def _persist_partial() -> str | None:
        # Persist whatever text/trace already streamed before the run errored out,
        # else on reload the user sees their message with no assistant reply at all
        # (WB-160). Best-effort usage (may be approximate on the error path).
        if assistant_text.strip() or trace_items:
            msg = db.add_message(
                session_id=session_id, role="assistant", content=assistant_text,
                actor="assistant", trace=trace_items,
                usage={"prompt": total_prompt or last_prompt, "completion": total_completion or _approx_tokens(assistant_text)},
            )
            return msg.id
        return None

    # Once the run is registered, everything runs inside the try so a client
    # disconnect (CancelledError / GeneratorExit) anywhere — including the connector
    # spawn `await` — still hits `finally`: the session status is reset and connector
    # MCP servers are closed, never leaked (WB-012, plus the mcp_stack-outside-try
    # leak noted in WB-023).
    try:
        yield events.run(run.to_dict())
        yield events.status("running")

        # Active toolset. Ask mode = no tools (pure Q&A). Otherwise base
        # (plan-filtered) tools + skill tools + connector (MCP) tools; connectors
        # spawn their stdio MCP servers now and are closed in `finally`.
        # Work-item tools only for project runs (WB-030) — ad-hoc chats have no
        # plan board to act on. Plan mode gets the read-only one (no status writes).
        wi_tools = work_item_tools(plan) if (session.project_id and not ask) else []
        # 知识库工具（ask 模式无工具）：检索按会话挂载的库（active_knowledge）给；
        # 加入文件只要后端接了 WeKnora（配了 key）就给——不要求先挂载（WB-175）。
        kb_tools = []
        if not ask:
            if active_knowledge:
                kb_tools.append(knowledge_retrieve)
            if settings.WEKNORA_API_KEY:
                kb_tools.append(knowledge_add)
        # WB-186：skill_tools / kb_tools 从前**完全绕过 plan 过滤**（只有 base_tools 和
        # wi_tools 认 plan）。技能侧当时恰好 3 个工具全只读所以没暴雷；知识库侧却是真漏：
        # knowledge_add 是写（灌文件进库 + 解析/切片/向量化），计划模式下 agent 真能调它。
        # 现在统一按 Tool.plan_safe 过滤（默认 False = 保守，新工具不标注就进不了 plan）。
        tools_list = [] if ask else (
            base_tools(plan)
            + plan_filter(skill_tools, plan)
            + plan_filter(RESOURCE_TOOLS if has_active_resources() else [], plan)
            + wi_tools  # work_item_tools(plan) 内部已过滤
            + plan_filter(kb_tools, plan)
        )
        active_tools = {t.name: t for t in tools_list}
        mcp_tools = []
        mcp_skipped = connector_mode_skips(active_connectors, plan=plan, ask=ask)
        if active_connectors and not plan and not ask:
            mcp_tools, mcp_stack, mcp_skipped = await open_connectors(
                active_connectors, env={"AGENTMATE_NOTES_DIR": str(current_root())}
            )
        mcp_by_name = {t.qualified: t for t in mcp_tools}
        schemas = (
            # 从 active_tools（已按名去重）生成，而非 tools_list —— 后者若有重名会向 LLM
            # 发两份同名 schema（WB-186）。今天技能工具与 base 工具无重名，但技能定义已可
            # 运营（WB-183），重名风险上升；且 run_tool 本来就只认 active_tools 里的那个。
            [t.schema() for t in active_tools.values()]
            + [mcp_schema(t) for t in mcp_tools]
            + ([] if ask else [ASK_USER_SCHEMA])
        )
        db.update_run_runtime(
            run_id,
            permission_snapshot={
                **run.permission_snapshot,
                "tools": sorted(active_tools),
                "mcp_tools": sorted(mcp_by_name),
                "permissions": sorted(
                    {permission for tool in active_tools.values() for permission in tool.permissions}
                    | ({"connector.call", "external.dynamic"} if mcp_by_name else set())
                ),
                "tool_policies": {
                    name: {
                        "permissions": list(tool.permissions),
                        "timeout_seconds": tool.timeout_seconds,
                        "isolation": tool.isolation,
                    }
                    for name, tool in sorted(active_tools.items())
                },
            },
        )

        # Show the loadout so the persona / skills / connectors that shaped this
        # run are visible — including connectors that were selected but couldn't
        # load (e.g. GitHub without a token), so it isn't a silent no-op.
        connector_names = sorted({t.connector for t in mcp_tools})
        loaded_skills = [
            skill_display_name(n) for n in active_skills
            if n not in skills_skipped and n not in skills_budget_omitted
        ]
        if active_experts or active_skills or connector_names or mcp_skipped or (active_knowledge and not ask):
            parts = []
            if loaded_experts:
                parts.append("专家 " + "、".join(loaded_experts))
            if loaded_skills:
                parts.append("技能 " + "、".join(loaded_skills))
            if connector_names:
                parts.append("连接器 " + "、".join(connector_names))
            if active_knowledge and not ask:
                parts.append(f"知识库 {len(active_knowledge)} 个")
            if mcp_skipped:
                parts.append("连接器未就绪 " + "、".join(f"{s['name']}（{s['reason']}）" for s in mcp_skipped))
            # 解析不到的技能如实报出（WB-179）——此前它们会被喂一句兜底话术，UI 照常显示
            # 「已加载」，用户无从分辨技能到底有没有生效。
            if skills_skipped:
                parts.append("技能未就绪 " + "、".join(
                    f"{skill_display_name(n)}（未安装或已停用）" for n in skills_skipped
                ))
            if skills_budget_omitted:
                parts.append("技能预算未加载 " + "、".join(skill_display_name(n) for n in skills_budget_omitted))
            if skills_truncated:
                parts.append("技能指令已截断 " + "、".join(skill_display_name(n) for n in skills_truncated))
            if experts_skipped:
                parts.append("专家未就绪 " + "、".join(
                    f"{n}（无人格定义）" for n in experts_skipped
                ))
            yield record({"kind": "step", "tool": "loadout", "label": "已加载 · " + " · ".join(parts)})

        # Resolve the picker selection to a concrete provider once (owner-scoped so a
        # provider/custom model uses its own base/key/path). Stable across tool-loop rounds.
        model_id, model_base, model_key, model_path = resolve_model_config(user.id, model)
        # 智能体设置（WB-150）：工具步数上限 + 回复发散度，按 owner 可配，本轮真读真用。
        _max_rounds = agent_settings.get_max_rounds(user.id)
        _temperature = agent_settings.get_temperature(user.id)

        for _round in range(_max_rounds):
            content_buf = ""
            reasoning_buf = ""
            tool_acc: dict[int, dict[str, Any]] = {}
            think_pending = True  # emit a "深度思考" marker before acting if no reasoning shown
            round_prompt = 0
            round_completion = 0
            first_token_at = None

            with telemetry.generation_observation(
                name=f"llm.chat.round-{_round + 1}",
                model=model_id,
                messages=llm_messages,
                temperature=_temperature,
                round_number=_round + 1,
            ) as generation_trace:
                async with aclosing(stream_chat(
                    llm_messages, model=model_id, tools=schemas,
                    api_base=model_base, api_key=model_key, chat_path=model_path,
                    temperature=_temperature,
                    max_tokens=max_output_tokens or None,
                )) as deltas:
                    async for delta in deltas:
                        if stop.is_set():
                            stopped = True
                            break
                        if first_token_at is None and (delta.content or delta.reasoning or delta.tool_calls):
                            first_token_at = datetime.now(timezone.utc)
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
                            round_prompt = int(delta.usage.get("prompt_tokens") or round_prompt)
                            round_completion += int(delta.usage.get("completion_tokens") or 0)
                            last_prompt = round_prompt or last_prompt
                            total_completion += int(delta.usage.get("completion_tokens") or 0)

                generation_trace.update(
                    output={
                        "content": content_buf,
                        "tool_calls": [item.get("name", "") for item in tool_acc.values()],
                        "stopped": stopped,
                    },
                    completion_start_time=first_token_at,
                    usage_details={"input": round_prompt, "output": round_completion},
                )

            total_prompt += round_prompt
            if max_total_tokens > 0 and total_prompt + total_completion > max_total_tokens:
                raise RuntimeBudgetExceeded(
                    f"Token budget exceeded: {total_prompt + total_completion} > {max_total_tokens}"
                )

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
                    tool_call_count += 1
                    with telemetry.tool_observation(
                        name="ask_user",
                        arguments={
                            "question_count": len(args.get("questions") or [])
                            if isinstance(args.get("questions"), list) else 0,
                        },
                        source="runtime",
                    ) as tool_trace:
                        # Suspend the agent until the user answers (spec 5.3). The
                        # /answer endpoint sets our event and wakes us on the SAME
                        # open SSE stream. stop also wakes us (via request_stop).
                        questions = args.get("questions") or []
                        # Be robust to a model that returns malformed questions (bare
                        # strings instead of {q, options}) — coerce so a bad shape
                        # doesn't AttributeError the whole turn (WB-023).
                        questions = [
                            q if isinstance(q, dict) else {"q": str(q), "options": []}
                            for q in (questions if isinstance(questions, list) else [])
                        ]
                        ev = asyncio.Event()
                        _answers[run_id] = {"ev": ev, "answers": None}
                        yield events.ask_user(questions)
                        db.touch_session(session_id, status="waiting")
                        db.set_run_status(run_id, "waiting_approval")
                        await ev.wait()
                        pending = _answers.pop(run_id, None)
                        answers = (pending or {}).get("answers")
                        db.touch_session(session_id, status="running")
                        if not stop.is_set() and answers is not None:
                            db.set_run_status(run_id, "running")
                        if stop.is_set() or answers is None:
                            stopped = True
                            tool_trace.update(output={"status": "cancelled"})
                            llm_messages.append({"role": "tool", "tool_call_id": call["id"], "content": "用户已跳过或取消本次提问。"})
                            break
                        qa = [
                            {"q": q.get("q", ""), "a": answers[i] if i < len(answers) else ""}
                            for i, q in enumerate(questions)
                        ]
                        yield record({"kind": "qa", "qa": qa})
                        result = "用户的选择：\n" + "\n".join(f"- {x['q']} → {x['a']}" for x in qa)
                        tool_trace.update(output={"status": "answered", "answer_count": len(answers)})
                        llm_messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
                    continue

                if name in mcp_by_name:
                    tool_call_count += 1
                    mt = mcp_by_name[name]
                    yield record({"kind": "step", "tool": mt.orig, "label": f"[{mt.connector}] {mt.orig}"})
                    with telemetry.tool_observation(
                        name=mt.orig, arguments=args, source="mcp",
                        metadata={"connector": mt.connector, "qualified_name": name},
                    ) as tool_trace:
                        try:
                            result = await execute_async_call(call_mcp(mt, args), stop, 60)
                            tool_trace.update(output=result)
                        except ToolExecutionCancelled:
                            stopped = True
                            result = "连接器调用已取消。"
                            yield record({"kind": "step", "tool": name, "label": result, "status": "cancelled"})
                            tool_trace.update(output={"status": "cancelled"})
                        except ToolExecutionTimeout:
                            result = "连接器调用超时（60s）。"
                            yield record({"kind": "step", "tool": name, "label": result, "status": "timeout"})
                            tool_trace.update(output={"status": "timeout"})
                    llm_messages.append({"role": "tool", "tool_call_id": call["id"], "content": result[:6000]})
                    if stopped:
                        break
                    continue

                tool = active_tools.get(name)
                if tool is None:
                    llm_messages.append({"role": "tool", "tool_call_id": call["id"], "content": f"未知工具：{name}"})
                    continue
                if tool.pre:
                    pre = tool.pre(args)
                    if pre:
                        yield record(pre)
                tool_call_count += 1
                # Run the (synchronous) tool off the event loop so a long
                # subprocess / web_fetch / file IO can't freeze every other SSE
                # stream or block /stop for its whole timeout (WB-002). to_thread
                # copies the contextvars, so the sandbox root stays correct.
                with telemetry.tool_observation(
                    name=name, arguments=args, source="builtin",
                ) as tool_trace:
                    try:
                        outcome = await execute_tool(tool, args, stop)
                        tool_trace.update(output=outcome.text)
                    except ToolExecutionCancelled:
                        stopped = True
                        outcome = ToolOutcome(text=f"工具 {name} 已取消。")
                        yield record({"kind": "step", "tool": name, "label": outcome.text, "status": "cancelled"})
                        tool_trace.update(output={"status": "cancelled"})
                    except ToolExecutionTimeout:
                        outcome = ToolOutcome(text=f"工具 {name} 执行超时（{tool.timeout_seconds:g}s）。")
                        yield record({"kind": "step", "tool": name, "label": outcome.text, "status": "timeout"})
                        tool_trace.update(output={"status": "timeout"})
                for it in outcome.trace:
                    yield record(it)
                for descriptor in outcome.artifacts:
                    path = descriptor.get("path", "")
                    try:
                        target = resolve_in_sandbox(path)
                        artifact = db.upsert_artifact(
                            run_id=run_id, path=path, full_path=target,
                            source_tool=name, kind=descriptor.get("kind", "file"),
                            validation=descriptor.get("validation"),
                            preview_path=descriptor.get("preview_path"),
                        )
                    except (FileNotFoundError, PermissionError, ValueError):
                        continue
                    yield record({
                        "kind": "artifact", "id": artifact.id, "run_id": run_id,
                        "name": artifact.name, "size": str(artifact.size), "path": artifact.path,
                        "sha256": artifact.sha256, "mime_type": artifact.mime_type,
                        "acceptance_status": artifact.acceptance_status,
                    })
                # Transient live events (WB-031: kanban sync) — emitted, not recorded,
                # so history replay never re-fires a stale state change.
                for ev in outcome.live:
                    yield events.work_item(ev)
                llm_messages.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": outcome.text}
                )
                if stopped:
                    break
            if stopped:
                break
            # loop again so the model can use the results
        finished_ok = True  # loop completed normally (incl. user-stop)
    except RuntimeBudgetExceeded as e:
        chat_trace.update(
            output={"status": "token_budget_exceeded", "partial_chars": len(assistant_text)},
            level="ERROR", status_message=str(e),
        )
        yield events.error("本次自动化已达到 token 成本上限")
        mid = _persist_partial()
        db.update_run_runtime(
            run_id, prompt_tokens=total_prompt or last_prompt,
            completion_tokens=total_completion, tool_calls=tool_call_count,
        )
        db.set_run_status(
            run_id, "failed", error_code="token_budget_exceeded", error_message=str(e)
        )
        db.touch_session(session_id, status="idle")
        finished_ok = True
        yield events.done(mid)
        await report_skill_runs("run_failed")
        return
    except LLMError as e:
        chat_trace.update(
            output={"status": "llm_error", "partial_chars": len(assistant_text)},
            level="ERROR", status_message=str(e),
        )
        yield events.error(str(e))
        mid = _persist_partial()  # 保留已流式的半截回复（WB-160）
        db.update_run_runtime(run_id, prompt_tokens=total_prompt or last_prompt, completion_tokens=total_completion, tool_calls=tool_call_count)
        db.set_run_status(run_id, "failed", error_code="llm_error", error_message=str(e))
        db.touch_session(session_id, status="idle")
        finished_ok = True  # status settled; don't let finally override it
        yield events.done(mid)
        await report_skill_runs("run_failed")
        return
    except Exception as e:  # noqa: BLE001 — surface any hiccup to the UI
        chat_trace.update(
            output={"status": "error", "partial_chars": len(assistant_text)},
            level="ERROR", status_message=str(e),
        )
        yield events.error(f"执行出错：{e}")
        mid = _persist_partial()  # 保留已流式的半截回复（WB-160）
        db.update_run_runtime(run_id, prompt_tokens=total_prompt or last_prompt, completion_tokens=total_completion, tool_calls=tool_call_count)
        db.set_run_status(run_id, "failed", error_code="runtime_error", error_message=str(e))
        db.touch_session(session_id, status="idle")
        finished_ok = True
        yield events.done(mid)
        await report_skill_runs("run_failed")
        return
    finally:
        _unregister_run(session_id, run_id)
        # If the run never reached a normal finish (client disconnect →
        # CancelledError, a BaseException that skips `except Exception`), leave the
        # session 'idle' instead of a phantom 'running'/'waiting' (WB-012).
        if not finished_ok:
            db.touch_session(session_id, status="idle")
            current_run = db.get_run(run_id)
            if current_run and current_run.status in {"planning", "running", "waiting_approval"}:
                try:
                    db.set_run_status(run_id, "paused", checkpoint={"reason": "stream_disconnected"})
                except ValueError:
                    db.set_run_status(run_id, "cancelled", error_code="stream_disconnected")
        if mcp_stack is not None:
            try:
                await mcp_stack.aclose()  # terminate connector MCP servers
            except Exception:  # noqa: BLE001
                pass

    if total_prompt == 0:
        total_prompt = last_prompt or sum(_approx_tokens(str(m.get("content") or "")) for m in llm_messages)
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
            usage={"prompt": total_prompt, "completion": total_completion},
        )
        message_id = msg.id

    db.update_run_runtime(
        run_id,
        plan=[{"text": item["text"]} for item in trace_items if item.get("kind") == "todo"],
        prompt_tokens=total_prompt, completion_tokens=total_completion, tool_calls=tool_call_count,
    )
    db.set_run_status(run_id, "cancelled" if stopped else "completed")

    chat_trace.update(
        output={"content": assistant_text, "stopped": stopped},
        metadata={
            "message_id": message_id or "",
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "tool_trace_items": len(trace_items),
        },
    )

    db.touch_session(session_id, status="done")

    yield _usage_event(total_prompt, total_completion, schemas, system_prompt)
    yield events.status("done", secs=secs)
    if stopped:
        yield events.text("\n\n_（已停止生成）_")
    yield events.done(message_id)
    await report_skill_runs("run_failed" if stopped else "run_succeeded")

    # 对话记忆自动抽取（WB-148）：用户在「设置 · 记忆」开启后，从这轮对话提炼可长期记住的用户事实，
    # 去重入库，供之后对话注入。**放在 done 之后**——前端已解锁，不被抽取往返拖住；`wait_for` 兜底，
    # 防抽取端点卡死（stream_chat read 超时为 None）把连接/生成器无限期挂住。best-effort，任何失败静默。
    if assistant_text.strip() and memory.capture_enabled(user.id):
        try:
            await asyncio.wait_for(
                memory.extract_and_store(
                    user.id, user_text, assistant_text,
                    model=model_id, api_base=model_base, api_key=model_key, chat_path=model_path,
                ),
                timeout=30,
            )
            # 衰退 GC（WB-166）：抽取后顺手归档强度过低的旧记忆（软状态，不硬删）。纯 DB、快，best-effort。
            memory.decay_gc(user.id)
        except Exception:  # noqa: BLE001 —— 含 asyncio.TimeoutError
            pass
