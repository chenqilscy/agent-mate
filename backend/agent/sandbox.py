"""Workspace sandbox (spec 8, hard-line #2) — now per-project (§11.2).

Each project gets its own checkout: `workspace/projects/<project_id>/`; ad-hoc
(non-project) chats use `workspace/default/`. The active root is a contextvar set
per request (run_chat sets it from the session's project_id); tools read it, so
their signatures don't change and concurrent requests stay isolated.

Any resolved path that escapes the active root is rejected.
"""
from __future__ import annotations

import contextvars
from pathlib import Path

from config import settings

WORKSPACE_BASE: Path = settings.WORKSPACE_ROOT
DEFAULT_ROOT: Path = WORKSPACE_BASE / "default"

# The active workspace root for the current request/task.
_current: contextvars.ContextVar[Path] = contextvars.ContextVar("workspace_root", default=DEFAULT_ROOT)


class SandboxError(PermissionError):
    pass


def project_root(project_id: str | None) -> Path:
    """Resolve the workspace root for a project (or the shared default)."""
    if project_id:
        return WORKSPACE_BASE / "projects" / project_id
    return DEFAULT_ROOT


def assistant_root(assistant_id: str) -> Path:
    """助理专属工作空间（WB-087）：`workspace/assistants/<id>/`。"""
    return WORKSPACE_BASE / "assistants" / assistant_id


def workspace_root(spec: str | None, project_id: str | None = None) -> Path:
    """按助理 workspace 规格解析根（WB-087）：
    `default`/None→默认；`project:<id>`→该项目根；`dedicated:<assistant_id>`→助理专属根。
    project_id 作为 `dedicated`/`default` 之外的回退（会话本身带的项目）。"""
    if spec and spec.startswith("project:"):
        return project_root(spec.split(":", 1)[1])
    if spec and spec.startswith("dedicated:"):
        return assistant_root(spec.split(":", 1)[1])
    return project_root(project_id)


def use_root(root: Path) -> None:
    """Set the active workspace root for this request/task (creates it)."""
    root.mkdir(parents=True, exist_ok=True)
    _current.set(root)


def current_root() -> Path:
    return _current.get()


def resolve_in_sandbox(rel_or_abs: str, root: Path | None = None) -> Path:
    """Resolve a user-supplied path and assert it stays within the active root."""
    base = (root or current_root()).resolve()
    base.mkdir(parents=True, exist_ok=True)
    candidate = (
        Path(rel_or_abs).resolve()
        if Path(rel_or_abs).is_absolute()
        else (base / rel_or_abs).resolve()
    )
    if candidate != base and base not in candidate.parents:
        raise SandboxError(f"路径越界（沙箱外）：{rel_or_abs}")
    return candidate


def relpath(p: Path, root: Path | None = None) -> str:
    base = (root or current_root()).resolve()
    try:
        return str(p.resolve().relative_to(base)).replace("\\", "/")
    except ValueError:
        return str(p)
