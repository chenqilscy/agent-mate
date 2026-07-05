"""MCP client (decision A.4 — the connector moat, Python `mcp` SDK).

Spawns a connector's stdio MCP server, discovers its tools, and lets the agent
call them. Real connectors (GitHub / 腾讯文档 / …) are the same shape — a different
launch command — so adding one is registry config, not new plumbing.

We use MCP's stdio CLIENT only (not its SSE server), which is why starlette is
pinned back to the FastAPI-compatible version in requirements.txt.
"""
from __future__ import annotations

import os
import re
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

_BACKEND = Path(__file__).resolve().parent.parent
_NOTES_SERVER = str(_BACKEND / "mcp_servers" / "notes.py")

# Connector name → how to launch its MCP server. The demo 本地便签 connector proves
# the full stdio round-trip with zero external deps/credentials. To add a real
# connector, register its command here (e.g. an npx-based GitHub MCP server).
CONNECTORS: dict[str, dict[str, Any]] = {
    "本地便签": {"command": sys.executable, "args": [_NOTES_SERVER]},
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
) -> tuple[list[McpTool], AsyncExitStack]:
    """Spawn each enabled connector's MCP server and list its tools.

    Returns (mcp_tools, exit_stack). Close the stack when the run finishes to
    terminate the servers. A connector that fails to start is skipped so it can't
    take down the chat.
    """
    stack = AsyncExitStack()
    tools: list[McpTool] = []
    for idx, name in enumerate(names):
        spec = CONNECTORS.get(name)
        if not spec:
            continue
        params = StdioServerParameters(
            command=spec["command"],
            args=spec.get("args", []),
            # Force UTF-8 stdio — MCP frames JSON as UTF-8, but a Python server on
            # Windows defaults to the system codepage (GBK), which corrupts CJK.
            # Base env is a secret-free whitelist (WB-011), not the whole os.environ.
            env={
                **_safe_base_env(),
                **(env or {}),
                **spec.get("env", {}),
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
            },
        )
        try:
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            listed = await session.list_tools()
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
        except Exception:  # noqa: BLE001 — a broken connector must not break chat
            continue
    return tools, stack


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
