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


def text(md: str) -> str:
    """A chunk of assistant prose (token-level increment)."""
    return sse("text", {"md": md})


def ask_user(questions: list[dict[str, Any]]) -> str:
    return sse("ask_user", {"questions": questions})


def artifact(name: str, size: str, path: str) -> str:
    return sse("artifact", {"name": name, "size": size, "path": path})


def usage(pct: float, used: int, detail: dict[str, Any] | None = None) -> str:
    return sse("usage", {"pct": round(pct, 2), "used": used, "detail": detail or {}})


def error(message: str) -> str:
    return sse("error", {"message": message})


def done(message_id: str | None = None) -> str:
    return sse("done", {"message_id": message_id} if message_id else {})
