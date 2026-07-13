"""Agent tools — real operations inside the workspace sandbox (spec 5.3).

Each tool exposes an OpenAI function schema plus an executor. Executors run
strictly within `workspace/` (spec 8, hard-line #2) and return a result string
plus trace items. The runtime turns those into typed SSE events
(step / file_read / diff / todo) — so the koda-style trace is driven by REAL
tool calls, not a script.

`run_command` is powerful and NOT a real sandbox (WB-014): cwd is pinned to the
workspace and there's a hard timeout, but the command itself runs with the
backend's own privileges — it can read/write outside the workspace, reach the
network, and install packages. It is safe only because the server binds
127.0.0.1 (see config HOST); do not expose the backend. M4 will gate risky
commands behind ask_user authorization.
"""
from __future__ import annotations

import contextvars
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable

from agent import security
from agent.sandbox import SandboxError, current_root, relpath, resolve_in_sandbox
from storage import db

MAX_OUTPUT = 6000
CMD_TIMEOUT = 30


@dataclass
class ToolOutcome:
    """What a tool execution produced: text fed back to the LLM + trace items.

    `live` holds transient SSE payloads the runtime emits but does NOT persist in
    the trace (WB-031) — e.g. a plan-item status change the kanban syncs live,
    which must not be re-fired on history replay.
    """
    text: str
    trace: list[dict[str, Any]] = field(default_factory=list)
    live: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    # Trace item shown BEFORE execution (pulses while running); None = none.
    pre: Callable[[dict[str, Any]], dict[str, Any] | None]
    # Executes the tool; returns result text + any POST trace items (e.g. diff).
    run: Callable[[dict[str, Any]], ToolOutcome]

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _truncate(s: str) -> str:
    return s if len(s) <= MAX_OUTPUT else s[:MAX_OUTPUT] + f"\n… [截断，共 {len(s)} 字符]"


# ---- list_dir -----------------------------------------------------------

def _list_dir_run(args: dict[str, Any]) -> ToolOutcome:
    path = args.get("path", ".") or "."
    target = resolve_in_sandbox(path)
    if not target.exists() or not target.is_dir():
        return ToolOutcome(text=f"目录不存在：{path}")
    rows = []
    for child in sorted(target.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        rows.append(("📄 " if child.is_file() else "📁 ") + child.name)
    listing = "\n".join(rows) if rows else "（空目录）"
    return ToolOutcome(text=f"{relpath(target) or '.'}:\n{listing}")


list_dir = Tool(
    name="list_dir",
    description="列出工作区某个目录下的文件与子目录。path 相对工作区根目录，默认根目录。",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "相对工作区的目录路径，默认 '.'"}},
    },
    pre=lambda a: {"kind": "step", "tool": "list_dir", "label": f"查看目录 {a.get('path', '.') or '.'}"},
    run=_list_dir_run,
)


# ---- read_file ----------------------------------------------------------

def _read_file_run(args: dict[str, Any]) -> ToolOutcome:
    path = args["path"]
    target = resolve_in_sandbox(path)
    if not target.exists() or not target.is_file():
        return ToolOutcome(text=f"文件不存在：{path}")
    content = target.read_text(encoding="utf-8", errors="replace")
    return ToolOutcome(text=_truncate(content))


read_file = Tool(
    name="read_file",
    description="读取工作区内某个文本文件的内容。path 相对工作区根目录。",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "相对工作区的文件路径"}},
        "required": ["path"],
    },
    pre=lambda a: {"kind": "file_read", "path": a.get("path", ""), "range": "全文"},
    run=_read_file_run,
)


# ---- write_file ---------------------------------------------------------

def _write_file_run(args: dict[str, Any]) -> ToolOutcome:
    path = args["path"]
    content = args.get("content", "")
    target = resolve_in_sandbox(path)
    existed = target.exists()
    old = target.read_text(encoding="utf-8", errors="replace") if existed else ""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    old_lines = old.splitlines()
    new_lines = content.splitlines()
    # Simple line delta (added = new beyond common length + changed tail).
    added = max(0, len(new_lines) - len(old_lines)) if existed else len(new_lines)
    deleted = max(0, len(old_lines) - len(new_lines)) if existed else 0
    # Count changed lines within the overlap as add+del.
    changed = sum(1 for a, b in zip(old_lines, new_lines) if a != b)
    added += changed
    deleted += changed
    op = "编辑" if existed else "创建"
    return ToolOutcome(
        text=f"已{op} {relpath(target)}（+{added} -{deleted}）",
        trace=[{"kind": "diff", "op": op, "file": relpath(target), "add": added, "del": deleted}],
    )


