"""Uniform timeout/cancellation boundary for built-in tools (WB-248)."""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from typing import Any, Awaitable

from agent import security
from agent.execution_policy import ExecutionAuthorization
from agent.sandbox import current_root
from agent.tools import Tool, ToolOutcome, run_tool
from config import scrubbed_env


class ToolExecutionTimeout(TimeoutError):
    pass


class ToolExecutionCancelled(asyncio.CancelledError):
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


async def _wait_thread_or_stop(
    awaitable: Awaitable[Any], stop: asyncio.Event, timeout: float,
) -> Any:
    """Do not report cancellation while an in-process worker can still mutate state.

    Python cannot kill a running executor thread. Once cancellation/deadline wins we
    therefore wait for the bounded tool call to reach its side-effect boundary,
    then classify the result as cancelled/timeout. Hazardous unbounded work belongs
    in subprocess isolation instead.
    """
    task = asyncio.ensure_future(awaitable)
    stop_task = asyncio.create_task(stop.wait())
    try:
        done, _ = await asyncio.wait(
            {task, stop_task}, timeout=max(0.1, timeout), return_when=asyncio.FIRST_COMPLETED,
        )
        if task in done:
            return await task
        cancelled = stop_task in done and stop.is_set()
        try:
            await asyncio.shield(task)
        except Exception:
            # The deadline/cancel decision is authoritative; the worker exception
            # is still consumed so it cannot become an unobserved task warning.
            pass
        if cancelled:
            raise ToolExecutionCancelled()
        raise ToolExecutionTimeout(f"tool exceeded {timeout:g}s")
    except asyncio.CancelledError:
        # Generator disconnect is also not allowed to leave a late in-process write.
        if not task.done():
            try:
                await asyncio.shield(task)
            except Exception:
                pass
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


async def execute_tool(
    tool: Tool, args: dict[str, Any], stop: asyncio.Event,
    *, authorization: ExecutionAuthorization,
) -> ToolOutcome:
    """Execute under the declared policy; subprocess tools are kill-tree cancellable."""
    if stop.is_set():
        raise ToolExecutionCancelled()
    authorization.enforce(tool.name, args, tool.permissions)
    started = time.monotonic()
    if tool.isolation == "subprocess":
        if tool.name != "run_command":
            raise RuntimeError(f"unsupported isolated tool: {tool.name}")
        return await _run_command_isolated(tool, args, stop)
    try:
        return await _wait_thread_or_stop(
            asyncio.to_thread(run_tool, tool, args), stop, tool.timeout_seconds,
        )
    except ToolExecutionTimeout as exc:
        raise ToolExecutionTimeout(
            f"{tool.name} exceeded {tool.timeout_seconds:g}s after {time.monotonic() - started:.2f}s"
        ) from exc


async def execute_async_call(
    awaitable: Awaitable[Any], stop: asyncio.Event, timeout_seconds: float,
    *, authorization: ExecutionAuthorization, tool_name: str,
    args: dict[str, Any], permissions: tuple[str, ...],
) -> Any:
    """Apply the same deadline/cancel classification to cancellable async adapters (MCP)."""
    authorization.enforce(tool_name, args, permissions)
    return await _wait_or_stop(awaitable, stop, timeout_seconds)
