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
import json
import mimetypes
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from agent import browser, office, security
from agent.sandbox import SandboxError, current_root, relpath, resolve_in_sandbox
from config import scrubbed_env, settings
import server_client
from storage import db
from storage.models import Role

MAX_OUTPUT = 6000
CMD_TIMEOUT = 30
KB_MAX_UPLOAD = 50 * 1024 * 1024  # 50 MB/文件，与知识库路由一致


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
    # Files truthfully produced by this tool. Runtime turns these descriptors into
    # hashed Artifact manifests tied to the active Run (WB-242).
    artifacts: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    # Trace item shown BEFORE execution (pulses while running); None = none.
    pre: Callable[[dict[str, Any]], dict[str, Any] | None]
    # Executes the tool; returns result text + any POST trace items (e.g. diff).
    run: Callable[[dict[str, Any]], ToolOutcome]
    # 计划模式下是否可用（WB-186）。plan 的契约是「plan, don't execute」——只读、不写文件、
    # 不跑命令。**默认 False = 保守**：新工具除非明确标注，plan 模式一律不给。
    # 从前只有 base 工具受 `_PLAN_TOOLS` 名单约束，技能工具完全绕过 plan 过滤——今天 3 个技能
    # 工具恰好都只读（web_fetch/html_to_markdown 是 HTTP GET、analyze_csv 是本地读）所以没暴雷，
    # 但技能定义已可运营（WB-183），一个会写的技能工具就会静默地在 plan 模式下跑起来。
    plan_safe: bool = False
    # Machine-readable authority used by Skill releases, upgrade diffs and Run snapshots.
    permissions: tuple[str, ...] = ()
    timeout_seconds: float = 30.0
    isolation: Literal["thread", "subprocess"] = "thread"

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
    plan_safe=True,  # 只读
    permissions=("workspace.read",),
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
    plan_safe=True,  # 只读
    permissions=("workspace.read",),
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
        artifacts=[{"path": relpath(target), "kind": "file"}],
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
    permissions=("workspace.write",),
)


# ---- dedicated office deliverables (WB-243) -----------------------------

def _office_create(args: dict[str, Any], builder: Callable[[dict[str, Any]], tuple[str, dict[str, Any]]]) -> ToolOutcome:
    path, validation = builder(args)
    return ToolOutcome(
        text=f"已生成并校验 {path}\n{json.dumps(validation, ensure_ascii=False)}",
        trace=[{"kind": "step", "tool": "office_validate", "label": f"已校验 {path}"}],
        artifacts=[{"path": path, "kind": "office", "validation": validation}],
    )


_SECTION_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "heading": {"type": "string"},
            "level": {"type": "integer", "minimum": 1, "maximum": 3},
            "paragraphs": {"type": "array", "items": {"type": "string"}},
        },
    },
}
_TABLES_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "rows": {"type": "array", "items": {"type": "array", "items": {}}},
        },
        "required": ["rows"],
    },
}

create_docx = Tool(
    name="create_docx",
    description="在工作区原子生成并重新打开校验一个 DOCX 报告；不要用 write_file 或 run_command 伪造 Word 文件。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "相对工作区路径，必须以 .docx 结尾"},
            "title": {"type": "string"}, "sections": _SECTION_SCHEMA,
            "tables": _TABLES_SCHEMA, "font": {"type": "string"}, "font_size": {"type": "number"},
        },
        "required": ["path", "title", "sections"],
    },
    pre=lambda a: {"kind": "step", "tool": "create_docx", "label": f"生成 Word {a.get('path', '')}"},
    run=lambda a: _office_create(a, office.create_docx),
    permissions=("workspace.write",),
    timeout_seconds=60,
)

