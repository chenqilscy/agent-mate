"""Trusted one-call subprocess worker for cancellable built-in tools (WB-387).

The parent sends one JSON payload over stdin.  No arguments, credentials or tool
parameters are placed in the command line/environment.  The worker imports the
same signed App registry, restores only the current Run's local execution
context, executes exactly one tool, and writes one JSON result to stdout.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import traceback
from typing import Any


def _configure_paths(payload: dict[str, Any]) -> None:
    # Import config before any storage/agent registry module so scratch DB paths
    # used by tests and alternate desktop data roots remain authoritative.
    from config import settings

    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    for field in ("DB_PATH", "WORKSPACE_ROOT", "SKILLS_DIR"):
        value = str(config.get(field.lower()) or "").strip()
        if value:
            setattr(settings, field, Path(value))
    # AGENTMATE_SERVER_URL belongs to the device-settings database and is
    # deliberately absent from the child environment.  Restore the parent's
    # already-validated, non-secret origin for this one tool invocation.
    settings.AGENTMATE_SERVER_URL = str(config.get("server_url") or "").strip().rstrip("/")


def _restore_context(payload: dict[str, Any]) -> None:
    from agent import security, skill_discovery, skill_resources, skill_usage, skills_store
    from agent.sandbox import use_root
    from agent.tools import restore_knowledge_context, restore_work_context

    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    owner_id = str(context.get("owner_id") or "")
    root = str(context.get("workspace_root") or "")
    if not owner_id or not root:
        raise ValueError("isolated tool context is incomplete")
    use_root(Path(root))
    security.set_security_context(owner_id)
    skills_store.set_owner(owner_id)
    skills_store.set_environment(context.get("environment") or ["adhoc"])
    restore_work_context(context.get("work"))
    restore_knowledge_context(context.get("knowledge"))
    skill_discovery.set_skill_candidates(context.get("skill_candidates") or [])
    skill_resources.set_active_resource_mounts(context.get("skill_resources") or {})
    usage = context.get("skill_usage") if isinstance(context.get("skill_usage"), dict) else {}
    skill_usage.set_context(owner_id, str(usage.get("run_id") or ""))


def run_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _configure_paths(payload)
    _restore_context(payload)
    from agent.skills import runtime_tool
    from agent.tools import run_tool

    tool_name = str(payload.get("tool") or "")
    args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
    tool = runtime_tool(tool_name)
    if tool is None:
        raise ValueError(f"tool is not available in worker registry: {tool_name}")
    outcome = run_tool(tool, args)
    return {
        "text": outcome.text,
        "trace": outcome.trace,
        "live": outcome.live,
        "artifacts": outcome.artifacts,
        "terminal": outcome.terminal,
    }


def main() -> int:
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid isolated tool payload")
        captured = io.StringIO()
        # Keep third-party/tool prints away from the one-message stdout protocol.
        with redirect_stdout(captured), redirect_stderr(captured):
            outcome = run_payload(payload)
        result = {"ok": True, "outcome": outcome}
    except Exception as exc:  # noqa: BLE001 - process boundary returns structured failure
        result = {
            "ok": False,
            "error": str(exc)[:2000],
            "error_type": type(exc).__name__,
            "traceback": traceback.format_exc(limit=8)[-6000:],
        }
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
