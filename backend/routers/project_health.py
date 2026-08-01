"""Local project health and explicit stale fallback for Server mirrors (WB-351)."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException

import server_client
from auth.deps import current_user
from storage import db

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from shared.project_health import build_project_health  # noqa: E402

router = APIRouter(prefix="/api", tags=["project_health"])


def _bearer(authorization: str) -> str:
    return authorization[7:].strip() if authorization[:7].lower() == "bearer " else ""


@router.get("/project-health")
def project_health(project: str, authorization: str = Header(default="")) -> dict:
    user = current_user()
    if db.project_access_role(project, user.id) is None:
        raise HTTPException(404, "project not found")
    project_row = db.get_project(project)
    server_origin = bool(project_row and getattr(project_row, "origin", "local") == "server")
    if server_origin and server_client.server_enabled():
        remote = server_client.get_project_health(_bearer(authorization), project)
        if remote is not None:
            db.save_project_health_cache(project, remote)
            return remote
    if server_origin:
        cached = db.get_project_health_cache(project)
        if cached is not None:
            return {**cached, "source": "server-cache", "stale": True}
    return build_project_health(
        db.list_work_items(project),
        db.list_milestones(project),
        db.list_project_governance(project),
        source="server-cache" if server_origin else "local",
        stale=server_origin,
    )