create_xlsx = Tool(
    name="create_xlsx",
    description="在工作区原子生成并重新打开校验一个 XLSX；支持多 sheet、公式和一张结构化图表。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "相对工作区路径，必须以 .xlsx 结尾"},
            "sheets": {
                "type": "array", "items": {
                    "type": "object", "properties": {
                        "name": {"type": "string"},
                        "rows": {"type": "array", "items": {"type": "array", "items": {}}},
                        "formulas": {"type": "array", "items": {"type": "object", "properties": {
                            "cell": {"type": "string"}, "formula": {"type": "string"}}, "required": ["cell", "formula"]}},
                        "chart": {"type": "object", "properties": {
                            "type": {"type": "string", "enum": ["bar", "line", "pie"]},
                            "title": {"type": "string"}, "data_min_col": {"type": "integer"},
                            "data_max_col": {"type": "integer"}, "categories_col": {"type": "integer"},
                            "min_row": {"type": "integer"}, "max_row": {"type": "integer"},
                            "anchor": {"type": "string"},
                        }},
                    }, "required": ["name", "rows"],
                },
            },
        },
        "required": ["path", "sheets"],
    },
    pre=lambda a: {"kind": "step", "tool": "create_xlsx", "label": f"生成 Excel {a.get('path', '')}"},
    run=lambda a: _office_create(a, office.create_xlsx),
    permissions=("workspace.write",),
    timeout_seconds=60,
)

create_pptx = Tool(
    name="create_pptx",
    description="在工作区原子生成并校验一个 PPTX 演示文稿；自动检查所有 shape 是否越出页面边界。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "相对工作区路径，必须以 .pptx 结尾"},
            "title": {"type": "string"},
            "slides": {"type": "array", "items": {"type": "object", "properties": {
                "title": {"type": "string"}, "bullets": {"type": "array", "items": {"type": "string"}},
            }, "required": ["title"]}},
        },
        "required": ["path", "slides"],
    },
    pre=lambda a: {"kind": "step", "tool": "create_pptx", "label": f"生成 PPT {a.get('path', '')}"},
    run=lambda a: _office_create(a, office.create_pptx),
    permissions=("workspace.write",),
    timeout_seconds=60,
)

create_pdf = Tool(
    name="create_pdf",
    description="在工作区原子生成并重新解析校验一个 PDF；支持 Unicode 正文与表格。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "相对工作区路径，必须以 .pdf 结尾"},
            "title": {"type": "string"},
            "paragraphs": {"type": "array", "items": {"type": "string"}},
            "tables": _TABLES_SCHEMA,
        },
        "required": ["path", "paragraphs"],
    },
    pre=lambda a: {"kind": "step", "tool": "create_pdf", "label": f"生成 PDF {a.get('path', '')}"},
    run=lambda a: _office_create(a, office.create_pdf),
    permissions=("workspace.write",),
    timeout_seconds=60,
)


def _inspect_office(args: dict[str, Any]) -> ToolOutcome:
    path = str(args["path"])
    validation = office.inspect_office_file(path)
    return ToolOutcome(
        text=json.dumps(validation, ensure_ascii=False),
        trace=[{"kind": "file_read", "path": path, "range": "结构校验"}],
    )


inspect_office_file = Tool(
    name="inspect_office_file",
    description="只读检查工作区里的 DOCX/XLSX/PPTX/PDF 结构、页/表/公式/图表与页面边界；不会修改文件。",
    parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    pre=lambda a: {"kind": "step", "tool": "inspect_office_file", "label": f"检查办公文件 {a.get('path', '')}"},
    run=_inspect_office,
    plan_safe=True,
    permissions=("workspace.read",),
    timeout_seconds=60,
)


# ---- persistent browser (WB-244) ---------------------------------------

def _browser_outcome(result: dict[str, Any]) -> ToolOutcome:
    artifacts = result.pop("artifacts", [])
    title = str(result.get("title") or "")
    url = str(result.get("url") or "")
    return ToolOutcome(
        text=json.dumps(result, ensure_ascii=False),
        trace=[{"kind": "step", "tool": "browser", "label": f"浏览器 · {title or url}"}],
        artifacts=artifacts,
    )


