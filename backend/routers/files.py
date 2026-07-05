"""Workspace files — tree + content, per-project scoped (spec 5.1 / §11.2).

`?session=` or `?project=` selects which workspace root to read (a project's own
checkout, or the shared default). Strictly sandbox-scoped either way.
"""
from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agent.sandbox import (
    SandboxError,
    current_root,
    project_root,
    relpath,
    resolve_in_sandbox,
    use_root,
)
from auth.deps import current_user
from storage import db

router = APIRouter(prefix="/api/files", tags=["files"])

QUOTA_BYTES = 5 * 1024 ** 3  # 5 GB soft limit (display only)
MAX_UPLOAD = 50 * 1024 * 1024  # 50 MB per file

_TEXT_EXT = {
    ".md", ".txt", ".json", ".js", ".ts", ".tsx", ".jsx", ".py", ".css",
    ".html", ".yaml", ".yml", ".toml", ".sh", ".conf", ".env", ".xml", ".csv",
}
_MAX_BYTES = 512 * 1024
_SKIP = {"node_modules", "__pycache__", ".git", ".venv"}
_MAX_DEPTH = 4


def _select_root(session: str | None, project: str | None) -> None:
    """Set the active workspace root from ?project= / ?session=.

    Ownership is enforced (WB-013): a project/session that isn't the caller's is
    rejected with 404, so file content/download can't be read across owners by
    guessing an id. Same-owner cross-project access is by design.
    """
    owner_id = current_user().id
    if project:
        if not db.get_project(project, owner_id=owner_id):
            raise HTTPException(404, "project not found")
        use_root(project_root(project))
        return
    if session:
        s = db.get_session(session, owner_id=owner_id)
        if not s:
            raise HTTPException(404, "session not found")
        use_root(project_root(s.project_id))
        return
    use_root(project_root(None))


def _entry(p: Path, depth: int) -> dict:
    is_dir = p.is_dir()
    st = p.stat()
    node: dict = {
        "name": p.name,
        "path": relpath(p),
        "type": "d" if is_dir else "f",
        "size": None if is_dir else st.st_size,
        "mtime": st.st_mtime,
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
def tree(session: str | None = None, project: str | None = None) -> dict:
    # (the old `root` query param was dead — the root is chosen by session/project
    # via _select_root; extra query params are ignored — WB-023 cleanup.)
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


# ---- file operations (§11 阶段 C：项目云盘) -----------------------------

class _PathBody(BaseModel):
    path: str
    project: str | None = None
    session: str | None = None


class _RenameBody(_PathBody):
    new_name: str


@router.get("/usage")
def usage(project: str | None = None, session: str | None = None) -> dict:
    _select_root(session, project)
    base = current_root()
    total = 0
    if base.exists():
        for f in base.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    return {"used": total, "quota": QUOTA_BYTES}


@router.post("/upload")
async def upload(request: Request, path: str, project: str | None = None, session: str | None = None) -> dict:
    _select_root(session, project)
    # Reject by declared size first (cheap), then keep enforcing while streaming —
    # a missing/lying Content-Length must not let a huge body fill memory before
    # the check (WB-017).
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_UPLOAD:
        raise HTTPException(413, f"文件过大（>{MAX_UPLOAD // (1024 * 1024)}MB）")
    buf = bytearray()
    async for chunk in request.stream():
        buf.extend(chunk)
        if len(buf) > MAX_UPLOAD:
            raise HTTPException(413, f"文件过大（>{MAX_UPLOAD // (1024 * 1024)}MB）")
    data = bytes(buf)
    try:
        target = resolve_in_sandbox(path)
    except SandboxError as e:
        raise HTTPException(403, str(e))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"ok": True, "path": relpath(target), "size": len(data)}


@router.get("/download")
def download(path: str, project: str | None = None, session: str | None = None):
    _select_root(session, project)
    try:
        target = resolve_in_sandbox(path)
    except SandboxError as e:
        raise HTTPException(403, str(e))
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "file not found")
    return FileResponse(target, filename=target.name)


@router.post("/mkdir")
def mkdir(body: _PathBody) -> dict:
    _select_root(body.session, body.project)
    try:
        target = resolve_in_sandbox(body.path)
    except SandboxError as e:
        raise HTTPException(403, str(e))
    target.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "path": relpath(target)}


@router.post("/rename")
def rename(body: _RenameBody) -> dict:
    _select_root(body.session, body.project)
    try:
        src = resolve_in_sandbox(body.path)
        dst = resolve_in_sandbox(str((Path(body.path).parent / body.new_name)))
    except SandboxError as e:
        raise HTTPException(403, str(e))
    if not src.exists():
        raise HTTPException(404, "not found")
    if dst.exists():
        raise HTTPException(409, "目标已存在")
    src.rename(dst)
    return {"ok": True, "path": relpath(dst), "name": dst.name}


@router.post("/delete")
def delete(body: _PathBody) -> dict:
    _select_root(body.session, body.project)
    try:
        target = resolve_in_sandbox(body.path)
    except SandboxError as e:
        raise HTTPException(403, str(e))
    if target == current_root():
        raise HTTPException(400, "不能删除根目录")
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=True)
    elif target.exists():
        target.unlink()
    return {"ok": True}
