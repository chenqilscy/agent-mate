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
from agent import agent_settings, memory, security, session_context, skills_store, telemetry, weknora, workspace_memory
from agent.experts import expert_for
from agent.personalization import build_personalization_prompt
from agent.context_layers import ContextLayers
from agent.delivery import build_delivery_summary
from agent.llm import LLMError, stream_chat
from agent.mcp_client import call_mcp, mcp_schema, open_connectors
from agent.sandbox import current_root, resolve_in_sandbox, use_root, workspace_root
from agent.skill_discovery import (
    DISCOVERY_TOOLS,
    build_skill_candidates,
    candidate_map,
    clear_skill_candidates,
    set_skill_candidates,
)
from agent.skill_resources import RESOURCE_TOOLS, has_active_resources, set_active_skill_resources
from agent.skills import canonical_skill_keys, skill_display_name, skill_runtime_def
from agent.tool_execution import (
    ToolExecutionCancelled, ToolExecutionTimeout, execute_async_call, execute_tool,
)
from agent.execution_policy import (
    ALLOW_ONCE_ANSWER,
    ALLOW_SESSION_ANSWER,
    TOOL_AUTHORIZATION_OPTIONS,
    ExecutionAuthorization,
    ToolAuthorizationDenied,
)
from agent.tools import (
    ASK_USER_SCHEMA,
    base_tools,
    deferred_tools,
    knowledge_add,
    knowledge_retrieve,
    plan_filter,
    run_tool,
    server_tool_enabled,
    set_deferred_tool_candidates,
    set_knowledge_context,
    set_work_context,
    Tool,
    ToolOutcome,
    tool_search,
    work_item_tools,
)
from config import settings
import server_client
import server_sync
from storage import db, model_governance, provider_seed
from storage.models import Message, Project, Session, User


class RuntimeBudgetExceeded(RuntimeError):
    """Raised before another tool/LLM round once the configured token cap is reached."""


def _request_output_limit(
    *, requested: int, model_cap: int, context_room: int, run_room: int | None = None,
) -> int:
    """Clamp one generation by explicit request, provider/model cap and live budgets."""
    limits = [max(1, int(model_cap)), int(context_room)]
    if requested > 0:
        limits.append(int(requested))
    if run_room is not None:
        limits.append(int(run_room))
    value = min(limits)
    if value <= 0:
        raise RuntimeBudgetExceeded("No output token room remains for this generation")
    return value


def _knowledge_tools(
    owner_id: str, active_knowledge: list[str], *, ask: bool, remote_project: bool = False,
) -> list[Tool]:
    """Local projects use owner config; Server projects use the central guarded gateway."""
    if ask:
        return []
    out = [knowledge_retrieve] if active_knowledge else []
    if remote_project or weknora.configured(owner_id):
        out.append(knowledge_add)
    return out


