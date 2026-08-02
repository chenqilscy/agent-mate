"""Owner-scoped project health resolution shared by HTTP and automations (WB-352)."""
from __future__ import annotations

import sys
from pathlib import Path

import server_client
from storage import db

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from shared.project_health import build_project_health  # noqa: E402


class ProjectHealthNotFound(LookupError):
    pass


def resolve_project_health(
    project_id: str, owner_id: str, *, server_token: str = "",
) -> dict:
    """Return current health without crossing owner or Server authority boundaries."""
    if db.project_access_role(project_id, owner_id) is None:
        raise ProjectHealthNotFound(project_id)
    project = db.get_project(project_id)
    server_origin = bool(project and getattr(project, "origin", "local") == "server")
    if server_origin and server_client.server_enabled():
        token = server_token or db.get_server_identity(owner_id) or ""
        remote = server_client.get_project_health(token, project_id)
        if remote is not None:
            db.save_project_health_cache(project_id, remote)
            return remote
    if server_origin:
        cached = db.get_project_health_cache(project_id)
        if cached is not None:
            return {**cached, "source": "server-cache", "stale": True}
    return build_project_health(
        db.list_work_items(project_id),
        db.list_milestones(project_id),
        db.list_project_governance(project_id),
        source="server-cache" if server_origin else "local",
        stale=server_origin,
    )