browser_navigate = Tool(
    name="browser_navigate",
    description=(
        "用当前用户隔离且可复用登录态的系统 Edge/Chrome 打开公共 HTTP(S) 页面并读取可见内容。"
        "默认阻断 localhost/私网和所有非 GET 网络写；可选把全页截图交付为 Artifact。"
    ),
    parameters={"type": "object", "properties": {
        "url": {"type": "string"}, "timeout_ms": {"type": "integer", "minimum": 1000, "maximum": 60000},
        "screenshot_path": {"type": "string", "description": "可选工作区 .png 路径"},
    }, "required": ["url"]},
    pre=lambda a: {"kind": "step", "tool": "browser_navigate", "label": f"打开网页 {str(a.get('url', ''))[:100]}"},
    run=lambda a: _browser_outcome(browser.navigate(a)),
    plan_safe=True,
    permissions=("network.read", "browser.state"),
    timeout_seconds=45,
)

browser_read = Tool(
    name="browser_read",
    description="读取当前用户浏览器 profile 上次页面（或指定公共 URL）的标题、可见文本、链接和表单控件；只发 GET。",
    parameters={"type": "object", "properties": {"url": {"type": "string"}}},
    pre=lambda a: {"kind": "step", "tool": "browser_read", "label": "读取浏览器页面"},
    run=lambda a: _browser_outcome(browser.read(a)),
    plan_safe=True,
    permissions=("network.read", "browser.state"),
    timeout_seconds=45,
)

browser_interact = Tool(
    name="browser_interact",
    description=(
        "在当前页面执行 fill/select/check/uncheck/click/upload/screenshot/download。"
        "submit、Enter 和任何 POST/PUT/PATCH/DELETE 始终被阻断并返回 confirmation_required；"
        "模型不能自行声明用户已确认。"
    ),
    parameters={"type": "object", "properties": {
        "url": {"type": "string"},
        "actions": {"type": "array", "items": {"type": "object", "properties": {
            "type": {"type": "string", "enum": ["fill", "select", "check", "uncheck", "click", "upload", "screenshot", "download", "submit", "press_enter"]},
            "selector": {"type": "string"}, "value": {"type": "string"}, "path": {"type": "string"},
        }, "required": ["type"]}},
    }, "required": ["actions"]},
    pre=lambda a: {"kind": "step", "tool": "browser_interact", "label": f"浏览器交互 {len(a.get('actions') or [])} 步"},
    run=lambda a: _browser_outcome(browser.interact(a)),
    permissions=("network.read", "browser.state", "workspace.write"),
    timeout_seconds=60,
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
            # 后端自己的密钥不进通用 shell（WB-192）：否则 `echo $LLM_API_KEY` 一句就能把它
            # 读进模型上下文 → 上传给 LLM 厂商 + 进 trace/持久化。同 WB-011 对连接器的收口，
            # 只是这条路用「剔除密钥」而非白名单（要跑用户真实命令，白名单会误伤）。
            env=scrubbed_env(),
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
    permissions=("workspace.read", "workspace.write", "process.execute", "host.unrestricted", "network.unrestricted"),
    timeout_seconds=CMD_TIMEOUT,
    isolation="subprocess",
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
    plan_safe=True,  # 写的是待办清单本身 —— 正是计划模式要产出的东西，不是「执行」
    permissions=("run.plan.write",),
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
    "review": "review", "待验收": "review", "提交验收": "review",
    # Agent can submit work, but only a human acceptance action may close it.
    "done": "review", "完成": "review", "已完成": "review",
}
_WI_LABEL = {"todo": "待开始", "doing": "进行中", "paused": "暂停", "review": "待验收", "done": "完成"}


def set_work_context(
    project_id: str | None, owner_id: str | None, *, server_token: str = "",
) -> None:
    """Set the active project/member authority for work-item tools."""
    _work_ctx.set(
        {"project_id": project_id, "owner_id": owner_id, "server_token": server_token}
        if project_id and owner_id else None
    )


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
    permissions=("project.read",),
)


