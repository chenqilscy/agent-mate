"""Uniform timeout/cancellation boundary for built-in tools (WB-248)."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Awaitable

from agent import security
from agent.execution_policy import ExecutionAuthorization
from agent.sandbox import current_root
from agent.tools import Tool, ToolOutcome, run_tool
from config import BACKEND_DIR, FROZEN, scrubbed_env, settings


class ToolExecutionTimeout(TimeoutError):
    pass


class ToolExecutionCancelled(asyncio.CancelledError):
    pass


class ToolExecutionIsolationError(RuntimeError):
    pass


async def _kill_process_tree(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    if os.name == "nt":
        killer = await asyncio.create_subprocess_exec(
            "taskkill", "/PID", str(proc.pid), "/T", "/F",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        await killer.wait()
    else:
        try:
            os.killpg(proc.pid, 15)
        except (ProcessLookupError, PermissionError):
            proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), 3)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()


async def _wait_or_stop(
    awaitable: Awaitable[Any], stop: asyncio.Event, timeout: float,
) -> Any:
    task = asyncio.ensure_future(awaitable)
    stop_task = asyncio.create_task(stop.wait())
    done, _ = await asyncio.wait(
        {task, stop_task}, timeout=max(0.1, timeout), return_when=asyncio.FIRST_COMPLETED,
    )
    if task in done:
        stop_task.cancel()
        return await task
    task.cancel()
    if stop_task in done and stop.is_set():
        raise ToolExecutionCancelled()
    raise ToolExecutionTimeout(f"tool exceeded {timeout:g}s")


def _worker_payload(tool: Tool, args: dict[str, Any], owner_id: str) -> bytes:
    from agent import skill_discovery, skill_resources, skill_usage, skills_store
    from agent.tools import knowledge_context_snapshot, work_context_snapshot

    payload = {
        "tool": tool.name,
        "args": args,
        "config": {
            "db_path": str(settings.DB_PATH),
            "workspace_root": str(settings.WORKSPACE_ROOT),
            "skills_dir": str(settings.SKILLS_DIR),
        },
        "context": {
            "owner_id": owner_id,
            "workspace_root": str(current_root()),
            "environment": sorted(skills_store.current_environment()),
            "work": work_context_snapshot(),
            "knowledge": knowledge_context_snapshot(),
            "skill_candidates": list(skill_discovery.candidate_map().values()),
            "skill_resources": skill_resources.active_resource_mounts(),
            "skill_usage": skill_usage.context_snapshot(),
        },
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


async def _run_tool_worker(
    tool: Tool, args: dict[str, Any], stop: asyncio.Event, *, owner_id: str,
) -> ToolOutcome:
    command = (
        [sys.executable, "--tool-worker"]
        if FROZEN else [sys.executable, "-m", "agent.tool_worker"]
    )
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    proc = await asyncio.create_subprocess_exec(
        *command, cwd=str(BACKEND_DIR), env=scrubbed_env(),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, **kwargs,
    )
    communicate = asyncio.create_task(proc.communicate(input=_worker_payload(tool, args, owner_id)))
    stop_task = asyncio.create_task(stop.wait())
    try:
        done, _ = await asyncio.wait(
            {communicate, stop_task}, timeout=max(0.1, tool.timeout_seconds),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if communicate in done:
            stdout, stderr = await communicate
            try:
                message = json.loads(stdout.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                detail = stderr.decode("utf-8", errors="replace")[-2000:]
                raise ToolExecutionIsolationError(
                    f"isolated tool returned invalid protocol: {tool.name}; {detail}"
                ) from exc
            if not isinstance(message, dict) or not message.get("ok"):
                raise ToolExecutionIsolationError(
                    str(message.get("error") if isinstance(message, dict) else "worker failed")
                )
            value = message.get("outcome") if isinstance(message.get("outcome"), dict) else {}
            return ToolOutcome(
                text=str(value.get("text") or ""),
                trace=list(value.get("trace") or []),
                live=list(value.get("live") or []),
                artifacts=list(value.get("artifacts") or []),
            )
        await _kill_process_tree(proc)
        communicate.cancel()
        await asyncio.gather(communicate, return_exceptions=True)
        if stop_task in done and stop.is_set():
            raise ToolExecutionCancelled()
        raise ToolExecutionTimeout(f"tool exceeded {tool.timeout_seconds:g}s")
    except asyncio.CancelledError:
        await _kill_process_tree(proc)
        communicate.cancel()
        await asyncio.gather(communicate, return_exceptions=True)
        raise
    finally:
        stop_task.cancel()


async def _run_command_isolated(
    tool: Tool, args: dict[str, Any], stop: asyncio.Event,
) -> ToolOutcome:
    command = str(args.get("command") or "")
    owner = security.current_owner()
    allowed, pattern = security.check_command(command, owner)
    if not allowed:
        security.audit(owner, tool.name, command, "blocked")
        return ToolOutcome(
            text=f"命令被安全策略拦截（命中规则「{pattern}」）：{command}\n"
                 "如确需执行，请到「设置 · 安全中心」移除该规则。"
        )
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    proc = await asyncio.create_subprocess_shell(
        command, cwd=str(current_root()), env=scrubbed_env(),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, **kwargs,
    )
    communicate = asyncio.create_task(proc.communicate())
    stop_task = asyncio.create_task(stop.wait())
    done, _ = await asyncio.wait(
        {communicate, stop_task}, timeout=max(0.1, tool.timeout_seconds),
        return_when=asyncio.FIRST_COMPLETED,
    )
    if communicate in done:
        stop_task.cancel()
        stdout, stderr = await communicate
        security.audit(owner, tool.name, command, "executed")
        out = stdout.decode(errors="replace")
        if stderr:
            out += "\n[stderr]\n" + stderr.decode(errors="replace")
        out = out.strip() or "（无输出）"
        if len(out) > 6000:
            out = out[:6000] + f"\n… [截断，共 {len(out)} 字符]"
        return ToolOutcome(text=f"退出码 {proc.returncode}\n{out}")
    await _kill_process_tree(proc)
    communicate.cancel()
    if stop_task in done and stop.is_set():
        security.audit(owner, tool.name, command, "cancelled")
        raise ToolExecutionCancelled()
    stop_task.cancel()
    security.audit(owner, tool.name, command, "timeout")
    raise ToolExecutionTimeout(f"tool exceeded {tool.timeout_seconds:g}s")


async def _execute_tool_impl(
    tool: Tool, args: dict[str, Any], stop: asyncio.Event,
    *, authorization: ExecutionAuthorization,
) -> ToolOutcome:
    """Execute under the declared policy; subprocess tools are kill-tree cancellable."""
    started = time.monotonic()
    if tool.isolation == "subprocess":
        if tool.name != "run_command":
            raise RuntimeError(f"unsupported isolated tool: {tool.name}")
        return await _run_command_isolated(tool, args, stop)
    # Every App-registered tool runs in a one-call child process.  Python cannot
    # safely terminate executor threads; a process boundary is the only way to
    # preserve both a real deadline and the no-late-side-effect contract.
    from agent.skills import runtime_tool
    if runtime_tool(tool.name) is not None:
        return await _run_tool_worker(tool, args, stop, owner_id=authorization.owner_id)
    mutating = any(
        permission.endswith((".write", ".manage")) or permission in {"browser.state"}
        for permission in tool.permissions
    )
    if mutating:
        raise ToolExecutionIsolationError(
            f"unregistered mutating tool cannot run in a non-killable thread: {tool.name}"
        )
    # Tests/extensions may supply side-effect-free Tool objects not present in the
    # signed registry. Their Run is still deadline-bounded; cancellation can leave
    # only a read in flight, never a state mutation.
    try:
        return await _wait_or_stop(
            asyncio.to_thread(run_tool, tool, args), stop, tool.timeout_seconds,
        )
    except ToolExecutionTimeout as exc:
        raise ToolExecutionTimeout(
            f"{tool.name} exceeded {tool.timeout_seconds:g}s after {time.monotonic() - started:.2f}s"
        ) from exc


async def execute_tool(
    tool: Tool, args: dict[str, Any], stop: asyncio.Event,
    *, authorization: ExecutionAuthorization,
) -> ToolOutcome:
    """Authorize, arbitrate shared Run resources, then execute one tool call."""
    from agent import run_resources

    if stop.is_set():
        raise ToolExecutionCancelled()
    authorization.enforce(tool.name, args, tool.permissions)
    async with run_resources.acquire(tool.permissions):
        return await _execute_tool_impl(tool, args, stop, authorization=authorization)


async def execute_async_call(
    awaitable: Awaitable[Any], stop: asyncio.Event, timeout_seconds: float,
    *, authorization: ExecutionAuthorization, tool_name: str,
    args: dict[str, Any], permissions: tuple[str, ...],
) -> Any:
    """Apply the same deadline/cancel classification to cancellable async adapters (MCP)."""
    from agent import run_resources

    authorization.enforce(tool_name, args, permissions)
    async with run_resources.acquire(permissions):
        return await _wait_or_stop(awaitable, stop, timeout_seconds)
