"""Runtime adapters for executable tool definitions downlinked from AgentMate Server."""
from __future__ import annotations

import json
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from agent.sandbox import current_root
from agent.tools import Tool, ToolOutcome
from config import scrubbed_env, settings
from storage import db


def platform_key(system: str | None = None) -> str:
    value = (system or platform.system()).strip().lower()
    if value in {"darwin", "mac", "macos"}:
        return "macos"
    if value.startswith("win"):
        return "windows"
    if value.startswith("linux"):
        return "linux"
    return value


def _interpreter(key: str) -> tuple[str, list[str], str]:
    if key == "windows":
        executable = shutil.which("pwsh.exe")
        if not executable:
            raise RuntimeError("当前 Windows 未安装或找不到 pwsh.exe")
        return executable, ["-NoLogo", "-NoProfile", "-NonInteractive", "-File"], ".ps1"
    if key in {"linux", "macos"}:
        executable = shutil.which("bash") or ("/bin/bash" if Path("/bin/bash").is_file() else "")
        if not executable:
            raise RuntimeError("当前系统未安装或找不到 bash")
        return executable, [], ".sh"
    raise RuntimeError(f"Server 工具暂不支持当前操作系统：{key or 'unknown'}")


def _truncate_output(value: str, limit: int) -> str:
    encoded = value.encode("utf-8", errors="replace")
    if len(encoded) <= limit:
        return value
    clipped = encoded[:limit].decode("utf-8", errors="ignore")
    return f"{clipped}\n… [输出已截断，原始 {len(encoded)} 字节]"


def _version_tuple(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for token in str(value or "").replace("-", ".").split("."):
        if not token.isdigit():
            break
        parts.append(int(token))
    return tuple(parts) if parts else (0,)


def _run_shell_tool(spec: dict[str, Any], key: str, script: str, args: dict[str, Any]) -> ToolOutcome:
    name = str(spec["name"])
    timeout = int(spec.get("timeout_seconds", 30))
    output_limit = int(spec.get("output_limit", 65536))
    try:
        executable, prefix, suffix = _interpreter(key)
        root = current_root()
        root.mkdir(parents=True, exist_ok=True)
        env = scrubbed_env()
        env["AGENTMATE_TOOL_NAME"] = name
        env["AGENTMATE_TOOL_PLATFORM"] = key
        with tempfile.TemporaryDirectory(prefix=f"agentmate-{name}-") as temp_dir:
            script_path = Path(temp_dir) / f"tool{suffix}"
            script_path.write_text(script, encoding="utf-8")
            completed = subprocess.run(
                [executable, *prefix, str(script_path)],
                cwd=str(root),
                env=env,
                input=json.dumps(args, ensure_ascii=False),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                shell=False,
                check=False,
            )
    except subprocess.TimeoutExpired:
        return ToolOutcome(text=f"Server 工具 {name} 执行超时（{timeout} 秒）。")
    except (OSError, RuntimeError) as exc:
        return ToolOutcome(text=f"Server 工具 {name} 无法启动：{exc}")

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    parts = [stdout] if stdout else []
    if stderr:
        parts.append(f"[stderr]\n{stderr}")
    output = "\n".join(parts) or "（无输出）"
    output = _truncate_output(output, output_limit)
    if completed.returncode != 0:
        return ToolOutcome(text=f"Server 工具 {name} 执行失败（退出码 {completed.returncode}）。\n{output}")
    return ToolOutcome(text=output)


def build_shell_tools(system: str | None = None) -> list[Tool]:
    """Materialize enabled Server shell definitions for this operating system."""
    key = platform_key(system)
    tools: list[Tool] = []
    for spec in db.list_server_tool_catalog():
        scripts = spec.get("scripts") if isinstance(spec.get("scripts"), dict) else {}
        script = scripts.get(key)
        if (
            spec.get("implementation_type") != "shell"
            or not spec.get("enabled")
            or spec.get("exposure") != "skill"
            or not spec.get("bindable")
            or _version_tuple(str(spec.get("min_app_version") or "0")) > _version_tuple(settings.APP_VERSION)
            or _version_tuple(str(spec.get("contract_version") or "1")) > _version_tuple(settings.TOOL_CONTRACT_VERSION)
            or not isinstance(script, str)
            or not script.strip()
        ):
            continue
        captured = dict(spec)
        captured_script = script
        captured_key = key
        tools.append(Tool(
            name=str(spec["name"]),
            description=str(spec.get("description") or spec.get("label") or spec["name"]),
            parameters=spec.get("parameters") if isinstance(spec.get("parameters"), dict) else {
                "type": "object", "properties": {},
            },
            pre=lambda _args, tool_name=str(spec["name"]), label=str(spec.get("label") or spec["name"]): {
                "kind": "step", "tool": tool_name, "label": f"运行 {label}",
            },
            run=lambda args, item=captured, os_key=captured_key, body=captured_script:
                _run_shell_tool(item, os_key, body, args),
            plan_safe=False,
            permissions=tuple(str(value) for value in spec.get("permissions", []) if str(value)),
            timeout_seconds=float(spec.get("timeout_seconds", 30)) + 1.0,
            isolation="thread",
        ))
    return tools