def _set_work_item_status_run(args: dict[str, Any]) -> ToolOutcome:
    ctx = _work_ctx.get()
    if not ctx:
        return ToolOutcome(text="当前不在项目中，无法修改计划项。")
    item_id = str(args.get("item_id", "")).strip()
    raw = str(args.get("status", "")).strip()
    status = _WI_STATUS.get(raw) or _WI_STATUS.get(raw.lower())
    if not status:
        return ToolOutcome(text=f"未知状态「{raw}」。可用：待开始 / 进行中 / 暂停 / 待验收。")
    wi = db.get_work_item(item_id)
    role = db.project_access_role(ctx["project_id"], ctx["owner_id"])
    if not wi or wi.project_id != ctx["project_id"] or role in {None, Role.VIEWER}:
        return ToolOutcome(text=f"未找到计划项 id={item_id}（或不属于当前项目）。可先用 list_work_items 核对 id。")
    project = db.get_project(ctx["project_id"])
    if project and project.origin == "server":
        token = str(ctx.get("server_token") or "")
        if not token:
            return ToolOutcome(text="Server 项目当前没有可用登录凭据，状态未更新。")
        updated = server_client.update_work_item(token, wi.project_id, wi.id, {"status": status})
        if not updated:
            return ToolOutcome(text="Server 暂不可达，状态未更新。")
        db.apply_server_work_item_status(
            wi.id, status, server_updated_at=float(updated.get("updated_at") or 0) or None,
        )
    else:
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
        "status 取 待开始 / 进行中 / 暂停 / 待验收 之一。Agent 认为完成时也只能提交待验收，不能自行验收。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "item_id": {"type": "string", "description": "计划项 id"},
            "status": {"type": "string", "description": "目标状态：待开始 / 进行中 / 暂停 / 待验收；完成会归一为待验收"},
        },
        "required": ["item_id", "status"],
    },
    pre=lambda a: None,
    run=_set_work_item_status_run,
    permissions=("project.write",),
)


def work_item_tools(plan: bool = False) -> list[Tool]:
    """Work-item tools for a run. Plan mode is read-only, so no status writes."""
    values = [list_work_items] if plan else [list_work_items, set_work_item_status]
    return [tool for tool in values if server_tool_enabled(tool.name)]


# ---- knowledge_retrieve（知识库检索）— WB-143/173 -------------------------
#
# 会话挂载的知识库检索，改用自托管 WeKnora（腾讯开源 RAG）。与 work-item 同款
# contextvar 注入：owner + 选中的 knowledge_ids 由 run_chat 每次运行前 set；工具真调
# WeKnora 检索（同步，由 runtime 的 asyncio.to_thread 兜住）。
# WB-188 起 owner_id 是**必需**的（不再是「备用」）：连接配置按 owner 存 DB（.env 兜底），
# 故 owner 决定打哪个 WeKnora、用谁的 key。key 只在后端解析，绝不回前端。
# 注意：knowledge_add 不要求挂载知识库（WB-175），所以 owner 必须**无条件** set，
# 「有没有挂库」只看 knowledge_ids 是否为空。

_kb_ctx: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar("kb_ctx", default=None)


def set_knowledge_context(
    owner_id: str | None,
    knowledge_ids: list[str] | None,
    *,
    server_project_id: str | None = None,
    server_token: str | None = None,
) -> None:
    """Set the active owner + mounted knowledge base ids for this run (run_chat calls it).

    local project 使用 owner 级 WeKnora；server_project_id 非空时所有知识操作经 Server 项目门禁代理，
    server_token 只留在 contextvar，不进入工具 schema、trace 或 LLM 上下文。"""
    _kb_ctx.set({
        "owner_id": owner_id,
        "knowledge_ids": knowledge_ids or [],
        "server_project_id": server_project_id or "",
        "server_token": server_token or "",
    } if owner_id else None)


def _kb_owner() -> str | None:
    ctx = _kb_ctx.get()
    return ctx["owner_id"] if ctx else None


