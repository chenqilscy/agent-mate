"""Workspace sandbox (spec 8, hard-line #2).

Default permission = tools may only touch paths inside `workspace/`. Any resolved
path that escapes the root is rejected. `run_cmd`/`edit_file` (M2) route through
here; the files router uses it too so the viewer can never read outside the box.
"""
from __future__ import annotations

from pathlib import Path

from config import settings

WORKSPACE_ROOT: Path = settings.WORKSPACE_ROOT


class SandboxError(PermissionError):
    pass


def resolve_in_sandbox(rel_or_abs: str) -> Path:
    """Resolve a user-supplied path and assert it stays within the workspace."""
    root = WORKSPACE_ROOT.resolve()
    candidate = (root / rel_or_abs).resolve() if not Path(rel_or_abs).is_absolute() else Path(rel_or_abs).resolve()
    if candidate != root and root not in candidate.parents:
        raise SandboxError(f"路径越界（沙箱外）：{rel_or_abs}")
    return candidate


def relpath(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(WORKSPACE_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(p)
