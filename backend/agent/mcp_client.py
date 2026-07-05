"""MCP client (decision A.4 — the connector moat, Python `mcp` SDK).

Spawns a connector's stdio MCP server, discovers its tools, and lets the agent
call them. Real connectors (GitHub / 腾讯文档 / …) are the same shape — a different
launch command — so adding one is registry config, not new plumbing.

We use MCP's stdio CLIENT only (not its SSE server), which is why starlette is
pinned back to the FastAPI-compatible version in requirements.txt.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters

# A connector that doesn't finish its MCP handshake in this many seconds is
# skipped, never hanging the chat — covers a wedged third-party server as well as
# the slow/broken local-server spawn seen in some bundled builds.
_CONNECT_TIMEOUT = 12.0
from mcp.client.stdio import stdio_client

_BACKEND = Path(__file__).resolve().parent.parent
_SERVERS = _BACKEND / "mcp_servers"


def _local(server: str) -> dict[str, Any]:
    """Launch spec for a built-in local FastMCP server. In dev, run the .py with
    the interpreter; in a PyInstaller bundle (no interpreter to run a .py), re-exec
    the app itself as `WorkBuddy.exe --mcp-server=<server>` (main.py routes it)."""
    if getattr(sys, "frozen", False):
        return {"command": sys.executable, "args": [f"--mcp-server={server}"], "builtin": True}
    return {"command": sys.executable, "args": [str(_SERVERS / f"{server}.py")], "builtin": True}

# Connector name → how to launch its MCP server.
#
# Built-in (local) connectors ship as small FastMCP servers under mcp_servers/
# and work out of the box — zero external deps or credentials. Third-party
# connectors (GitHub / …) declare `secret_env` (host env var → subprocess env
# var) so their credential is forwarded ONLY to that connector's process — never
# `os.environ` wholesale (WB-011) — and `requires` so a run without the token is
# skipped with a clear reason instead of a silent failure.
CONNECTORS: dict[str, dict[str, Any]] = {
    # ── built-in, no setup ──
    "本地便签": _local("notes"),
    "时间助手": _local("clock"),
    "工作区检索": _local("search"),
    # ── third-party, needs a token in backend/.env ──
    "GitHub": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "secret_env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "GITHUB_TOKEN"},
        "requires": ["GITHUB_TOKEN"],
    },
}


def is_connector(name: str) -> bool:
    return name in CONNECTORS


# Only these (harmless, needed-to-launch) host env vars are forwarded to a
# connector subprocess. A whitelist — never `os.environ` wholesale — so the
# backend's LLM_API_KEY / LLM_API_BASE and any other secret can't leak into a
# third-party MCP server's process (WB-011, hard-line #4).
_SAFE_ENV = {
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "SYSTEMDRIVE",
    "TEMP", "TMP", "TMPDIR", "HOME", "HOMEPATH", "HOMEDRIVE", "USERPROFILE",
    "APPDATA", "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA",
    "LANG", "LC_ALL", "LC_CTYPE", "TZ", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
}


def _safe_base_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k.upper() in _SAFE_ENV}


def _secret_env(spec: dict[str, Any]) -> dict[str, str]:
    """A connector's own declared credentials, read from host env / backend .env
    and injected into ONLY that connector's subprocess (target var name → value).
    Nothing else from os.environ crosses over (WB-011)."""
    out: dict[str, str] = {}
    for target, source_key in spec.get("secret_env", {}).items():
        val = os.environ.get(source_key, "").strip()
        if val:
            out[target] = val
    return out


def _resolve_command(command: str) -> str:
    """Resolve a launcher to a runnable path. On Windows `npx` is `npx.cmd`; a
    bare name won't spawn without shell, so resolve it via PATH when possible."""
    return shutil.which(command) or command


@dataclass
class McpTool:
    connector: str
    qualified: str  # mcp__<slug>__<tool> — namespaced to avoid collisions
    orig: str
    description: str
    schema: dict[str, Any]
    session: ClientSession