write_file = Tool(
    name="write_file",
    description="在工作区创建或覆盖一个文本文件。会记录为一条变更（diff）。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "相对工作区的文件路径"},
            "content": {"type": "string", "description": "文件完整内容"},
        },
        "required": ["path", "content"],
    },
    pre=lambda a: None,
    run=_write_file_run,
)


# ---- run_command --------------------------------------------------------

def _run_command_run(args: dict[str, Any]) -> ToolOutcome:
    command = args["command"]
    # 命令安全策略（WB-152）：命中用户配置的黑名单则真拦截、不执行、记审计。
    owner = security.current_owner()
    allowed, pattern = security.check_command(command, owner)
    if not allowed:
        security.audit(owner, "run_command", command, "blocked")
        return ToolOutcome(text=f"命令被安全策略拦截（命中规则「{pattern}」）：{command}\n如确需执行，请到「设置 · 安全中心」移除该规则。")
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(current_root()),
            capture_output=True,
            text=True,
            timeout=CMD_TIMEOUT,
        )
        security.audit(owner, "run_command", command, "executed")
        out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
        out = out.strip() or "（无输出）"
        return ToolOutcome(text=f"退出码 {proc.returncode}\n{_truncate(out)}")
    except subprocess.TimeoutExpired:
        security.audit(owner, "run_command", command, "executed")
        return ToolOutcome(text=f"命令超时（>{CMD_TIMEOUT}s）：{command}")
    except Exception as e:  # noqa: BLE001
        return ToolOutcome(text=f"命令执行失败：{e}")


run_command = Tool(
    name="run_command",
    description=(
        "在工作区目录内运行一条 shell 命令并返回输出（工作目录固定在工作区、有超时）。"
        "注意：这不是真正的沙箱——命令以后端自身权限执行，可访问本机任意路径与网络，"
        "请仅执行必要且可信的命令。"
    ),
    parameters={
        "type": "object",
        "properties": {"command": {"type": "string", "description": "要执行的命令"}},
        "required": ["command"],
    },
    pre=lambda a: {"kind": "step", "tool": "run_command", "label": f"运行命令 {a.get('command', '')[:80]}"},
    run=_run_command_run,
)


# ---- update_plan (todos) ------------------------------------------------

def _update_plan_run(args: dict[str, Any]) -> ToolOutcome:
    todos = args.get("todos", []) or []
    trace = [{"kind": "todo", "text": str(t)} for t in todos]
    return ToolOutcome(text=f"已更新执行计划（{len(todos)} 项）", trace=trace)


update_plan = Tool(
    name="update_plan",
    description="更新当前任务的待办清单（todo）。用于把多步任务拆解并展示进度。",
    parameters={
        "type": "object",
        "properties": {
            "todos": {"type": "array", "items": {"type": "string"}, "description": "待办事项文本列表"}
        },
        "required": ["todos"],
    },
    pre=lambda a: None,
    run=_update_plan_run,
)


# ---- work items (计划项) — §11 阶段 B+ / WB-030 -------------------------
#
# Let the agent see and transition the current project's plan items (待办). Like
# the sandbox root, the active project/owner is a contextvar set per run by
# run_chat; the tools read it (so their signatures stay pure and concurrent runs
# stay isolated). Only added to the toolset when the run belongs to a project.

_work_ctx: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar("work_ctx", default=None)

# Accept both the en status keys and the Chinese labels the model is likely to emit.
_WI_STATUS = {
    "todo": "todo", "待开始": "todo", "待办": "todo",
    "doing": "doing", "进行中": "doing",
    "paused": "paused", "暂停": "paused", "已暂停": "paused",
    "done": "done", "完成": "done", "已完成": "done",
}
_WI_LABEL = {"todo": "待开始", "doing": "进行中", "paused": "暂停", "done": "完成"}


def set_work_context(project_id: str | None, owner_id: str | None) -> None:
    """Set the active project/owner for work-item tools (run_chat calls this)."""
    _work_ctx.set({"project_id": project_id, "owner_id": owner_id} if project_id and owner_id else None)