def _knowledge_retrieve_run(args: dict[str, Any]) -> ToolOutcome:
    from agent import weknora  # 延迟导入，避免与加载顺序耦合

    ctx = _kb_ctx.get()
    if not ctx or not ctx["knowledge_ids"]:
        return ToolOutcome(text="当前会话未挂载任何知识库。")
    query = str(args.get("query", "")).strip()
    if not query:
        return ToolOutcome(text="请提供检索问题（query）。")
    owner = ctx["owner_id"]
    remote_project = str(ctx.get("server_project_id") or "")
    remote_token = str(ctx.get("server_token") or "")
    if remote_project:
        if not remote_token:
            return ToolOutcome(text="中央项目知识库不可用：当前账号缺少有效的 Server 登录凭据，请重新登录后重试。")
    elif not weknora.configured(owner):
        return ToolOutcome(text=weknora.NOT_CONFIGURED)
    try:
        top_k = int(args.get("top_k") or 8)
    except (TypeError, ValueError):
        top_k = 8
    try:
        if remote_project:
            hits = server_client.search_project_knowledge(
                remote_token, remote_project, query=query,
                knowledge_ids=ctx["knowledge_ids"], top_k=max(1, min(top_k, 20)),
            )
            if hits is None:
                return ToolOutcome(text="中央项目知识库检索失败：Server/WeKnora 不可达、无权访问或请求被拒绝；未回退到本地知识库。")
        else:
            hits = weknora.search(owner, query=query, knowledge_ids=ctx["knowledge_ids"], top_k=max(1, min(top_k, 20)))
    except weknora.WeKnoraError as e:
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
    plan_safe=True,  # 检索 = 读；规划时查资料正当（WB-186）
    permissions=("knowledge.read", "network.read"),
    timeout_seconds=45,
)


# ---- knowledge_add（把工作区文件或 URL 加入知识库）— WB-175/193 ------------
#
# 会话内把工作区文件或 URL 沉淀进 WeKnora 知识库。
# **不要求先把库挂载到对话**：只要后端接了 WeKnora（配了 key）就可用——目标库按
# knowledge_id / kb_name / 挂载库 / 唯一现存库 依次解析，都定不了才让用户澄清。
# path 复用沙箱读文件 + upload_file；url 走 create_from_url，后者先对 WeKnora 版本做
# fail-closed SSRF 安全门禁。二者都异步解析（parse_status pending→completed 后可检索）。

def _fmt_kbs(kbs: dict[str, str]) -> str:
    return "；".join(f"{n or '(无名)'}={i}" for i, n in kbs.items()) or "（无）"


class _CentralKnowledgeUnavailable(RuntimeError):
    pass


def _available_kbs(weknora, owner: str | None) -> list[dict[str, Any]]:
    ctx = _kb_ctx.get() or {}
    project_id = str(ctx.get("server_project_id") or "")
    if not project_id:
        return weknora.list_kb(owner)
    token = str(ctx.get("server_token") or "")
    if not token:
        raise _CentralKnowledgeUnavailable("当前账号缺少有效的 Server 登录凭据。")
    rows = server_client.list_project_knowledge(token, project_id)
    if rows is None:
        raise _CentralKnowledgeUnavailable("Server/WeKnora 不可达、无权访问或请求被拒绝。")
    return [row for row in rows if row.get("provider_status") == "ready"]


def _resolve_add_kb(weknora, owner: str | None, args: dict[str, Any], mounted: list[str]) -> tuple[str | None, str]:
    """定位要加入的知识库。返回 (kb_id, note)。kb_id=None → 需用户澄清（note 是提示文案）。
    优先级：显式 knowledge_id > 显式 kb_name > 会话挂载的唯一库 > 现存唯一库 > 让用户指定。"""
    want_id = str(args.get("knowledge_id") or "").strip()
    want_name = str(args.get("kb_name") or "").strip()

    def _load() -> dict[str, str]:
        return {str(k.get("id")): (k.get("name") or "") for k in _available_kbs(weknora, owner) if k.get("id")}

    if want_id:
        kbs = _load()
        if want_id in kbs:
            return want_id, (f"「{kbs[want_id]}」" if kbs[want_id] else "")
        return None, f"未找到知识库 id={want_id}。现有：{_fmt_kbs(kbs)}"
    if want_name:
        kbs = _load()
        hits = [i for i, n in kbs.items() if n == want_name]
        if len(hits) == 1:
            return hits[0], f"「{want_name}」"
        if not hits:
            return None, f"未找到名为「{want_name}」的知识库。现有：{_fmt_kbs(kbs)}"
        return None, f"有多个名为「{want_name}」的库，请用 knowledge_id 指定。"
    if len(mounted) == 1:
        return mounted[0], ""
    if len(mounted) > 1:
        return None, f"本会话挂载了多个知识库（{', '.join(mounted)}），请用 knowledge_id 指定要加入哪个。"
    kbs = _load()
    if len(kbs) == 1:
        only = next(iter(kbs))
        return only, (f"「{kbs[only]}」" if kbs[only] else "")
    if not kbs:
        return None, "知识库为空，请先在「知识库」页新建一个知识库，再加入文件。"
    return None, f"有多个知识库，请用 knowledge_id 或 kb_name 指定要加入哪个。现有：{_fmt_kbs(kbs)}"


