"""Workspace files — tree + content, strictly sandbox-scoped (spec 5.1)."""
from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException

from agent.sandbox import WORKSPACE_ROOT, SandboxError, relpath, resolve_in_sandbox

router = APIRouter(prefix="/api/files", tags=["files"])

_TEXT_EXT = {
    ".md", ".txt", ".json", ".js", ".ts", ".tsx", ".jsx", ".py", ".css",
    ".html", ".yaml", ".yml", ".toml", ".sh", ".conf", ".env", ".xml", ".csv",
}
_MAX_BYTES = 512 * 1024


def _entry(p: Path) -> dict:
    is_dir = p.is_dir()
    return {
        "name": p.name,
        "path": relpath(p),
        "type": "d" if is_dir else "f",
        "size": None if is_dir else p.stat().st_size,
    }


@router.get("/tree")
def tree(root: str = "workspace") -> dict:
    base = WORKSPACE_ROOT
    if not base.exists():
        return {"root": "workspace", "entries": []}
    entries = []
    for child in sorted(base.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        if child.name.startswith("."):
            continue
        entries.append(_entry(child))
    return {"root": "workspace", "entries": entries}


@router.get("/content")
def content(path: str) -> dict:
    try:
        target = resolve_in_sandbox(path)
    except SandboxError as e:
        raise HTTPException(403, str(e))
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "file not found")

    mime, _ = mimetypes.guess_type(target.name)
    size = target.stat().st_size
    is_text = target.suffix.lower() in _TEXT_EXT

    if is_text and size <= _MAX_BYTES:
        text = target.read_text(encoding="utf-8", errors="replace")
        return {
            "path": relpath(target),
            "name": target.name,
            "mime": mime or "text/plain",
            "kind": "text",
            "content": text,
        }
    return {
        "path": relpath(target),
        "name": target.name,
        "mime": mime or "application/octet-stream",
        "kind": "binary",
        "size": size,
    }
