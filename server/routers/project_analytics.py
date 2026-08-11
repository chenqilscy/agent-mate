"""Project-scoped execution analytics API (WB-503)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import db
from auth import CurrentAccount
from models import Account
from project_execution_analytics import build_project_execution_analytics


router = APIRouter(prefix="/api", tags=["project-analytics"])


@router.get("/projects/{project_id}/execution-analytics")
def execution_analytics(
    project_id: str,
    days: int = Query(default=7),
    timezone: str = Query(default="UTC", min_length=1, max_length=80),
    account: Account = CurrentAccount,
) -> dict:
    if db.project_access_role(project_id, account.id) is None:
        raise HTTPException(404, "project not found")
    try:
        return build_project_execution_analytics(project_id, days=days, timezone_name=timezone)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