def _knowledge_add_run(args: dict[str, Any]) -> ToolOutcome:
    from agent import weknora  # 延迟导入

    owner = _kb_owner()
    ctx = _kb_ctx.get() or {}
    remote_project = str(ctx.get("server_project_id") or "")
    remote_token = str(ctx.get("server_token") or "")
    if remote_project and not remote_token:
        return ToolOutcome(text="中央项目知识库不可用：当前账号缺少有效的 Server 登录凭据，请重新登录后重试。")
    if not remote_project and not weknora.configured(owner):
        return ToolOutcome(text=weknora.NOT_CONFIGURED)
    path = str(args.get("path") or "").strip()
    url = str(args.get("url") or "").strip()
    if bool(path) == bool(url):
        return ToolOutcome(text="请在 path 与 url 中恰好提供一个：path 用于工作区文件，url 用于网页或远程文件。")

    target = None
    if path:
        try:
            target = resolve_in_sandbox(path)
        except SandboxError as e:
            return ToolOutcome(text=f"路径不合法：{e}")
        if not target.exists() or not target.is_file():
            return ToolOutcome(text=f"文件不存在：{path}")
        ext = target.suffix.lstrip(".").lower()
        if ext and ext not in weknora.SUPPORTED_EXTS:
            return ToolOutcome(text=f"知识库不支持的文件类型：.{ext}（支持 {', '.join(sorted(weknora.SUPPORTED_EXTS))}）。")
        size = target.stat().st_size
        if size > KB_MAX_UPLOAD:
            return ToolOutcome(text=f"文件超过 50MB 上限（约 {size // (1024 * 1024)}MB），无法加入知识库。")
    else:
        try:
            url = weknora.validate_import_url(url)
        except weknora.WeKnoraError as e:
            return ToolOutcome(text=str(e))

    mounted = (_kb_ctx.get() or {}).get("knowledge_ids") or []
    try:
        kb_id, note = _resolve_add_kb(weknora, owner, args, mounted)
    except (weknora.WeKnoraError, _CentralKnowledgeUnavailable) as e:
        return ToolOutcome(text=f"读取知识库列表失败：{e}")
    if kb_id is None:
        return ToolOutcome(text=note)  # 需用户指定 / 知识库为空

    try:
        if target is not None:
            content = target.read_bytes()
            ct = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if remote_project:
                if server_client.upload_project_knowledge_file(
                    remote_token, remote_project, kb_id,
                    filename=target.name, content=content, content_type=ct,
                ) is None:
                    return ToolOutcome(text="加入中央项目知识库失败：Server/WeKnora 不可达、无权写入或请求被拒绝；文件未加入本地知识库。")
            else:
                weknora.upload_file(owner, kb_id, filename=target.name, content=content, content_type=ct)
        else:
            if remote_project:
                if server_client.import_project_knowledge_url(
                    remote_token, remote_project, kb_id, url=url,
                ) is None:
                    return ToolOutcome(text="URL 加入中央项目知识库失败：Server/WeKnora 不可达、安全策略拒绝或无权写入；未回退到本地知识库。")
            else:
                weknora.create_from_url(owner, kb_id, url=url)
    except weknora.WeKnoraError as e:
        return ToolOutcome(text=f"加入知识库失败：{e}")
    if kb_id in mounted:
        tail = ""
    elif remote_project:
        tail = "（中央项目绑定将在下次项目同步或执行时自动刷新）"
    else:
        tail = "（该库未挂载到本会话；如需在对话中检索它，去「知识库」页点『挂载到对话』）"
    source = f"「{target.name}」" if target is not None else f"URL「{url[:120]}」"
    return ToolOutcome(
        text=f"已把{source}加入知识库{note}（正在后台解析并向量化，稍后即可用 knowledge_retrieve 检索到）。{tail}"
    )


