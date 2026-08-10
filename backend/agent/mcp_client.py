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
from mcp.client.sse import sse_client
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
def connector_specs(owner_id: str = "") -> dict[str, dict[str, Any]]:
    """连接器名 → 启动 spec，读自 DB（enabled 行）。替代原硬编码的 CONNECTORS 字典。"""
    from storage import db  # 局部 import：避免 storage.db ↔ agent.* 的模块级循环依赖
    specs = db.connector_specs()
    if owner_id:
        import local_agent_store
        for item in local_agent_store.list_connector_instances(owner_id, enabled_only=True):
            specs[item["name"]] = {
                "transport": item["transport"], "command": item["command"],
                "args": item["args"], "url": item["url"], "env": item["environment"],
                "secret_keys": item["secret_keys"], "_instance_id": item["id"],
                "_health_status": item["health_status"], "_source": "local",
            }
    return specs


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


def _credential(owner_id: str, connector_name: str, spec: dict[str, Any], key: str) -> str:
    if owner_id:
        import local_agent_store
        instance_id = str(spec.get("_instance_id") or "")
        local = (
            local_agent_store.get_connector_secret(owner_id, instance_id, key)
            if instance_id else local_agent_store.get_builtin_connector_secret(owner_id, connector_name, key)
        )
        if local:
            return local.strip()
        # Owner-created connector definitions are untrusted input.  They may
        # name a credential but must never use that name to read an unrelated
        # secret from the Local Agent process environment.  Environment
        # fallback is retained only for trusted catalog/built-in definitions.
        if instance_id:
            return ""
    return os.environ.get(key, "").strip()


def _secret_env(spec: dict[str, Any], *, owner_id: str, connector_name: str) -> dict[str, str]:
    """A connector's own declared credentials, read from host env / backend .env
    and injected into ONLY that connector's subprocess (target var name → value).
    Nothing else from os.environ crosses over (WB-011)."""
    out: dict[str, str] = {}
    for target, source_key in spec.get("secret_env", {}).items():
        val = _credential(owner_id, connector_name, spec, str(source_key))
        if val:
            out[target] = val
    for target in spec.get("secret_keys", []):
        val = _credential(owner_id, connector_name, spec, str(target))
        if val:
            out[str(target)] = val
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
    names: list[str], *, env: dict[str, str] | None = None, owner_id: str = "",
    allow_unhealthy: bool = False,
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
    specs = connector_specs(owner_id)  # trusted built-ins + owner-scoped local instances

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
            skipped.append({"name": name, "reason": "本机未提供可信运行定义或定义不兼容"})
            continue
        if spec.get("_instance_id") and spec.get("_health_status") != "healthy" and not allow_unhealthy:
            skipped.append({"name": name, "reason": "本机连接器尚未通过连通测试"})
            continue
        missing = [
            str(key) for key in spec.get("requires", [])
            if not _credential(owner_id, name, spec, str(key))
        ]
        missing.extend(
            str(key) for key in spec.get("secret_keys", [])
            if not _credential(owner_id, name, spec, str(key))
        )
        if missing:
            skipped.append({"name": name, "reason": f"缺少本机凭据 {', '.join(dict.fromkeys(missing))}"})
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

        if spec.get("transport") == "sse":
            url = str(spec.get("url") or "")
            if not url:
                skipped.append({"name": name, "reason": "SSE 地址未配置"})
                continue
            headers = {
                **{str(k): str(v) for k, v in spec.get("env", {}).items()},
                **_secret_env(spec, owner_id=owner_id, connector_name=name),
            }
            try:
                read, write = await stack.enter_async_context(
                    sse_client(url, headers=headers, timeout=_CONNECT_TIMEOUT)
                )
                session = await stack.enter_async_context(ClientSession(read, write))
                await asyncio.wait_for(session.initialize(), timeout=_CONNECT_TIMEOUT)
                _collect(name, idx, session, await asyncio.wait_for(session.list_tools(), timeout=_CONNECT_TIMEOUT))
            except asyncio.TimeoutError:
                skipped.append({"name": name, "reason": "连接超时"})
            except Exception:  # noqa: BLE001
                skipped.append({"name": name, "reason": "连接失败"})
            continue

        # ── Third-party server: spawn as a stdio subprocess. A frozen bundle can
        #    wedge on a held-open subprocess, so gate it (opt back in with
        #    AGENTMATE_BUNDLE_CONNECTORS=1).
        if getattr(sys, "frozen", False) and os.environ.get("AGENTMATE_BUNDLE_CONNECTORS") != "1":
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
                **_secret_env(spec, owner_id=owner_id, connector_name=name),
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


def connector_statuses(owner_id: str) -> list[dict[str, Any]]:
    """Return a sanitized, actionable readiness view for the App."""
    import local_agent_store
    instances = local_agent_store.list_connector_instances(owner_id)
    instances_by_id = {str(item["id"]): item for item in instances}
    result: list[dict[str, Any]] = []
    for name, spec in connector_specs(owner_id).items():
        required = [str(item) for item in spec.get("requires", [])]
        required.extend(str(item) for item in spec.get("secret_keys", []))
        missing_credentials = [
            key for key in dict.fromkeys(required) if not _credential(owner_id, name, spec, key)
        ]
        missing_bins = [str(item) for item in spec.get("requires_bin", []) if not shutil.which(str(item))]
        instance_id = str(spec.get("_instance_id") or "")
        health = str(spec.get("_health_status") or "ready")
        configured = not missing_credentials and not missing_bins
        healthy = configured and (not instance_id or health == "healthy")
        result.append({
            "id": instance_id or f"builtin:{name}", "name": name,
            "source": "local" if instance_id else "builtin",
            "transport": str(spec.get("transport") or ("builtin" if spec.get("builtin_server") else "stdio")),
            "enabled": True, "configured": configured, "healthy": healthy,
            "health_status": health if configured else "blocked",
            "last_error": (
                f"缺少凭据：{', '.join(missing_credentials)}" if missing_credentials
                else f"未安装：{', '.join(missing_bins)}" if missing_bins
                else ""
            ),
            "credential_keys": list(dict.fromkeys(required)),
            "tool_count": int(instances_by_id.get(instance_id, {}).get("tool_count", 0)) if instance_id else 0,
        })
    visible_ids = {str(item["id"]) for item in result}
    for instance in instances:
        instance_id = str(instance["id"])
        if instance_id in visible_ids:
            continue
        # Disabled instances are intentionally excluded from connector_specs(),
        # but must remain visible so the App can edit or enable them again.
        result.append({
            "id": instance_id,
            "name": str(instance["name"]),
            "source": "local",
            "transport": str(instance["transport"]),
            "enabled": bool(instance["enabled"]),
            "configured": True,
            "healthy": False,
            "health_status": "disabled" if not instance["enabled"] else str(instance["health_status"]),
            "last_error": str(instance.get("last_error") or ""),
            "credential_keys": list(instance.get("secret_keys") or []),
            "tool_count": int(instance.get("tool_count") or 0),
        })
    return result


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
