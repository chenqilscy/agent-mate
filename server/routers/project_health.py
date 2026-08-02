"""Server-authoritative, explainable project health summary (WB-351)."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

import db
from auth import CurrentAccount
from models import Account
from project_health_service import calculate_project_health, scan_accessible_projects

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from shared.project_health import build_health_portfolio  # noqa: E402

router = APIRouter(prefix="/api", tags=["project_health"])


@router.get("/project-health")
def project_health_portfolio(account: Account = CurrentAccount) -> dict:
    items = []
    for project, role in db.list_projects_for(account.id):
        health = calculate_project_health(project.id)
        events = db.list_project_health_events(project.id, 1)
        items.append({
            "project": {
                "id": project.id,
                "name": project.name,
                "origin": "server",
                "role": role.value,
                "updated_at": project.updated_at,
            },
            "health": health,
            "last_transition": events[0] if events else None,
        })
    return build_health_portfolio(items, source="server")


@router.get("/projects/{project_id}/health")
def project_health(project_id: str, account: Account = CurrentAccount) -> dict:
    if db.project_access_role(project_id, account.id) is None:
        raise HTTPException(404, "project not found")
    return calculate_project_health(project_id)


@router.post("/project-health/scan")
def scan_project_health(account: Account = CurrentAccount) -> dict:
    return scan_accessible_projects(account.id)


@router.get("/projects/{project_id}/health-events")
def project_health_events(project_id: str, account: Account = CurrentAccount) -> dict:
    if db.project_access_role(project_id, account.id) is None:
        raise HTTPException(404, "project not found")
    return {"events": db.list_project_health_events(project_id), "source": "server", "stale": False}