knowledge_add = Tool(
    name="knowledge_add",
    description=(
        "把工作区里的一个文件或 http(s) URL 加入知识库（path/url 恰好二选一）。"
        "WeKnora 会解析/切片/向量化，之后可被 knowledge_retrieve 检索。"
        "当用户要求把文档或网页「加入/上传/添加/沉淀到知识库」时用——无需先挂载知识库。"
        "目标库：只有一个库时自动选；多个库时用 knowledge_id 或 kb_name 指定。"
        "path 支持 pdf/doc(x)/ppt(x)/xls(x)/txt/md/html/csv/图片，单文件≤50MB；url 需 WeKnora 安全版本及其 SSRF 白名单允许。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "要加入知识库的工作区文件（相对工作区路径）"},
            "url": {"type": "string", "description": "要加入知识库的 http(s) 网页或远程文件 URL（与 path 恰好二选一）"},
            "knowledge_id": {"type": "string", "description": "目标知识库 id（多库时二选一：id 或 kb_name）"},
            "kb_name": {"type": "string", "description": "目标知识库名称（多库时二选一：id 或 kb_name）"},
        },
    },
    pre=lambda a: {
        "kind": "step", "tool": "knowledge_add",
        "label": f"加入知识库 {str(a.get('path') or a.get('url') or '')[:60]}",
    },
    run=_knowledge_add_run,
    permissions=("workspace.read", "knowledge.write", "network.write"),
    timeout_seconds=120,
    # plan_safe 保持默认 False（WB-186）：这是**写**——把文件灌进知识库并触发解析/切片/向量化。
    # 此前 kb_tools 完全绕过 plan 过滤，计划模式下 agent 真能调它改知识库，违反「plan, don't execute」。
)


TOOLS: list[Tool] = [
    list_dir, read_file, write_file,
    create_docx, create_xlsx, create_pptx, create_pdf, inspect_office_file,
    browser_navigate, browser_read, browser_interact,
    run_command, update_plan,
]
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
# 这份名单现在只是 `Tool.plan_safe` 的**一致性断言**（WB-186）：过滤真正依据 plan_safe，
# 好让技能工具（不在 TOOLS 里）也能表达「我 plan 安全吗」。两处若漂移，下面的断言会炸。
_PLAN_TOOLS = {"list_dir", "read_file", "inspect_office_file", "browser_navigate", "browser_read", "update_plan"}
for _t in TOOLS:  # 建表期自检：名单与 plan_safe 必须一致，防止日后改一处忘另一处
    assert (_t.name in _PLAN_TOOLS) == _t.plan_safe, (
        f"tools.py: {_t.name} 的 plan_safe={_t.plan_safe} 与 _PLAN_TOOLS 名单不一致"
    )


def base_tools(plan: bool = False) -> list[Tool]:
    return plan_filter(TOOLS, plan)


def plan_filter(tools: list[Tool], plan: bool) -> list[Tool]:
    """计划模式下滤掉非 plan-safe 的工具（WB-186）。供技能/知识库等**非 base** 工具集复用
    —— 它们从前完全绕过 plan 过滤。默认 plan_safe=False，故新工具不标注就进不了 plan 模式。"""
    return [
        tool for tool in tools
        if server_tool_enabled(tool.name) and (not plan or tool.plan_safe)
    ]


def server_tool_enabled(name: str) -> bool:
    """Server 已下发目录时由其控制工具启停；纯本地/旧 Server 保持现有能力。"""
    if not settings.DB_PATH.is_file():
        return True
    rows = db.list_server_tool_catalog()
    if not rows:
        return True
    item = next((value for value in rows if value.get("name") == name), None)
    return bool(item and item.get("enabled"))


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
