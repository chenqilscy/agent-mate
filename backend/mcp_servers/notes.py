"""A tiny real MCP server (stdio) used to prove the connector round-trip locally.

It exposes two tools over the Model Context Protocol — add_note / list_notes —
backed by a JSON file in the project workspace (WORKBUDDY_NOTES_DIR). Real
connectors (GitHub / 腾讯文档 / …) are the same shape: a different MCP server
launched the same way. Run standalone: `python notes.py` (speaks MCP on stdio).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("notes")


def _file() -> Path:
    # Resolved at call time (not import) so this server works both as a spawned
    # subprocess (env set at spawn) and in-process (env set per run).
    return Path(os.environ.get("WORKBUDDY_NOTES_DIR", ".")).resolve() / "notes.json"


def _load() -> list[str]:
    f = _file()
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save(notes: list[str]) -> None:
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")


@mcp.tool()
def add_note(text: str) -> str:
    """添加一条便签到本地便签本。"""
    notes = _load()
    notes.append(text)
    _save(notes)
    return f"已记录第 {len(notes)} 条便签：{text}"


@mcp.tool()
def list_notes() -> str:
    """列出本地便签本里的所有便签。"""
    notes = _load()
    if not notes:
        return "（暂无便签）"
    return "\n".join(f"{i + 1}. {n}" for i, n in enumerate(notes))


if __name__ == "__main__":
    mcp.run()
