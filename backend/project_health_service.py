"""Owner-scoped project health resolution shared by HTTP and automations (WB-352)."""
from __future__ import annotations

import sys
from pathlib import Path

import server_client
from storage import db

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from shared.project_health import build_health_portfolio, build_project_health  # noqa: E402


class ProjectHealthNotFound(LookupError):
    pass


def _local_or_cached_health(project_id: str, *, server_origin: bool) -> dict:
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
        return _local_or_cached_health(project_id, server_origin=True)
    return _local_or_cached_health(project_id, server_origin=False)


def resolve_project_health_portfolio(owner_id: str, *, server_token: str = "") -> dict:
    """Resolve all accessible projects with one Server request and offline-safe mirrors."""
    projects = db.list_projects_for(owner_id)
    server_ids = {project.id for project, _role in projects if project.origin == "server"}
    remote_by_id: dict[str, dict] = {}
    if server_ids and server_client.server_enabled():
        token = server_token or db.get_server_identity(owner_id) or ""
        remote = server_client.get_project_health_portfolio(token)
        if remote is not None:
            for item in remote.get("items", []):
                project_data = item.get("project") if isinstance(item, dict) else None
                health = item.get("health") if isinstance(item, dict) else None
                project_id = project_data.get("id") if isinstance(project_data, dict) else None
                if project_id in server_ids and isinstance(health, dict):
                    remote_by_id[project_id] = health
                    db.save_project_health_cache(project_id, health)

    items = []
    sources: set[str] = set()
    for project, role in projects:
        if project.origin == "server" and project.id in remote_by_id:
            health = remote_by_id[project.id]
        else:
            health = _local_or_cached_health(project.id, server_origin=project.origin == "server")
        sources.add(str(health.get("source") or project.origin))
        items.append({
            "project": {
                "id": project.id,
                "name": project.name,
                "origin": project.origin,
                "role": role.value,
                "updated_at": project.updated_at,
            },
            "health": health,
        })
    source = next(iter(sources)) if len(sources) == 1 else "mixed"
    return build_health_portfolio(items, source=source if sources else "local")
