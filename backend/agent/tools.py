"""Agent tools — real operations inside the workspace sandbox (spec 5.3).

Each tool exposes an OpenAI function schema plus an executor. Executors run
strictly within `workspace/` (spec 8, hard-line #2) and return a result string
plus trace items. The runtime turns those into typed SSE events
(step / file_read / diff / todo) — so the koda-style trace is driven by REAL
tool calls, not a script.

`run_command` is powerful; for M1/M2 it runs with cwd pinned to the workspace and
a hard timeout. M4 will gate out-of-sandbox escapes behind ask_user authorization.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable

from agent.sandbox import WORKSPACE_ROOT, SandboxError, relpath, resolve_in_sandbox

MAX_OUTPUT = 6000
CMD_TIMEOUT = 30


@dataclass
class ToolOutcome:
    """What a tool execution produced: text fed back to the LLM + trace items."""
    text: str
    trace: list[dict[str, Any]] = field(default_factory=list)


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
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(WORKSPACE_ROOT),
            capture_output=True,
            text=True,
            timeout=CMD_TIMEOUT,
        )
        out = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
        out = out.strip() or "（无输出）"
        return ToolOutcome(text=f"退出码 {proc.returncode}\n{_truncate(out)}")
    except subprocess.TimeoutExpired:
        return ToolOutcome(text=f"命令超时（>{CMD_TIMEOUT}s）：{command}")
    except Exception as e:  # noqa: BLE001
        return ToolOutcome(text=f"命令执行失败：{e}")


run_command = Tool(
    name="run_command",
    description="在工作区目录内运行一条 shell 命令并返回输出（沙箱内、有超时）。",
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


def tool_schemas(plan: bool = False) -> list[dict[str, Any]]:
    tools = [t for t in TOOLS if (t.name in _PLAN_TOOLS)] if plan else TOOLS
    return [t.schema() for t in tools] + [ASK_USER_SCHEMA]


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
