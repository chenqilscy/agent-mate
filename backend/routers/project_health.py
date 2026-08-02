"""Local project health and explicit stale fallback for Server mirrors (WB-351)."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from project_health_service import (
    ProjectHealthNotFound,
    resolve_project_health,
    resolve_project_health_portfolio,
)
from auth.deps import current_user

router = APIRouter(prefix="/api", tags=["project_health"])


def _bearer(authorization: object) -> str:
    if not isinstance(authorization, str):
        return ""
    return authorization[7:].strip() if authorization[:7].lower() == "bearer " else ""


@router.get("/project-health")
def project_health(project: str, authorization: str = Header(default="")) -> dict:
    user = current_user()
    try:
        return resolve_project_health(project, user.id, server_token=_bearer(authorization))
    except ProjectHealthNotFound:
        raise HTTPException(404, "project not found") from None


@router.get("/project-health/portfolio")
def project_health_portfolio(authorization: str = Header(default="")) -> dict:
    user = current_user()
    return resolve_project_health_portfolio(user.id, server_token=_bearer(authorization))
