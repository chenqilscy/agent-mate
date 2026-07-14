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
from mcp.shared.memory import create_connected_server_and_client_session

_BACKEND = Path(__file__).resolve().parent.parent
_SERVERS = _BACKEND / "mcp_servers"


def _builtin_fastmcp(server: str):
    """The FastMCP instance for a built-in server (imported lazily)."""
    if server == "notes":
        from mcp_servers.notes import mcp
        return mcp
    if server == "clock":
        from mcp_servers.clock import mcp
        return mcp
    if server == "search":
        from mcp_servers.search import mcp
        return mcp
    if server == "telegram":
        from mcp_servers.telegram import mcp
        return mcp
    if server == "kdocs":
        from mcp_servers.kdocs import mcp
        return mcp
    return None

# Connector definitions live in the DB now (catalog_connectors, WB-059) — the old
# hardcoded CONNECTORS dict was migrated there and seeded on first start
# (storage/catalog_seed.py). Same launch-spec shape, now data not code:
#   built-in (local)  → {"builtin_server": "<name>", "builtin": True[, "requires":[...], "requires_bin":[...]]}
#       ships as a small FastMCP server under mcp_servers/ and runs IN-PROCESS via
#       MCP's in-memory transport (no subprocess) — works identically in dev and in
#       a PyInstaller bundle (a subprocess held open inside the SSE stream wedges a
#       frozen build, A2.1; an in-process server doesn't).
#   third-party stdio → {"command","args","secret_env","requires"[,"requires_bin"]}
#       `secret_env` forwards ONLY that connector's credential to its own process —
#       never `os.environ` wholesale (WB-011); `requires` skips a run missing the
#       token with a clear reason instead of a silent failure.
def connector_specs() -> dict[str, dict[str, Any]]:
    """连接器名 → 启动 spec，读自 DB（enabled 行）。替代原硬编码的 CONNECTORS 字典。"""
    from storage import db  # 局部 import：避免 storage.db ↔ agent.* 的模块级循环依赖
    return db.connector_specs()


def is_connector(name: str) -> bool:
    return name in connector_specs()


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
    specs = connector_specs()  # name → launch spec, from DB (WB-059)

    def _collect(name: str, idx: int, session: ClientSession, listed: Any) -> None:
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

    for idx, name in enumerate(names):
        spec = specs.get(name)
        if not spec:
            skipped.append({"name": name, "reason": "未内置该连接器"})
            continue
        missing = [k for k in spec.get("requires", []) if not os.environ.get(k, "").strip()]
        if missing:
            skipped.append({"name": name, "reason": f"需在 backend/.env 配置 {', '.join(missing)}"})
            continue
        # `requires_bin`: an external CLI must be on PATH (e.g. kdocs-cli for 金山文档,
        # whose auth is OAuth→keychain, not an env token). Missing → clean skip.
        missing_bin = [b for b in spec.get("requires_bin", []) if not shutil.which(b)]
        if missing_bin:
            skipped.append({"name": name, "reason": f"未安装 {', '.join(missing_bin)}"})
            continue

        # ── Built-in server: run IN-PROCESS via MCP's in-memory transport (no
        #    subprocess). Works in dev and in a frozen bundle alike. The server task
        #    is created here, inside this run's context, so it reads the per-run
        #    workspace root from the sandbox contextvar (current_root) at call time.
        #    We must NOT stash the dir in process-global os.environ — two concurrent
        #    runs in different projects would clobber each other's dir (WB-154).
        if spec.get("builtin_server"):
            fastmcp = _builtin_fastmcp(spec["builtin_server"])
            if fastmcp is None:
                skipped.append({"name": name, "reason": "内置服务缺失"})
                continue
            try:
                session = await stack.enter_async_context(
                    create_connected_server_and_client_session(fastmcp._mcp_server)
                )
                _collect(name, idx, session, await session.list_tools())
            except Exception:  # noqa: BLE001 — a broken connector must not break chat
                skipped.append({"name": name, "reason": "启动失败"})
            continue

        # ── Third-party server: spawn as a stdio subprocess. A frozen bundle can
        #    wedge on a held-open subprocess, so gate it (opt back in with
        #    WORKBUDDY_BUNDLE_CONNECTORS=1).
        if getattr(sys, "frozen", False) and os.environ.get("WORKBUDDY_BUNDLE_CONNECTORS") != "1":
            skipped.append({"name": name, "reason": "桌面打包版暂不支持该连接器（开发环境可用）"})
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
            async def _connect() -> tuple[ClientSession, Any, AsyncExitStack]:
                # Own the spawn in a LOCAL stack: if wait_for times out and cancels us
                # mid-handshake, tear the child process down HERE instead of orphaning
                # it (a cleanup not yet registered on the run-level stack would leak —
                # WB-160).
                local = AsyncExitStack()
                try:
                    read, write = await local.enter_async_context(stdio_client(params))
                    session = await local.enter_async_context(ClientSession(read, write))
                    await session.initialize()
                    return session, await session.list_tools(), local
                except BaseException:
                    await local.aclose()
                    raise

            session, listed, local = await asyncio.wait_for(_connect(), timeout=_CONNECT_TIMEOUT)
            await stack.enter_async_context(local)  # 交给 run 级 stack 统一在结束时关闭
            _collect(name, idx, session, listed)
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
