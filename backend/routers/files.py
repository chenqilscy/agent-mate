"""Workspace files — tree + content, per-project scoped (spec 5.1 / §11.2).

`?session=` or `?project=` selects which workspace root to read (a project's own
checkout, or the shared default). Strictly sandbox-scoped either way.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException

from agent.sandbox import (
    SandboxError,
    current_root,
    project_root,
    relpath,
    resolve_in_sandbox,
    use_root,
)
from storage import db

router = APIRouter(prefix="/api/files", tags=["files"])

_TEXT_EXT = {
    ".md", ".txt", ".json", ".js", ".ts", ".tsx", ".jsx", ".py", ".css",
    ".html", ".yaml", ".yml", ".toml", ".sh", ".conf", ".env", ".xml", ".csv",
}
_MAX_BYTES = 512 * 1024
_SKIP = {"node_modules", "__pycache__", ".git", ".venv"}
_MAX_DEPTH = 4


def _select_root(session: str | None, project: str | None) -> None:
    """Set the active workspace root from ?project= / ?session=."""
    if project:
        use_root(project_root(project))
        return
    if session:
        s = db.get_session(session)
        use_root(project_root(s.project_id if s else None))
        return
    use_root(project_root(None))


def _entry(p: Path, depth: int) -> dict:
    is_dir = p.is_dir()
    node: dict = {
        "name": p.name,
        "path": relpath(p),
        "type": "d" if is_dir else "f",
        "size": None if is_dir else p.stat().st_size,
    }
    if is_dir and depth < _MAX_DEPTH:
        node["children"] = _children(p, depth + 1)
    return node


def _children(base: Path, depth: int) -> list[dict]:
    out = []
    for child in sorted(base.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        if child.name.startswith(".") or child.name in _SKIP:
            continue
        out.append(_entry(child, depth))
    return out


@router.get("/tree")
def tree(root: str = "workspace", session: str | None = None, project: str | None = None) -> dict:
    _select_root(session, project)
    base = current_root()
    if not base.exists():
        return {"root": "workspace", "entries": []}
    return {"root": "workspace", "entries": _children(base, 0)}


@router.get("/content")
def content(path: str, session: str | None = None, project: str | None = None) -> dict:
    _select_root(session, project)
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