SYSTEM_PROMPT = (
    "你是 AgentMate，一个运行在用户本机的智能工作伙伴。\n"
    "你可以使用提供的工具在工作区（沙箱目录）内操作：列目录(list_dir)、读文件(read_file)、"
    "写文件(write_file)、运行命令(run_command)、更新待办清单(update_plan)；"
    "生成或检查 DOCX/XLSX/PPTX/PDF、使用浏览器导航/读取/安全交互等长尾能力不会默认暴露 schema，"
    "需要时先调用 tool_search 检索并加载，再从下一轮使用；"
    "遇到影响方向的关键决策时用 ask_user 向用户确认。\n"
    "工作方式：先思考再行动；多步任务先用 update_plan 拆解；需要时调用工具，逐步完成并核对结果。\n"
    "只在确有必要时使用工具——简单问答直接回答，不要空跑工具。所有路径都相对工作区根目录。\n"
    "最终回答使用 Markdown：用二级标题（##）分章节，善用列表、表格、代码块，让结构清晰。"
    "最终回复必须自包含地说明完成内容、实际验证结果和仍未完成的边界；不得把未校验或待验收产物说成已经验收。"
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


def _question_checkpoint(
    questions: list[dict[str, Any]], *, source: str, tool_call_id: str,
    tool_name: str = "",
) -> dict[str, Any]:
    checkpoint: dict[str, Any] = {
        "kind": "ask_user",
        "questions": questions,
        "source": source,
        "tool_call_id": tool_call_id,
        "asked_at": time.time(),
    }
    if tool_name:
        checkpoint["tool_name"] = tool_name
    return checkpoint


def _merge_checkpoint(run_id: str, **updates: Any) -> dict[str, Any]:
    run = db.get_run(run_id)
    checkpoint = dict(run.checkpoint) if run and isinstance(run.checkpoint, dict) else {}
    checkpoint.update(updates)
    return checkpoint


def _without_pending_question(run_id: str) -> dict[str, Any]:
    checkpoint = _merge_checkpoint(run_id)
    if checkpoint.get("kind") == "ask_user":
        for key in ("kind", "questions", "source", "tool_call_id", "tool_name", "asked_at", "reason"):
            checkpoint.pop(key, None)
    return checkpoint


def resolve_model_config(
    owner_id: str, client_model: str | None
) -> tuple[str, str | None, str | None, str]:
    """Map the picker selection to a concrete (model_id, api_base, api_key, chat_path).

    Resolution order (WB-136: the default no longer reads .env — it is a user choice):
      0. Empty selection「跟随默认」→ the owner's DB default model (set in「模型管理」).
         No default configured → raise, honestly (no silent .env fallback).
      1. Built-in provider pick `@{provider}:{model}` (WB-128) → the provider's
         base_url/chat_path (provider_seed) + the owner's key for that provider.
      2. DB custom model matched by display name (WB-124) → its own base/key.
      3. Anything else (unknown provider / key revoked / model deleted) → raise,
         so the user picks a valid default instead of silently running a config-file model.
    Every successful path returns an owner-scoped API base and key. There is no
    environment/config-file fallback.
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
            try:
                base = model_governance.validate_endpoint_url(base)
            except ValueError as exc:
                raise LLMError(str(exc)) from exc
            return mid, base, key, path
        # provider unknown / model empty / no key → 落到下方诚实报错
    else:
        row = db.get_custom_model_by_name(owner_id, client_model, include_secrets=True)
        if row and row.get("model_id"):
            base = row.get("api_base")
            key = row.get("api_key")
            if base and key:
                try:
                    base = model_governance.validate_endpoint_url(base)
                except ValueError as exc:
                    raise LLMError(str(exc)) from exc
                return row["model_id"], base, key, default_path
    raise LLMError(
        f"模型「{client_model}」当前不可用（可能厂商 Key 已撤销、或模型已删除）。"
        "请在「模型管理」里补充该模型的 API Base/API Key，或重新选择可运行模型。"
    )


def parse_legacy_model_id(selection: str) -> str | None:
    """Parse old display labels for data compatibility; never supplies credentials."""
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
    if k == "plan_snapshot":
        return events.plan_snapshot(
            item["version"], item["items"], item.get("project_id"),
        )
    if k == "plan_patch":
        return events.plan_patch(
            item["version"], item["items"], item.get("project_id"),
        )
    if k == "qa":
        return events.qa_summary(item["qa"])
    if k == "context_degraded":
        return events.context_degraded(item["reason"], item["excerpt_messages"])
    if k == "artifact":
        return events.artifact(
            item["name"], item["size"], item["path"], artifact_id=item["id"],
            run_id=item["run_id"], sha256=item["sha256"], mime_type=item["mime_type"],
            acceptance_status=item.get("acceptance_status", "pending"),
            is_primary=bool(item.get("is_primary")),
            display_order=int(item.get("display_order") or 0),
        )
    return ""


def _usage_event(
    prompt_tokens: int, completion_tokens: int, schemas: list[dict[str, Any]],
    system_prompt: str, context_window: int = settings.CONTEXT_WINDOW,
) -> str:
    used = prompt_tokens + completion_tokens
    pct = used / max(1, context_window) * 100
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


def _cached_prompt_tokens(usage: dict[str, Any]) -> int:
    details = usage.get("prompt_tokens_details") or {}
    return max(0, int(
        details.get("cached_tokens")
        or usage.get("prompt_cache_hit_tokens")
        or 0
    ))


def _history_budget(
    context_window: int, system_prompt: str, requested_output: int,
) -> int:
    """Reserve room for system/tool contracts and output before adding history."""
    output_reserve = requested_output or min(8192, max(1024, context_window // 8))
    tool_reserve = min(12_000, max(2048, context_window // 10))
    available = context_window - _approx_tokens(system_prompt) - output_reserve - tool_reserve
    return max(256, min(settings.SESSION_HISTORY_TOKEN_BUDGET, available))


async def _build_memory_prompt(
    owner_id: str, query_text: str, project_id: str | None,
) -> str:
    """Keep model loading, embedding HTTP and legacy-vector backfill off-loop."""
    def _worker() -> str:
        try:
            return memory.build_memory_prompt(
                owner_id,
                query_text,
                project_id=project_id,
            )
        finally:
            # asyncio's executor threads are long-lived.  A thread-local SQLite
            # connection left behind here pins temporary DB files on Windows and
            # keeps stale database paths across owner/test boundaries.
            db.close_thread_connection()

    return await asyncio.to_thread(_worker)


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
    bundle_ids: list[str] | None = None,
    connectors: list[str] | None = None,
    knowledge_ids: list[str] | None = None,
    refs: list[dict] | None = None,
    system_extra: str | None = None,
    workspace: str | None = None,
    idempotency_key: str | None = None,
    retry_of: str | None = None,
    max_total_tokens: int = 0,
    max_output_tokens: int = 0,
    execution_source: str = "interactive",
    preauthorized_permissions: list[str] | None = None,
    history_override: list[Message] | None = None,
    project_override: Project | None = None,
    server_token_override: str | None = None,
    authoritative_run_context: dict[str, str] | None = None,
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
            experts=experts, skills=skills, bundle_ids=bundle_ids, connectors=connectors,
            knowledge_ids=knowledge_ids, refs=refs,
            system_extra=system_extra, workspace=workspace,
            idempotency_key=idempotency_key, retry_of=retry_of,
            max_total_tokens=max_total_tokens,
            max_output_tokens=max_output_tokens,
            execution_source=execution_source,
            preauthorized_permissions=preauthorized_permissions,
            history_override=history_override,
            project_override=project_override,
            server_token_override=server_token_override,
            authoritative_run_context=authoritative_run_context,
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
    bundle_ids: list[str] | None = None,
    connectors: list[str] | None = None,
    knowledge_ids: list[str] | None = None,
    refs: list[dict] | None = None,
    system_extra: str | None = None,
    workspace: str | None = None,
    idempotency_key: str | None = None,
    retry_of: str | None = None,
    max_total_tokens: int = 0,
    max_output_tokens: int = 0,
    execution_source: str = "interactive",
    preauthorized_permissions: list[str] | None = None,
    history_override: list[Message] | None = None,
    project_override: Project | None = None,
    server_token_override: str | None = None,
    authoritative_run_context: dict[str, str] | None = None,
    chat_trace: telemetry.Observation,
) -> AsyncIterator[str]:
    """Async generator of SSE strings for POST /api/chat.

    Persists the user turn, runs the tool loop, persists the assistant turn with
    its full trace so history replay reproduces the trace. Plan mode plans only
    (read-only tools + ask_user); Ask mode answers only (no tools). The loadout
    (experts/skills/connectors) is the project's plus any picked from the ＋ menu.
    """
    session_id = session.id
    context_layers = ContextLayers(PLAN_SYSTEM_PROMPT if plan else SYSTEM_PROMPT)
    if ask:
        context_layers.add(
            "ask_mode", "只回答用户的问题，不要调用任何工具、不执行任何操作。",
            source="run.mode", authority="system", priority=10, heading="仅问答模式",
        )
    if authoritative_run_context:
        server_session_id = str(authoritative_run_context.get("session_id") or "")
        server_run_id = str(authoritative_run_context.get("run_id") or "")
        server_work_item_id = str(authoritative_run_context.get("work_item_id") or "")
        context_layers.add(
            "authoritative_server_run",
            f"当前已经是 Server 创建并由 Local Agent 领取的权威项目 Run："
            f"session_id={server_session_id}，run_id={server_run_id}，"
            f"work_item_id={server_work_item_id}。不得再次调用 start_work_item_run，也不得声称缺少真实 Run 标识。"
            "专注生成任务交付物；Run 终态和已校验产物会由 Server 自动把 WorkItem 推进到待验收或暂停，"
            "无需也不得自行调用 set_work_item_status。",
            source="server.run", authority="system", priority=11, heading="权威 Server Run",
        )
    # 助理人格注入（WB-077）：外部渠道助理可在设置面板里定名字/风格，这里附加到系统提示。
    if system_extra and system_extra.strip():
        context_layers.add(
            "assistant_profile", system_extra, source="assistant.profile",
            authority="assistant", priority=200, heading="助理设定",
        )
    # 个性化偏好（WB-147）：用户在「设置 · 个性化」定的回复风格 + 自定义指令，注入系统提示，
    # 全模式（exec/plan/ask）真生效。无偏好则空串。
    context_layers.add(
        "personalization", build_personalization_prompt(user.id),
        source="user.settings", authority="preference", priority=300,
    )
    # 用户记忆（WB-148）：此前记住的关于用户的长期事实，注入系统提示 → 之后对话「记得」。无则空串。
    # WB-167：本地嵌入可用时按【当前这轮 user_text】的语义相关性检索 top-N（否则按强度排序）。
    context_layers.add(
        "cognitive_memory", await _build_memory_prompt(user.id, user_text, session.project_id),
        source="memory.db", authority="history", priority=400,
    )
    if session.project_id:
        context_layers.add(
            "workspace_memory", workspace_memory.build_workspace_prompt(session.project_id),
            source=f"project:{session.project_id}:memory", authority="history", priority=410,
        )

    # Per-project workspace (§11.2): this run's tools operate in the project's own
    # checkout (or the shared default for ad-hoc chats). WB-087: an assistant may
    # override this (dedicated / project:<id>) via the `workspace` spec.
    use_root(workspace_root(workspace, session.project_id))
    # 安全中心（WB-152）：本 owner 作为工具执行归属，run_command 据此查黑名单 + 记审计。
    security.set_security_context(user.id)
    # Skill package is machine-shared, while installation/enabled state is owner-scoped (WB-249).
    skills_store.set_owner(user.id)

    def _dedup(seq: list[str]) -> list[str]:
        return list(dict.fromkeys(seq))

    # Experts/connectors keep project ∪ per-session semantics.  Project Skills are
    # a discoverable candidate pool; the ＋ menu / assistant Skills are explicit
    # activations and keep the existing eager-load behavior (WB-334).
    proj_experts, proj_skills, proj_connectors, proj_knowledge = [], [], [], []
    project = None
    if session.project_id:
        project = project_override or db.get_project(session.project_id)
        if project:
            if project.instruction.strip():
                context_layers.add(
                    "project_instruction", project.instruction,
                    source=f"project:{project.id}", authority="project", priority=100,
                    heading=f"项目背景与规范（项目：{project.name}）",
                )
            proj_experts, proj_skills, proj_connectors = project.experts, project.skills, project.connectors
            proj_knowledge = project.knowledge_ids

    environment_tags = ["project" if session.project_id else "adhoc"]
    if project and project.origin == "server":
        environment_tags.append("server-project")
    if session.kind == "assistant":
        environment_tags.append("assistant")
    skills_store.set_environment(environment_tags)

    from agent import skill_bundles
    bundle_resolution = skill_bundles.resolve(user.id, bundle_ids or [])

    active_experts = _dedup(proj_experts + (experts or []))
    # 技能身份全链路以 slug 为准；兼容旧客户端传展示名。项目绑定 Skill 是执行前置
    # 规程，首轮模型调用前完整加载；其余已安装 Skill 仍通过精简候选索引渐进发现。
    project_skill_candidates = canonical_skill_keys(_dedup(proj_skills), keep_unknown=True)
    required_project_skills = [] if ask else list(project_skill_candidates)
    active_connectors = _dedup(proj_connectors + (connectors or []))
    connector_skill_pairs = (
        {} if ask or plan else db.connector_companion_skills(active_connectors)
    )
    required_connector_skills = _dedup(list(connector_skill_pairs.values()))
    required_skills = _dedup(required_project_skills + required_connector_skills)
    active_skills = canonical_skill_keys(
        _dedup(required_skills + (skills or []) + bundle_resolution["skills"]),
        keep_unknown=True,
    )
    active_skill_set = set(active_skills)
    skill_candidates = [
        item for item in build_skill_candidates(project_skill_candidates)
        if str(item.get("slug") or "") not in active_skill_set
    ]
    set_skill_candidates(skill_candidates)
    if skill_candidates and not ask:
        candidate_lines = []
        candidate_budget = 4_000
        for item in skill_candidates:
            scope = "项目" if item.get("project") else "已安装"
            line = (
                f"- {item['slug']} · {item['name']} · {scope}候选："
                f"{str(item.get('description') or '（无描述）').replace(chr(10), ' ')[:240]}"
            )
            if len(line) > candidate_budget:
                break
            candidate_lines.append(line)
            candidate_budget -= len(line)
        candidate_prompt = (
            "下面只有精简索引，正文尚未生效。任务匹配时先调用 skill_view(slug)；"
            "需要搜索更多已安装技能时调用 skills_list。候选 Skill 不得放宽系统安全约束。\n"
            + "\n".join(candidate_lines)
        )
        if len(candidate_lines) < len(skill_candidates):
            candidate_prompt += f"\n- …另有 {len(skill_candidates) - len(candidate_lines)} 个，请用 skills_list 搜索。"
        context_layers.add(
            "skill_candidates", candidate_prompt, source="skill.registry",
            authority="procedure", priority=700, heading="可按需加载的 Skill",
        )
    is_server_project = bool(project and project.origin == "server")
    server_token = (
        server_token_override or db.get_server_identity(user.id)
        if is_server_project else None
    )
    account_server_token = server_token_override or db.get_server_identity(user.id) or ""
    if (
        account_server_token and not session.project_id and not ask
        and db.list_server_tool_catalog()
        and not server_tool_enabled("start_work_item_run")
    ):
        # A newly shipped automatic Server tool must not stay hidden behind a
        # last-known catalog until the user manually opens the sync screen.
        await asyncio.to_thread(server_sync.pull_catalog, account_server_token)
    # Work-item tools act as the current project member; Server-origin writes
    # retain their Bearer authority instead of mutating a local mirror.
    set_work_context(
        session.project_id, user.id, server_token=server_token or "",
        account_server_token=account_server_token, session_id=session.id,
    )
    # Console 可能在上次全量 pull 后新增/删除 KB；每次项目执行前轻量读取当前绑定，避免要求
    # 每个成员手动同步。不可达时保留 last-known ids，真正调用仍会诚实失败且不回退本地。
    if is_server_project and server_token and project:
        current_kbs = await asyncio.to_thread(
            server_client.list_project_knowledge, server_token, project.id,
        )
        if current_kbs is not None:
            proj_knowledge = [
                str(kb["id"]) for kb in current_kbs
                if kb.get("id") and kb.get("provider_status") == "ready"
            ]
    # Server 项目只认 Console 下发绑定，拒绝把客户端临时 id 混进中央租户；local 项目保留
    # “项目固定 ∪ 本轮临时挂载”语义（WB-198）。
    active_knowledge = _dedup(
        proj_knowledge if is_server_project else (proj_knowledge + (knowledge_ids or []))
    )
    set_knowledge_context(
        None if ask else user.id,
        active_knowledge if not ask else None,
        server_project_id=(project.id if is_server_project and not ask else None),
        server_token=(server_token if not ask else None),
    )

    # Tell the model about the plan-item tools when this run is inside a project
    # (WB-030). Plan mode is read-only, so it only gets the viewing tool.
    if not ask and not session.project_id:
        context_layers.add(
            "personal_action_items",
            "自然语言输入是 AgentMate 工作操作入口。用户询问今天、我的任务、待处理工作或跨项目事项时，"
            "必须先调用 list_my_action_items 读取 AgentMate Server 的真实 WorkItem；不得扫描工作区文件、"
            "聊天标题或历史输出推测任务。查询只读，不创建或修改 WorkItem；只有用户明确选择真实任务后才执行。",
            source="server:work-items:personal", authority="project",
            priority=120, heading="个人工作入口",
        )
        context_layers.add(
            "personal_action_execution",
            "用户明确说处理、开始或执行某个行动项时，使用上一轮结果中的 project_id 与 work_item_id "
            "调用 start_work_item_run；它会创建权威 Server Session/Run。不得在全局默认工作区直接执行该项目任务，"
            "也不得替其他成员启动任务。向用户返回真实 session_id/run_id，交付完成后仍由人工验收。",
            source="server:work-items:execute", authority="project",
            priority=119, heading="任务执行交接",
        )
    if session.project_id and not ask:
        if plan:
            context_layers.add(
                "work_items", "可用 list_work_items 查看本项目的待办及其状态与 id（计划模式下只读，不修改）。",
                source=f"project:{session.project_id}:work_items", authority="project",
                priority=110, heading="项目计划项（待办）",
            )
        elif authoritative_run_context:
            context_layers.add(
                "work_items",
                "这是已启动的 Server WorkItem 项目 Run；可用 list_work_items 只读核对当前计划项。"
                "不要再次启动任务或手动回写状态，Server 会依据 Run 终态和产物校验结果推进生命周期。",
                source=f"project:{session.project_id}:work_items", authority="project",
                priority=110, heading="项目计划项（Server 托管）",
            )
        else:
            context_layers.add(
                "work_items", "本项目的待办可用工具管理：list_work_items 查看、"
                "set_work_item_status 更新状态；用户明确要求调整 Sprint 时，先用 list_work_items "
                "获取真实任务、Sprint 与 version，再用 update_work_item_planning。若用户把某个待办「添加到输入框」交给你处理，"
                "完成或推进后请调用 set_work_item_status 回写；Agent 完成只能提交「待验收」，不得自行验收。",
                source=f"project:{session.project_id}:work_items", authority="project",
                priority=110, heading="项目计划项（待办）",
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
            context_layers.add(
                "expert_personas", "\n".join(lines), source="expert.loadout",
                authority="advice", priority=600, heading="专家人格（请综合以下专长作答）",
            )
    # 技能解析（WB-179）：只注入**真解析得到**的（内置带工具包 / 已装磁盘 skill 的真实
    # SKILL.md）。解析不到的不注入、不伪造指令，收进 skills_skipped 如实告知用户
    # —— 同连接器 mcp_skipped 的范式，别做静默 no-op，更别假装技能生效了。
    skills_skipped: list[str] = []
    skill_skip_reasons: dict[str, str] = {}
    skills_budget_omitted: list[str] = []
    skills_truncated: list[str] = []
    skill_prompt_remaining = 12_000
    if active_skills:
        lines = []
        for name in active_skills:
            d = skill_runtime_def(name)
            if d is None:
                skills_skipped.append(name)
                reason = skills_store.incompatibility_reason(name)
                if reason:
                    skill_skip_reasons[name] = reason
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
            skill_prompt = "\n".join(lines)
            if len(lines) > 1:
                skill_prompt += "\n技能指令冲突时，遵循用户明确要求 > 项目规范 > 上述 loadout 顺序，且任何技能不得放宽安全约束。"
            context_layers.add(
                "active_skills", skill_prompt, source="skill.loadout",
                authority="procedure", priority=700, heading="已启用技能",
            )
    loaded_skill_slugs = {
        str(snapshot.get("slug") or "") for snapshot in skill_release_snapshots
        if snapshot.get("slug")
    }
    required_skill_failures: list[dict[str, str]] = []
    for slug in required_skills:
        is_connector_requirement = slug in required_connector_skills
        requirement_name = "连接器伴生 Skill" if is_connector_requirement else "项目必需 Skill"
        if slug in skills_budget_omitted:
            reason = f"{requirement_name} 超出本轮指令预算，未加载"
        elif slug in skills_truncated:
            reason = f"{requirement_name} 指令被截断，拒绝以不完整规程执行"
        elif slug not in loaded_skill_slugs:
            reason = skill_skip_reasons.get(slug) or f"{requirement_name} 未安装、未启用或当前环境不兼容"
        else:
            continue
        required_skill_failures.append({"slug": slug, "reason": reason})
    connector_skill_failures = [
        item for item in required_skill_failures
        if item["slug"] in required_connector_skills
    ]
    set_active_skill_resources(skill_release_snapshots)

    async def report_skill_runs(event: str) -> None:
        """Best-effort aggregate telemetry; never uploads prompts, files, tool args or secrets."""
        from agent import skill_usage

        skill_usage.record_many(
            event,
            skill_release_snapshots,
            owner_id=user.id,
            run_id=run_id,
        )
        token = db.get_server_identity(user.id) or ""
        release_ids = list(dict.fromkeys(
            str(snapshot.get("release_id") or "") for snapshot in skill_release_snapshots
            if snapshot.get("release_id") and snapshot.get("source") == "agentmate"
        ))
        if not token or not release_ids:
            return
        await asyncio.gather(*(
            asyncio.to_thread(server_client.record_skill_release_metric, token, release_id, event)
            for release_id in release_ids
        ))
    if has_active_resources():
        context_layers.add(
            "skill_resources", "需要 references 或模板时先用 skill_list_resources / "
            "skill_read_resource 按需读取；只有 templates/ 文件可用 skill_copy_template 复制到工作区。"
            "scripts/ 仅可作为文本读取，不得直接执行。",
            source="skill.resources", authority="procedure", priority=710, heading="Skill 资源",
        )

    if active_knowledge and not ask:
        context_layers.add(
            "knowledge", "遇到需要事实性/资料性依据的问题，先用 knowledge_retrieve 检索知识库，"
            "再基于命中内容作答并注明来源；检索不到再用你自己的知识回答。"
            "需要把工作区里的文件或网页 URL 沉淀进知识库（用户说「加入/上传/添加到知识库」）时，用 knowledge_add。",
            source="knowledge.loadout", authority="reference", priority=720,
            heading=f"已挂载知识库（{len(active_knowledge)} 个）",
        )
    elif is_server_project and not ask:
        context_layers.add(
            "knowledge", "本项目的知识库由 Console/Server 统一管理，不需要本机配置 WeKnora。"
            "用户要加入工作区文件或网页 URL 时用 knowledge_add；如果项目还没有知识库，明确引导到 Console 创建。"
            "Server 不可达时如实报告，不得改用用户本地知识库。",
            source="server.project.knowledge", authority="reference", priority=720,
            heading="中央项目知识库",
        )
    elif weknora.configured(user.id) and not ask:
        context_layers.add(
            "knowledge", "本机已接入知识库。用户要把工作区文件或网页 URL「加入/上传/添加到知识库」时，"
            "直接用 knowledge_add（无需先挂载；只有一个库时自动选，多个库用 knowledge_id 或 kb_name 指定）。",
            source="local.knowledge", authority="reference", priority=720, heading="知识库",
        )

    system_prompt = context_layers.render()
    context_manifest = context_layers.manifest()

    offered_skill_slugs = [str(item["slug"]) for item in skill_candidates]
    explicitly_loaded_skill_slugs = [
        str(snapshot.get("slug") or "") for snapshot in skill_release_snapshots
        if snapshot.get("slug")
    ]
    viewed_skill_slugs: list[str] = []

    def skill_compliance_snapshot() -> dict[str, Any]:
        loaded = list(dict.fromkeys(explicitly_loaded_skill_slugs + viewed_skill_slugs))
        return {
            "offered": offered_skill_slugs,
            "required": required_skills,
            "required_project": required_project_skills,
            "required_connector": required_connector_skills,
            "required_loaded": [slug for slug in required_skills if slug in loaded],
            "explicitly_loaded": explicitly_loaded_skill_slugs,
            "viewed_loaded": list(viewed_skill_slugs),
            "loaded": loaded,
            "not_loaded": [slug for slug in offered_skill_slugs if slug not in loaded],
            "matching": "model_semantic_match",
            "gate": "blocked" if required_skill_failures else "passed",
            "gate_failures": required_skill_failures,
        }

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
                lifecycle_note = (
                    "（当前已是权威 Server Run；专注交付，状态由 Server 按 Run 终态自动推进）"
                    if authoritative_run_context else
                    "（处理完成或推进后，调用 set_work_item_status(item_id, status) 回写它的状态）"
                )
                blocks.append(
                    f"【关联待办任务 {name}（计划项 id={r['itemId']}）】\n{body}{note}\n"
                    f"{lifecycle_note}"
                )
            else:
                blocks.append(f"【参考文件 {name}】\n{body}{note}")
        llm_user_text = "\n\n".join(blocks) + "\n\n---\n\n" + user_text

    # Snapshot before persisting this turn: current user text is appended separately,
    # so it cannot be summarized or duplicated in the same request (WB-325).
    history_messages = history_override if history_override is not None else db.list_messages(session_id)
    work_item_id = next(
        (str(ref.get("itemId")) for ref in (refs or []) if ref.get("kind") == "todo" and ref.get("itemId")),
        None,
    )
    try:
        workspace_key = str(current_root().resolve().relative_to(settings.WORKSPACE_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        workspace_key = "default"
    governance_decision = model_governance.policy_decision(
        user.id, model, project_id=session.project_id,
    )
    selected_model_ref = str(governance_decision.get("selected_model_ref") or model or "")
    effective_token_budget = max(0, int(max_total_tokens or 0))
    budget_source = "explicit" if effective_token_budget else "account_default"
    if not effective_token_budget:
        effective_token_budget = db.get_model_default_run_token_budget(user.id)
        if not effective_token_budget:
            budget_source = "disabled"
    hard_remaining_tokens = max(0, int(governance_decision.get("hard_remaining_tokens") or 0))
    if hard_remaining_tokens and (
        not effective_token_budget or hard_remaining_tokens < effective_token_budget
    ):
        effective_token_budget = hard_remaining_tokens
        budget_source = "model_policy_hard_remaining"
    run, created = db.create_run(
        session_id=session_id, owner_id=user.id, project_id=session.project_id,
        work_item_id=work_item_id, mode="ask" if ask else ("plan" if plan else "exec"),
        workspace=workspace_key, idempotency_key=idempotency_key, retry_of=retry_of,
        allow_unmirrored_work_item=bool(project_override and server_token_override),
        permission_snapshot={
            "mode": "ask" if ask else ("plan" if plan else "exec"),
            "experts": active_experts, "skills": active_skills,
            "skill_candidates": [item["slug"] for item in skill_candidates],
            "project_skill_candidates": project_skill_candidates,
            "required_project_skills": required_project_skills,
            "required_connector_skills": required_connector_skills,
            "connector_skill_pairs": connector_skill_pairs,
            "connector_pair_gate": {
                "status": "blocked" if connector_skill_failures else (
                    "pending" if connector_skill_pairs else "passed"
                ),
                "failures": [
                    {
                        "connector": next(
                            (name for name, slug in connector_skill_pairs.items() if slug == item["slug"]),
                            "",
                        ),
                        "skill": item["slug"],
                        "reason": item["reason"],
                    }
                    for item in connector_skill_failures
                ],
            },
            "skill_bundles": bundle_resolution["bundles"],
            "missing_skill_bundles": bundle_resolution["missing_bundles"],
            "missing_bundle_skills": bundle_resolution["missing_skills"],
            "skill_releases": skill_release_snapshots,
            "connectors": active_connectors, "knowledge_ids": active_knowledge,
            "token_budget": effective_token_budget,
            "token_budget_source": budget_source,
            "model_governance": governance_decision,
            "execution_source": execution_source,
            "preauthorized_permissions": sorted(set(preauthorized_permissions or [])),
            "context_layers": context_manifest,
            "skill_compliance": skill_compliance_snapshot(),
        },
    )
    run_id = run.id
    authorization = ExecutionAuthorization(
        owner_id=user.id,
        session_id=session_id,
        source=execution_source if execution_source in {"interactive", "background", "external"} else "interactive",
        preauthorized_permissions=frozenset(preauthorized_permissions or []),
    )
    from agent import skill_usage
    skill_usage.set_context(user.id, run_id)
    if not created:
        clear_skill_candidates()
        skill_usage.clear_context()
        skills_store.set_environment(["adhoc"])
        set_active_skill_resources([])
        yield events.run(run.to_dict())
        yield events.done()
        return
    skill_usage.record_many(
        "offered", skill_candidates, owner_id=user.id, run_id=run_id,
    )
    skill_usage.record_many(
        "loaded", skill_release_snapshots, owner_id=user.id, run_id=run_id,
    )
    user_message = db.add_message(session_id=session_id, role="user", content=user_text, actor=user.id)
    db.touch_session(session_id, status="running")

    stop = asyncio.Event()
    _register_run(session_id, run_id, stop)
    finished_ok = False  # set once the run reaches its normal 'done' (WB-012)
    mcp_stack = None       # defined before the try so `finally` can always close it
    trace_items: list[dict[str, Any]] = []
    assistant_text = ""
    last_prompt = 0
    total_prompt = 0
    total_cached_prompt = 0
    total_completion = 0
    stopped = False
    schemas: list[dict[str, Any]] = []
    tool_call_count = 0
    substantive_actions: list[str] = []
    artifact_paths: list[str] = []
    terminal_handoff = False
    persisted_message_id: str | None = None
    t0 = time.time()

    def record(item: dict[str, Any]) -> str:
        if item.get("kind") in {"plan_snapshot", "plan_patch"}:
            # A RunPlan is state, not an append-only log. Persist only the latest
            # materialized snapshot in the assistant message while still emitting
            # snapshot/patch semantics live over SSE.
            trace_items[:] = [
                existing for existing in trace_items
                if existing.get("kind") not in {"plan_snapshot", "plan_patch", "todo"}
            ]
        trace_items.append(item)
        return _trace_to_sse(item)

    def _persist_partial(error_message: str | None = None) -> str | None:
        # Persist whatever text/trace already streamed before the run errored out,
        # else on reload the user sees their message with no assistant reply at all
        # (WB-160). Best-effort usage (may be approximate on the error path).
        nonlocal persisted_message_id
        if persisted_message_id:
            return persisted_message_id
        if assistant_text.strip() or trace_items or error_message:
            msg = db.add_message(
                session_id=session_id, role="assistant", content=assistant_text,
                actor="assistant", trace=trace_items,
                usage={"prompt": total_prompt or last_prompt, "completion": total_completion or _approx_tokens(assistant_text)},
                run_id=run_id,
                error=error_message,
            )
            persisted_message_id = msg.id
            return persisted_message_id
        return None

    # Once the run is registered, everything runs inside the try so a client
    # disconnect (CancelledError / GeneratorExit) anywhere — including the connector
    # spawn `await` — still hits `finally`: the session status is reset and connector
    # MCP servers are closed, never leaked (WB-012, plus the mcp_stack-outside-try
    # leak noted in WB-023).
    try:
        yield events.run(run.to_dict(), user_message.id)
        yield events.status("running")

        if required_skill_failures:
            detail = "；".join(
                f"{item['slug']}：{item['reason']}" for item in required_skill_failures
            )
            assistant_text = f"执行所需的 Skill 未能完整加载，已在执行前阻断：{detail}"
            yield record({
                "kind": "step", "tool": "skill_preload_gate",
                "label": assistant_text, "status": "blocked",
            })
            yield events.error(assistant_text)
            mid = _persist_partial(assistant_text)
            db.set_run_status(
                run_id, "failed", error_code="required_skill_unavailable",
                error_message=detail,
            )
            db.touch_session(session_id, status="idle")
            finished_ok = True
            yield events.done(mid)
            await report_skill_runs("run_failed")
            return

        policy_notes = list(governance_decision.get("warnings") or [])
        if governance_decision.get("fallback_from"):
            policy_notes.insert(
                0,
                f"Provider 健康门禁：{governance_decision['fallback_from']} → {selected_model_ref}",
            )
        if policy_notes:
            yield record({
                "kind": "step", "tool": "model_governance",
                "label": "；".join(str(note) for note in policy_notes)[:500],
            })

        # Resolve once, then open connectors before context compaction. A summary call
        # uses the same real configured LLM; failure falls back to a bounded recent
        # window and never blocks the actual run for more than the configured timeout.
        if not governance_decision.get("allowed", True):
            raise LLMError(str(governance_decision.get("error") or "模型策略拒绝本次运行"))
        model_id, model_base, model_key, model_path = resolve_model_config(
            user.id, selected_model_ref,
        )
        # A connector with a trusted companion Skill is one atomic execution unit:
        # the Skill gate above and the MCP startup below must both pass before any
        # model request (including history compaction). Unpaired legacy connectors
        # retain their best-effort compatibility behavior.
        mcp_tools = []
        mcp_skipped = connector_mode_skips(active_connectors, plan=plan, ask=ask)
        mcp_permissions = ("connector.call", "external.dynamic")
        connector_authorized = authorization.tool_available(mcp_permissions)
        if active_connectors and not plan and not ask and connector_authorized:
            mcp_tools, mcp_stack, mcp_skipped = await open_connectors(
                active_connectors, env={"AGENTMATE_NOTES_DIR": str(current_root())}, owner_id=user.id,
            )
        elif active_connectors and not plan and not ask and not connector_authorized:
            mcp_skipped.extend(
                {"name": name, "reason": "后台运行未预授权外部连接器"}
                for name in active_connectors
            )
        skipped_by_name = {item["name"]: item["reason"] for item in mcp_skipped}
        connector_pair_failures = [
            {
                "connector": name,
                "skill": skill_slug,
                "reason": skipped_by_name[name],
            }
            for name, skill_slug in connector_skill_pairs.items()
            if name in skipped_by_name
        ]
        db.update_run_runtime(
            run_id,
            permission_snapshot={
                **run.permission_snapshot,
                "connector_skill_pairs": connector_skill_pairs,
                "required_connector_skills": required_connector_skills,
                "connector_pair_gate": {
                    "status": "blocked" if connector_pair_failures else "passed",
                    "failures": connector_pair_failures,
                },
                "connector_skipped": mcp_skipped,
            },
        )
        if connector_pair_failures:
            detail = "；".join(
                f"{item['connector']} + {item['skill']}：{item['reason']}"
                for item in connector_pair_failures
            )
            assistant_text = f"连接器与伴生 Skill 未能原子加载，已在执行前阻断：{detail}"
            yield record({
                "kind": "step", "tool": "connector_skill_gate",
                "label": assistant_text, "status": "blocked",
            })
            yield events.error(assistant_text)
            mid = _persist_partial(assistant_text)
            db.set_run_status(
                run_id, "failed", error_code="connector_pair_unavailable",
                error_message=detail,
            )
            db.touch_session(session_id, status="idle")
            finished_ok = True
            yield events.done(mid)
            await report_skill_runs("run_failed")
            return
        run = db.set_run_model_snapshot(
            run_id,
            model_ref=selected_model_ref,
            model_id=model_id,
            snapshot=model_governance.build_run_snapshot(
                user.id, selected_model_ref, model_id, governance=governance_decision,
            ),
        )
        context_window = max(
            1024,
            int(run.model_snapshot.get("context_window") or settings.CONTEXT_WINDOW),
        )
        model_output_cap = max(
            1,
            int(run.model_snapshot.get("max_output_tokens") or settings.DEFAULT_MAX_OUTPUT_TOKENS),
        )
        context_result = await session_context.build_llm_context(
            session,
            history_messages,
            new_user_text=llm_user_text,
            system_prompt=system_prompt,
            model=model_id,
            api_base=model_base,
            api_key=model_key,
            chat_path=model_path,
            history_token_budget=_history_budget(
                context_window, system_prompt, min(max_output_tokens or model_output_cap, model_output_cap),
            ),
        )
        llm_messages = context_result.messages
        total_prompt += context_result.summary_prompt_tokens
        total_completion += context_result.summary_completion_tokens
        total_cached_prompt += context_result.summary_cached_prompt_tokens
        if context_result.compaction_degraded:
            degradation = {
                "degraded": True,
                "reason": context_result.compaction_reason or "summary_failed",
                "excerpt_messages": context_result.degraded_excerpt_messages,
                "retry_on_next_turn": True,
            }
            db.set_run_status(
                run_id, "running",
                checkpoint=_merge_checkpoint(run_id, context_compaction=degradation),
            )
            yield record({
                "kind": "context_degraded",
                "reason": degradation["reason"],
                "excerpt_messages": degradation["excerpt_messages"],
                "retry_on_next_turn": True,
            })
        if effective_token_budget > 0 and total_prompt + total_completion >= effective_token_budget:
            raise RuntimeBudgetExceeded(
                f"Token budget exhausted by context compaction: "
                f"{total_prompt + total_completion} >= {effective_token_budget}"
            )

        # Active toolset. Ask mode = no tools (pure Q&A). Otherwise base
        # (plan-filtered) tools + skill tools + connector (MCP) tools; connectors
        # spawn their stdio MCP servers now and are closed in `finally`.
        # The personal inbox is globally readable from Server. Project-scoped list/
        # status tools remain available only when this Run belongs to a project.
        wi_tools = (
            work_item_tools(plan, include_project=bool(session.project_id)) if not ask else []
        )
        # 知识库工具（ask 模式无工具）：检索按会话挂载的库（active_knowledge）给；
        # 加入文件只要后端接了 WeKnora（配了 key）就给——不要求先挂载（WB-175）。
        kb_tools = _knowledge_tools(
            user.id, active_knowledge, ask=ask, remote_project=is_server_project,
        )
        # WB-186：skill_tools / kb_tools 从前**完全绕过 plan 过滤**（只有 base_tools 和
        # wi_tools 认 plan）。技能侧当时恰好 3 个工具全只读所以没暴雷；知识库侧却是真漏：
        # knowledge_add 是写（灌文件进库 + 解析/切片/向量化），计划模式下 agent 真能调它。
        # 现在统一按 Tool.plan_safe 过滤（默认 False = 保守，新工具不标注就进不了 plan）。
        mcp_by_name = {t.qualified: t for t in mcp_tools}
        active_tools: dict[str, Tool] = {}
        deferred_candidates = [] if ask else [
            tool for tool in deferred_tools(plan)
            if authorization.tool_available(tool.permissions)
        ]
        deferred_by_name = {tool.name: tool for tool in deferred_candidates}
        loaded_deferred_tools: dict[str, Tool] = {}
        discovery_available = bool(
            deferred_candidates
            and server_tool_enabled(tool_search.name)
            and authorization.tool_available(tool_search.permissions)
        )
        set_deferred_tool_candidates(deferred_candidates if discovery_available else [])

        def refresh_skill_contract() -> None:
            """Rebuild schemas and Run authority after progressive capability loading."""
            nonlocal schemas
            tools_list = [] if ask else (
                base_tools(plan, include_deferred=not discovery_available)
                + ([tool_search] if discovery_available else [])
                + list(loaded_deferred_tools.values())
                + plan_filter(DISCOVERY_TOOLS if skill_candidates else [], plan)
                + plan_filter(skill_tools, plan)
                + plan_filter(RESOURCE_TOOLS if has_active_resources() else [], plan)
                + wi_tools  # work_item_tools(plan) 内部已过滤
                + plan_filter(kb_tools, plan)
            )
            active_tools.clear()
            active_tools.update({
                tool.name: tool for tool in tools_list
                if authorization.tool_available(tool.permissions)
            })
            schemas = (
                # 从 active_tools（已按名去重）生成，而非 tools_list，避免同名 schema。
                [tool.schema() for tool in active_tools.values()]
                + [mcp_schema(tool) for tool in mcp_tools]
                + ([] if ask or not server_tool_enabled("ask_user") else [ASK_USER_SCHEMA])
            )
            db.update_run_runtime(
                run_id,
                permission_snapshot={
                    **run.permission_snapshot,
                    "skills": list(active_skills),
                    "skill_candidates": [item["slug"] for item in skill_candidates],
                    "skill_compliance": skill_compliance_snapshot(),
                    "project_skill_candidates": project_skill_candidates,
                    "skill_releases": list(skill_release_snapshots),
                    "tools": sorted(active_tools),
                    "deferred_tool_candidates": sorted(deferred_by_name),
                    "deferred_tools_loaded": sorted(loaded_deferred_tools),
                    "tool_discovery": "tool_search" if discovery_available else "legacy_direct",
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

        refresh_skill_contract()

        def validate_viewed_skill(outcome: ToolOutcome) -> tuple[ToolOutcome, dict[str, Any] | None]:
            """Validate a skill_view trace in the parent context without granting authority yet."""
            event = next(
                (
                    item for item in outcome.trace
                    if item.get("kind") == "step"
                    and item.get("tool") == "skill_view"
                    and item.get("slug")
                ),
                None,
            )
            if not event:
                return outcome, None
            slug = str(event["slug"])
            candidate = candidate_map().get(slug)
            definition = skill_runtime_def(slug) if candidate else None
            if not definition:
                return ToolOutcome(
                    text=f"Skill 加载验证失败，未授予任何新能力：{slug}",
                    trace=[{
                        "kind": "step", "tool": "skill_view",
                        "label": f"技能加载失败 · {slug}", "status": "error",
                    }],
                ), None
            snapshot = dict(definition["snapshot"])
            if (
                str(snapshot.get("release_id") or "") != str(event.get("release_id") or "")
                or str(snapshot.get("content_hash") or "") != str(event.get("content_hash") or "")
            ):
                return ToolOutcome(
                    text=f"Skill 在加载期间发生版本变化，未授予任何新能力：{slug}",
                    trace=[{
                        "kind": "step", "tool": "skill_view",
                        "label": f"技能版本变化 · {slug}", "status": "error",
                    }],
                ), None
            return outcome, definition

        def activate_viewed_skills(definitions: list[dict[str, Any]]) -> None:
            """Apply validated definitions between LLM rounds, then rebuild schemas once."""
            changed = False
            existing = {
                (
                    str(snapshot.get("slug") or ""),
                    str(snapshot.get("release_id") or ""),
                    str(snapshot.get("content_hash") or ""),
                )
                for snapshot in skill_release_snapshots
            }
            for definition in definitions:
                snapshot = dict(definition["snapshot"])
                identity = (
                    str(snapshot.get("slug") or ""),
                    str(snapshot.get("release_id") or ""),
                    str(snapshot.get("content_hash") or ""),
                )
                if identity in existing:
                    continue
                existing.add(identity)
                slug = identity[0]
                if slug and slug not in active_skills:
                    active_skills.append(slug)
                if slug and slug not in viewed_skill_slugs:
                    viewed_skill_slugs.append(slug)
                skill_tools.extend(definition["tools"])
                skill_release_snapshots.append(snapshot)
                skill_usage.record(
                    "loaded",
                    snapshot,
                    owner_id=user.id,
                    run_id=run_id,
                )
                changed = True
            if changed:
                set_active_skill_resources(skill_release_snapshots)
                refresh_skill_contract()

        def validate_tool_search(outcome: ToolOutcome) -> tuple[ToolOutcome, list[Tool]]:
            event = next(
                (
                    item for item in outcome.trace
                    if item.get("kind") == "step" and item.get("tool") == "tool_search"
                ),
                None,
            )
            raw_names = event.get("loaded_tools") if event else None
            if not isinstance(raw_names, list):
                return outcome, []
            selected: list[Tool] = []
            for raw_name in raw_names:
                name = str(raw_name)
                tool = deferred_by_name.get(name)
                if tool is None or name in loaded_deferred_tools:
                    continue
                selected.append(tool)
            return outcome, selected

        def activate_deferred_tools(values: list[Tool]) -> None:
            changed = False
            for tool in values:
                if tool.name not in loaded_deferred_tools:
                    loaded_deferred_tools[tool.name] = tool
                    changed = True
            if changed:
                refresh_skill_contract()

        # Show the loadout so the persona / skills / connectors that shaped this
        # run are visible — including connectors that were selected but couldn't
        # load (e.g. GitHub without a token), so it isn't a silent no-op.
        connector_names = sorted({t.connector for t in mcp_tools})
        loaded_skills = [
            skill_display_name(n) for n in active_skills
            if n not in skills_skipped and n not in skills_budget_omitted
        ]
        ready_candidate_slugs = {item["slug"] for item in skill_candidates}
        project_candidates_ready = [
            slug for slug in project_skill_candidates if slug in ready_candidate_slugs
        ]
        project_candidates_skipped = [
            slug for slug in project_skill_candidates if slug not in ready_candidate_slugs
        ]
        if (
            active_experts or active_skills or project_skill_candidates or bundle_ids
            or connector_names or mcp_skipped or (active_knowledge and not ask)
        ):
            parts = []
            if loaded_experts:
                parts.append("专家 " + "、".join(loaded_experts))
            if loaded_skills:
                parts.append("技能 " + "、".join(loaded_skills))
            if bundle_resolution["bundles"]:
                parts.append(
                    "技能组合 " + "、".join(item["name"] for item in bundle_resolution["bundles"])
                )
            if bundle_resolution["missing_bundles"]:
                parts.append(
                    "技能组合不存在 " + "、".join(bundle_resolution["missing_bundles"])
                )
            if bundle_resolution["missing_skills"]:
                parts.append(
                    "组合内技能缺失 " + "、".join(
                        f"{item['bundle_name']}:{item['skill']}"
                        for item in bundle_resolution["missing_skills"]
                    )
                )
            if project_candidates_ready:
                parts.append(f"项目候选技能 {len(project_candidates_ready)} 个（按需加载）")
            if project_candidates_skipped:
                parts.append("项目候选技能未就绪 " + "、".join(
                    skill_display_name(slug) for slug in project_candidates_skipped
                ))
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
                    f"{skill_display_name(n)}（{skill_skip_reasons.get(n) or '未安装或已停用'}）"
                    for n in skills_skipped
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

            estimated_round_prompt = sum(
                _approx_tokens(str(message.get("content") or "")) + 4
                for message in llm_messages
            ) + _approx_tokens(json.dumps(schemas, ensure_ascii=False))
            context_output_room = context_window - estimated_round_prompt
            if context_output_room <= 0:
                raise RuntimeBudgetExceeded(
                    f"Model context exhausted before generation: "
                    f"{estimated_round_prompt} >= {context_window}"
                )
            run_output_room: int | None = None
            if effective_token_budget > 0:
                run_output_room = (
                    effective_token_budget
                    - total_prompt
                    - total_completion
                    - estimated_round_prompt
                )
                if run_output_room <= 0:
                    raise RuntimeBudgetExceeded(
                        "Token budget exhausted before generation: "
                        f"estimated input {estimated_round_prompt}, remaining "
                        f"{effective_token_budget - total_prompt - total_completion}"
                    )
            request_max_tokens = _request_output_limit(
                requested=max_output_tokens,
                model_cap=model_output_cap,
                context_room=context_output_room,
                run_room=run_output_room,
            )

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
                    max_tokens=max(1, request_max_tokens),
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
                            total_cached_prompt += _cached_prompt_tokens(delta.usage)
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
            if effective_token_budget > 0 and total_prompt + total_completion > effective_token_budget:
                raise RuntimeBudgetExceeded(
                    f"Token budget exceeded: {total_prompt + total_completion} > {effective_token_budget}"
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

            pending_skill_defs: list[dict[str, Any]] = []
            pending_deferred_tools: list[Tool] = []
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
                        db.touch_session(session_id, status="waiting")
                        db.set_run_status(
                            run_id, "waiting_approval",
                            checkpoint=_merge_checkpoint(
                                run_id,
                                **_question_checkpoint(
                                    questions, source="agent", tool_call_id=call["id"],
                                ),
                            ),
                        )
                        yield events.ask_user(questions)
                        await ev.wait()
                        pending = _answers.pop(run_id, None)
                        answers = (pending or {}).get("answers")
                        db.touch_session(session_id, status="running")
                        if not stop.is_set() and answers is not None:
                            db.set_run_status(
                                run_id, "running",
                                checkpoint=_without_pending_question(run_id),
                            )
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
                            decision = authorization.decision(name, args, mcp_permissions)
                            if decision == "confirm":
                                # Connector calls are not currently in the interactive
                                # confirmation set, but keep the boundary complete for
                                # future permission classifications.
                                raise ToolAuthorizationDenied(f"confirmation required: {name}")
                            result = await execute_async_call(
                                call_mcp(mt, args), stop, 60,
                                authorization=authorization, tool_name=name, args=args,
                                permissions=mcp_permissions,
                            )
                            tool_trace.update(output=result)
                        except ToolAuthorizationDenied:
                            result = "连接器调用被运行权限策略拒绝。"
                            yield record({"kind": "step", "tool": name, "label": result, "status": "blocked"})
                            tool_trace.update(output={"status": "blocked"})
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
                tool_completed = False
                decision = authorization.decision(name, args, tool.permissions)
                if decision == "confirm":
                    questions = [{
                        "q": f"工具「{name}」请求高风险权限：{', '.join(tool.permissions)}。请选择授权范围。",
                        "options": list(TOOL_AUTHORIZATION_OPTIONS),
                    }]
                    ev = asyncio.Event()
                    _answers[run_id] = {"ev": ev, "answers": None}
                    db.touch_session(session_id, status="waiting")
                    db.set_run_status(
                        run_id, "waiting_approval",
                        checkpoint=_merge_checkpoint(
                            run_id,
                            **_question_checkpoint(
                                questions, source="tool_authorization",
                                tool_call_id=call["id"], tool_name=name,
                            ),
                        ),
                    )
                    yield events.ask_user(questions)
                    await ev.wait()
                    pending = _answers.pop(run_id, None)
                    answers = (pending or {}).get("answers") or []
                    db.touch_session(session_id, status="running")
                    answer = answers[0] if answers else ""
                    if not stop.is_set() and answer in {ALLOW_ONCE_ANSWER, ALLOW_SESSION_ANSWER}:
                        if answer == ALLOW_SESSION_ANSWER:
                            authorization.approve_for_session(tool.permissions)
                        else:
                            authorization.approve_once(name, args)
                        db.set_run_status(
                            run_id, "running",
                            checkpoint=_without_pending_question(run_id),
                        )
                    else:
                        outcome = ToolOutcome(text=f"工具 {name} 未获本次授权。")
                        yield record({"kind": "step", "tool": name, "label": outcome.text, "status": "blocked"})
                        llm_messages.append({"role": "tool", "tool_call_id": call["id"], "content": outcome.text})
                        if stop.is_set():
                            stopped = True
                            break
                        continue
                elif decision == "deny":
                    outcome = ToolOutcome(text=f"工具 {name} 未获后台预授权。")
                    yield record({"kind": "step", "tool": name, "label": outcome.text, "status": "blocked"})
                    llm_messages.append({"role": "tool", "tool_call_id": call["id"], "content": outcome.text})
                    continue
                # Run the (synchronous) tool off the event loop so a long
                # subprocess / web_fetch / file IO can't freeze every other SSE
                # stream or block /stop for its whole timeout (WB-002). to_thread
                # copies the contextvars, so the sandbox root stays correct.
                with telemetry.tool_observation(
                    name=name, arguments=args, source="builtin",
                ) as tool_trace:
                    try:
                        # Discovery is bounded local metadata/disk access and must run
                        # in the parent context: a worker-thread SQLite connection
                        # would outlive the call on Windows, and ContextVar mutations
                        # must never be mistaken for runtime authority changes.
                        outcome = (
                            run_tool(tool, args)
                            if name in {"skills_list", "skill_view", "tool_search"}
                            else await execute_tool(tool, args, stop, authorization=authorization)
                        )
                        tool_completed = True
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
                    except ToolAuthorizationDenied:
                        outcome = ToolOutcome(text=f"工具 {name} 被运行权限策略拒绝。")
                        yield record({"kind": "step", "tool": name, "label": outcome.text, "status": "blocked"})
                        tool_trace.update(output={"status": "blocked"})
                if name == "skill_view" and tool_completed and not stopped:
                    outcome, definition = validate_viewed_skill(outcome)
                    if definition:
                        pending_skill_defs.append(definition)
                if name == "tool_search" and tool_completed and not stopped:
                    outcome, selected_tools = validate_tool_search(outcome)
                    pending_deferred_tools.extend(selected_tools)
                if tool_completed and not stopped and any(
                    permission.endswith(".write") for permission in tool.permissions
                ):
                    substantive_actions.append(name)
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
                            is_primary=True if descriptor.get("is_primary") is True else None,
                            display_order=(
                                int(descriptor["display_order"])
                                if isinstance(descriptor.get("display_order"), int) else None
                            ),
                        )
                    except (FileNotFoundError, PermissionError, ValueError):
                        continue
                    yield record({
                        "kind": "artifact", "id": artifact.id, "run_id": run_id,
                        "name": artifact.name, "size": str(artifact.size), "path": artifact.path,
                        "sha256": artifact.sha256, "mime_type": artifact.mime_type,
                        "is_primary": artifact.is_primary, "display_order": artifact.display_order,
                        "acceptance_status": artifact.acceptance_status,
                    })
                    artifact_paths.append(artifact.path)
                # Transient live events (WB-031: kanban sync) — emitted, not recorded,
                # so history replay never re-fires a stale state change.
                for ev in outcome.live:
                    yield events.work_item(ev)
                llm_messages.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": outcome.text}
                )
                if tool_completed and outcome.terminal:
                    # start_work_item_run is an authority transfer, not another
                    # reasoning step.  End the global Run immediately so sibling
                    # or later model calls cannot execute the project task in the
                    # default workspace after the Server Run has been created.
                    terminal_handoff = True
                    assistant_text += outcome.text
                    yield events.text(outcome.text)
                    break
                if stopped:
                    break
            if stopped or terminal_handoff:
                break
            # Dynamic Skill tools/resources become visible only in the next LLM
            # round, never to sibling calls from the batch that requested skill_view.
            activate_viewed_skills(pending_skill_defs)
            # Deferred schemas obey the same batch boundary: a sibling call cannot
            # use a tool that tool_search discovered in this batch.
            activate_deferred_tools(pending_deferred_tools)
            # loop again so the model can use the results
        delivery_summary = build_delivery_summary(db.list_artifacts(run_id), stopped=stopped)
        if delivery_summary:
            assistant_text += delivery_summary
            yield events.text(delivery_summary)
        finished_ok = True  # loop completed normally (incl. user-stop)
    except RuntimeBudgetExceeded as e:
        chat_trace.update(
            output={"status": "token_budget_exceeded", "partial_chars": len(assistant_text)},
            level="ERROR", status_message=str(e),
        )
        yield events.error("本次运行已达到 token 上限")
        mid = _persist_partial("本次运行已达到 token 上限")
        db.update_run_runtime(
            run_id, prompt_tokens=total_prompt or last_prompt,
            cached_prompt_tokens=total_cached_prompt,
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
        mid = _persist_partial(str(e))  # 保留已流式的半截回复（WB-160）
        db.update_run_runtime(run_id, prompt_tokens=total_prompt or last_prompt, cached_prompt_tokens=total_cached_prompt, completion_tokens=total_completion, tool_calls=tool_call_count)
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
        mid = _persist_partial(f"执行出错：{e}")  # 保留已流式的半截回复（WB-160）
        db.update_run_runtime(run_id, prompt_tokens=total_prompt or last_prompt, cached_prompt_tokens=total_cached_prompt, completion_tokens=total_completion, tool_calls=tool_call_count)
        db.set_run_status(run_id, "failed", error_code="runtime_error", error_message=str(e))
        db.touch_session(session_id, status="idle")
        finished_ok = True
        yield events.done(mid)
        await report_skill_runs("run_failed")
        return
    finally:
        _unregister_run(session_id, run_id)
        clear_skill_candidates()
        set_deferred_tool_candidates([])
        skill_usage.clear_context()
        skills_store.set_environment(["adhoc"])
        set_active_skill_resources([])
        # If the run never reached a normal finish (client disconnect →
        # CancelledError, a BaseException that skips `except Exception`), leave the
        # session 'idle' instead of a phantom 'running'/'waiting' (WB-012).
        if not finished_ok:
            db.touch_session(session_id, status="idle")
            current_run = db.get_run(run_id)
            if current_run and current_run.status in {"planning", "running", "waiting_approval"}:
                try:
                    db.set_run_status(
                        run_id, "paused",
                        checkpoint=_merge_checkpoint(run_id, reason="stream_disconnected"),
                    )
                    _persist_partial("运行已暂停，可重试")
                except ValueError:
                    db.set_run_status(run_id, "cancelled", error_code="stream_disconnected")
                    _persist_partial("运行已取消，可重试")
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
            run_id=run_id,
        )
        message_id = msg.id

    db.update_run_runtime(
        run_id,
        prompt_tokens=total_prompt, cached_prompt_tokens=total_cached_prompt,
        completion_tokens=total_completion, tool_calls=tool_call_count,
    )
    db.set_run_status(
        run_id, "cancelled" if stopped else "completed",
        checkpoint=_without_pending_question(run_id),
    )

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

    yield _usage_event(total_prompt, total_completion, schemas, system_prompt, context_window)
    yield events.status("done", secs=secs)
    if stopped:
        yield events.text("\n\n_（已停止生成）_")
    yield events.done(message_id)
    await report_skill_runs("run_failed" if stopped else "run_succeeded")

    # WorkBuddy 式工作空间日志（WB-324）：仅记录真实完成且执行过写操作的项目 run。
    # 搜索/读文件/计划/纯问答/失败或中止不写；内容来自本次真实 request/tool/artifact/result，不造摘要。
    try:
        workspace_memory.record_completed_run(
                session.project_id,
                stopped=stopped,
                session_id=session_id,
                run_id=run_id,
                title=session.title,
                user_text=user_text,
                assistant_text=assistant_text,
                actions=substantive_actions,
                artifacts=artifact_paths,
            )
    except Exception:  # noqa: BLE001 — 日志是 best-effort，不反向破坏已完成 run
        pass

    # 对话记忆自动抽取（WB-148）：用户在「设置 · 记忆」开启后，从这轮对话提炼可长期记住的用户事实，
    # 去重入库，供之后对话注入。**放在 done 之后**——前端已解锁，不被抽取往返拖住；`wait_for` 兜底，
    # 防抽取端点卡死（stream_chat read 超时为 None）把连接/生成器无限期挂住。best-effort，任何失败静默。
    if assistant_text.strip() and memory.capture_enabled(user.id):
        try:
            await asyncio.wait_for(
                memory.extract_and_store(
                    user.id, user_text, assistant_text,
                    model=model_id, api_base=model_base, api_key=model_key, chat_path=model_path,
                    project_id=session.project_id,
                ),
                timeout=30,
            )
            # 衰退 GC（WB-166）：抽取后顺手归档强度过低的旧记忆（软状态，不硬删）。纯 DB、快，best-effort。
            memory.decay_gc(user.id, project_id=session.project_id)
        except Exception:  # noqa: BLE001 —— 含 asyncio.TimeoutError
            pass