def _list_work_items_run(args: dict[str, Any]) -> ToolOutcome:
    ctx = _work_ctx.get()
    if not ctx:
        return ToolOutcome(text="当前不在项目中，没有计划项可列。")
    items = db.list_work_items(ctx["project_id"])
    if not items:
        return ToolOutcome(text="本项目暂无计划项（待办）。")
    lines = [f"- [{_WI_LABEL.get(i.status, i.status)}] {i.title}（id={i.id}）" for i in items]
    return ToolOutcome(text="本项目计划项：\n" + "\n".join(lines))


list_work_items = Tool(
    name="list_work_items",
    description="列出当前项目的计划项（待办）及其状态与 id。改状态前可用它拿到 item_id。",
    parameters={"type": "object", "properties": {}},
    pre=lambda a: {"kind": "step", "tool": "list_work_items", "label": "查看项目计划项"},
    run=_list_work_items_run,
)


def _set_work_item_status_run(args: dict[str, Any]) -> ToolOutcome:
    ctx = _work_ctx.get()
    if not ctx:
        return ToolOutcome(text="当前不在项目中，无法修改计划项。")
    item_id = str(args.get("item_id", "")).strip()
    raw = str(args.get("status", "")).strip()
    status = _WI_STATUS.get(raw) or _WI_STATUS.get(raw.lower())
    if not status:
        return ToolOutcome(text=f"未知状态「{raw}」。可用：待开始 / 进行中 / 暂停 / 完成。")
    # Owner + project scoping: only touch items the caller owns in THIS project.
    wi = db.get_work_item(item_id, owner_id=ctx["owner_id"])
    if not wi or wi.project_id != ctx["project_id"]:
        return ToolOutcome(text=f"未找到计划项 id={item_id}（或不属于当前项目）。可先用 list_work_items 核对 id。")
    db.update_work_item(item_id, status=status)
    label = _WI_LABEL.get(status, status)
    return ToolOutcome(
        text=f"已将计划项「{wi.title}」状态改为「{label}」。",
        trace=[{"kind": "step", "tool": "set_work_item_status", "label": f"计划项「{wi.title}」→ {label}"}],
        # Transient live sync for the kanban (WB-031) — not persisted in the trace.
        live=[{"id": wi.id, "project_id": wi.project_id, "status": status, "title": wi.title}],
    )


set_work_item_status = Tool(
    name="set_work_item_status",
    description=(
        "修改当前项目某个计划项（待办）的状态。item_id 来自任务引用或 list_work_items；"
        "status 取 待开始 / 进行中 / 暂停 / 完成 之一。完成或推进了关联待办后应调用它回写状态。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "item_id": {"type": "string", "description": "计划项 id"},
            "status": {"type": "string", "description": "目标状态：待开始 / 进行中 / 暂停 / 完成"},
        },
        "required": ["item_id", "status"],
    },
    pre=lambda a: None,
    run=_set_work_item_status_run,
)


def work_item_tools(plan: bool = False) -> list[Tool]:
    """Work-item tools for a run. Plan mode is read-only, so no status writes."""
    return [list_work_items] if plan else [list_work_items, set_work_item_status]


# ---- knowledge_retrieve（知识库检索）— WB-143 -----------------------------
#
# 会话挂载的 GLM 知识库检索。与 work-item 同款 contextvar 注入：owner + 选中的
# knowledge_ids 由 run_chat 每次运行前 set；工具真调 GLM 检索（同步，由 runtime 的
# asyncio.to_thread 兜住）。key 只在本地：db.get_provider_key(owner, "zhipu")，绝不回前端。

_kb_ctx: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("kb_ctx", default=None)


def set_knowledge_context(owner_id: str | None, knowledge_ids: list[str] | None) -> None:
    """Set the active owner + mounted knowledge base ids for this run (run_chat calls it)."""
    _kb_ctx.set({"owner_id": owner_id, "knowledge_ids": knowledge_ids} if owner_id and knowledge_ids else None)