def _slug(name: str, idx: int) -> str:
    # Function names sent to the LLM must be ASCII [a-zA-Z0-9_-]; a Chinese
    # connector name would be rejected, so strip to ASCII (index fallback).
    s = re.sub(r"[^a-zA-Z0-9_]+", "", name)[:16]
    return s or f"c{idx}"


async def open_connectors(
    names: list[str], *, env: dict[str, str] | None = None
) -> tuple[list[McpTool], AsyncExitStack, list[dict[str, str]]]:
    """Spawn each enabled connector's MCP server and list its tools.

    Returns (mcp_tools, exit_stack, skipped). `skipped` is a list of
    {name, reason} so the caller can tell the user why a selected connector
    didn't load (unknown / missing credential / launch failure) instead of it
    silently vanishing. Close the stack when the run finishes to terminate the
    servers. A connector that fails to start is skipped, never breaking the chat.
    """
    stack = AsyncExitStack()
    tools: list[McpTool] = []
    skipped: list[dict[str, str]] = []
    for idx, name in enumerate(names):
        spec = CONNECTORS.get(name)
        if not spec:
            skipped.append({"name": name, "reason": "未内置该连接器"})
            continue
        # Bundled (PyInstaller) build: an MCP server subprocess held open inside a
        # streaming response wedges the SSE stream on the frozen event loop (open
        # follow-up). Skip cleanly so chat still works; connectors are dev-only for
        # now. (Fix path: onedir build or an embedded interpreter.)
        if getattr(sys, "frozen", False):
            skipped.append({"name": name, "reason": "桌面打包版暂不支持连接器（开发环境可用）"})
            continue
        missing = [k for k in spec.get("requires", []) if not os.environ.get(k, "").strip()]
        if missing:
            skipped.append({"name": name, "reason": f"需在 backend/.env 配置 {', '.join(missing)}"})
            continue
        params = StdioServerParameters(
            command=_resolve_command(spec["command"]),
            args=spec.get("args", []),
            # Force UTF-8 stdio — MCP frames JSON as UTF-8, but a Python server on
            # Windows defaults to the system codepage (GBK), which corrupts CJK.
            # Base env is a secret-free whitelist (WB-011); only this connector's
            # own declared secret_env credentials are added on top.
            env={
                **_safe_base_env(),
                **(env or {}),
                **spec.get("env", {}),
                **_secret_env(spec),
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
            },
        )
        try:
            async def _connect() -> tuple[ClientSession, Any]:
                read, write = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                return session, await session.list_tools()

            session, listed = await asyncio.wait_for(_connect(), timeout=_CONNECT_TIMEOUT)
            for t in listed.tools:
                safe_tool = re.sub(r"[^a-zA-Z0-9_-]+", "_", t.name)[:40]
                tools.append(
                    McpTool(
                        connector=name,
                        qualified=f"mcp__{_slug(name, idx)}__{safe_tool}",
                        orig=t.name,
                        description=t.description or "",
                        schema=t.inputSchema or {"type": "object", "properties": {}},
                        session=session,
                    )
                )
        except asyncio.TimeoutError:
            skipped.append({"name": name, "reason": "启动超时"})
            continue
        except Exception:  # noqa: BLE001 — a broken connector must not break chat
            skipped.append({"name": name, "reason": "启动失败"})
            continue
    return tools, stack, skipped


def mcp_schema(t: McpTool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": t.qualified,
            "description": f"[连接器 {t.connector}] {t.description}",
            "parameters": t.schema,
        },
    }


async def call_mcp(t: McpTool, args: dict[str, Any]) -> str:
    try:
        res = await t.session.call_tool(t.orig, arguments=args)
    except Exception as e:  # noqa: BLE001
        return f"连接器调用失败：{e}"
    parts: list[str] = []
    for c in res.content:
        text = getattr(c, "text", None)
        parts.append(text if text is not None else str(c))
    return "\n".join(parts) or "(无输出)"
