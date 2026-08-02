"""Server-authoritative, explainable project health summary (WB-351)."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

import db
from auth import CurrentAccount
from models import Account

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from shared.project_health import build_health_portfolio, build_project_health  # noqa: E402

router = APIRouter(prefix="/api", tags=["project_health"])


@router.get("/project-health")
def project_health_portfolio(account: Account = CurrentAccount) -> dict:
    items = []
    for project, role in db.list_projects_for(account.id):
        health = build_project_health(
            db.list_work_items(project.id),
            db.list_milestones(project.id),
            db.list_project_governance(project.id),
            source="server",
        )
        items.append({
            "project": {
                "id": project.id,
                "name": project.name,
                "origin": "server",
                "role": role.value,
                "updated_at": project.updated_at,
            },
            "health": health,
        })
    return build_health_portfolio(items, source="server")


@router.get("/projects/{project_id}/health")
def project_health(project_id: str, account: Account = CurrentAccount) -> dict:
    if db.project_access_role(project_id, account.id) is None:
        raise HTTPException(404, "project not found")
    return build_project_health(
        db.list_work_items(project_id),
        db.list_milestones(project_id),
        db.list_project_governance(project_id),
        source="server",
    )