def _knowledge_retrieve_run(args: dict[str, Any]) -> ToolOutcome:
    from agent import glm_kb  # 延迟导入，避免与加载顺序耦合

    ctx = _kb_ctx.get()
    if not ctx:
        return ToolOutcome(text="当前会话未挂载任何知识库。")
    query = str(args.get("query", "")).strip()
    if not query:
        return ToolOutcome(text="请提供检索问题（query）。")
    key = db.get_provider_key(ctx["owner_id"], "zhipu")
    if not key:
        return ToolOutcome(text="未配置智谱 API Key，无法检索知识库（去「模型管理」为「智谱 AI·GLM」配置）。")
    try:
        top_k = int(args.get("top_k") or 8)
    except (TypeError, ValueError):
        top_k = 8
    try:
        hits = glm_kb.retrieve(key, query=query, knowledge_ids=ctx["knowledge_ids"], top_k=max(1, min(top_k, 20)))
    except glm_kb.GlmKbError as e:
        return ToolOutcome(text=f"知识库检索失败：{e}")
    if not hits:
        return ToolOutcome(text=f"知识库中未检索到与「{query}」相关的内容。")
    lines = [f"检索到 {len(hits)} 条相关内容（按相关度）："]
    for i, h in enumerate(hits, 1):
        meta = h.get("metadata") or {}
        doc = meta.get("doc_name") or meta.get("doc_id") or "未知来源"
        score = h.get("score")
        text = str(h.get("text") or "").strip()
        head = f"\n[{i}] 来源：{doc}" + (f"（相关度 {score:.3f}）" if isinstance(score, (int, float)) else "")
        lines.append(head + "\n" + _truncate(text))
    return ToolOutcome(text="\n".join(lines))


knowledge_retrieve = Tool(
    name="knowledge_retrieve",
    description=(
        "检索本会话挂载的知识库，返回最相关的资料片段（含来源文档名）。"
        "遇到需要事实性/资料性依据的问题时先检索，再基于命中内容作答并注明来源。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索问题/关键词"},
            "top_k": {"type": "integer", "description": "返回条数上限（1-20，默认 8）"},
        },
        "required": ["query"],
    },
    pre=lambda a: {"kind": "step", "tool": "knowledge_retrieve", "label": f"检索知识库 {str(a.get('query', ''))[:60]}"},
    run=_knowledge_retrieve_run,
)


TOOLS: list[Tool] = [list_dir, read_file, write_file, run_command, update_plan]
_BY_NAME = {t.name: t for t in TOOLS}

# ask_user is not a pure function — the runtime suspends on it and resumes when
# the user answers (spec 5.3). Its schema is exposed to the model; execution is
# special-cased in the runtime, not dispatched through safe_run.
ASK_USER_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "ask_user",
        "description": (
            "当需要用户澄清关键决策时，向用户提出 1-3 个选择题并等待回答后再继续。"
            "计划模式下，遇到影响方向的决策务必用它与用户确认。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "q": {"type": "string", "description": "问题文本"},
                            "options": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "2-4 个候选答案",
                            },
                        },
                        "required": ["q", "options"],
                    },
                }
            },
            "required": ["questions"],
        },
    },
}

# Plan mode = read-only tools + ask_user (no write_file / run_command).
_PLAN_TOOLS = {"list_dir", "read_file", "update_plan"}


def base_tools(plan: bool = False) -> list[Tool]:
    return [t for t in TOOLS if (t.name in _PLAN_TOOLS)] if plan else list(TOOLS)


def build_schemas(tools: list[Tool]) -> list[dict[str, Any]]:
    """OpenAI tool schemas for a concrete toolset + the special ask_user schema."""
    return [t.schema() for t in tools] + [ASK_USER_SCHEMA]


def tool_schemas(plan: bool = False) -> list[dict[str, Any]]:
    return build_schemas(base_tools(plan))


def run_tool(tool: Tool, args: dict[str, Any]) -> ToolOutcome:
    """Execute a concrete Tool (base or skill-provided) with error capture."""
    try:
        return tool.run(args)
    except SandboxError as e:
        return ToolOutcome(text=f"沙箱拒绝：{e}")
    except Exception as e:  # noqa: BLE001
        return ToolOutcome(text=f"工具出错：{e}")


def get_tool(name: str) -> Tool | None:
    return _BY_NAME.get(name)


def safe_run(name: str, args: dict[str, Any]) -> ToolOutcome:
    tool = _BY_NAME.get(name)
    if not tool:
        return ToolOutcome(text=f"未知工具：{name}")
    try:
        return tool.run(args)
    except SandboxError as e:
        return ToolOutcome(text=f"沙箱拒绝：{e}")
    except Exception as e:  # noqa: BLE001
        return ToolOutcome(text=f"工具出错：{e}")
