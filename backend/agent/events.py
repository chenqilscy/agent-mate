"""Typed SSE event protocol (spec 5.2).

One event type ⇄ one DOM shape in the UI. The frontend renders purely by
consuming these; the backend never sends HTML. Serialised as standard SSE:

    event: <type>\n
    data: <json>\n\n
"""
from __future__ import annotations

import json
from typing import Any


def sse(event: str, data: dict[str, Any] | None = None) -> str:
    payload = json.dumps(data or {}, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


# Convenience builders — keep event names in one place.

def status(state: str, secs: int | None = None) -> str:
    d: dict[str, Any] = {"state": state}
    if secs is not None:
        d["secs"] = secs
    return sse("status", d)


def run(item: dict[str, Any], user_message_id: str | None = None) -> str:
    """Stable execution identity/lifecycle, separate from its Session (WB-242)."""
    data: dict[str, Any] = {"run": item}
    if user_message_id:
        data["user_message_id"] = user_message_id
    return sse("run", data)


def think(text: str = "深度思考") -> str:
    return sse("think", {"text": text})


def step(tool: str, label: str | None = None) -> str:
    return sse("step", {"tool": tool, "label": label or f"处理{tool}"})


def file_read(path: str, rng: str = "") -> str:
    return sse("file_read", {"path": path, "range": rng})


def diff(op: str, file: str, add: int, delete: int) -> str:
    return sse("diff", {"op": op, "file": file, "add": add, "del": delete})


def todo(text: str) -> str:
    return sse("todo", {"text": text})


def plan_snapshot(
    version: int, items: list[dict[str, Any]], project_id: str | None = None,
) -> str:
    return sse("plan_snapshot", {
        "version": max(0, int(version)), "items": items, "project_id": project_id,
    })


def plan_patch(
    version: int, items: list[dict[str, Any]], project_id: str | None = None,
) -> str:
    return sse("plan_patch", {
        "version": max(0, int(version)), "items": items, "project_id": project_id,
    })


def text(md: str) -> str:
    """A chunk of assistant prose (token-level increment)."""
    return sse("text", {"md": md})


def ask_user(questions: list[dict[str, Any]]) -> str:
    return sse("ask_user", {"questions": questions})


def qa_summary(qa: list[dict[str, Any]]) -> str:
    """The answered question card (Q→A pairs), shown in the trace after ask_user."""
    return sse("qa_summary", {"qa": qa})


def context_degraded(reason: str, excerpt_messages: int) -> str:
    return sse("context_degraded", {
        "reason": reason,
        "excerpt_messages": max(0, int(excerpt_messages)),
        "retry_on_next_turn": True,
    })


def artifact(
    name: str, size: str, path: str, *, artifact_id: str | None = None,
    run_id: str | None = None, sha256: str | None = None,
    mime_type: str | None = None, acceptance_status: str = "pending",
    is_primary: bool = False, display_order: int = 0,
) -> str:
    data: dict[str, Any] = {"name": name, "size": size, "path": path}
    if artifact_id:
        data.update({
            "id": artifact_id, "run_id": run_id, "sha256": sha256,
            "mime_type": mime_type, "acceptance_status": acceptance_status,
            "is_primary": is_primary, "display_order": max(0, int(display_order)),
        })
    return sse("artifact", data)


def work_item(item: dict[str, Any]) -> str:
    """A plan item changed (WB-031) — the frontend syncs its kanban store live.
    Transient: emitted when a tool mutates a work item, NOT persisted in the trace."""
    return sse("work_item", {"item": item})


def usage(pct: float, used: int, detail: dict[str, Any] | None = None) -> str:
    return sse("usage", {"pct": round(pct, 2), "used": used, "detail": detail or {}})


def error(message: str) -> str:
    return sse("error", {"message": message})


def done(message_id: str | None = None) -> str:
    return sse("done", {"message_id": message_id} if message_id else {})
