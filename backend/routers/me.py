"""Current user & role (drives authStore; M1 returns the local user stub)."""
from __future__ import annotations

from fastapi import APIRouter

from auth.deps import current_user
from config import settings

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me")
def get_me() -> dict:
    user = current_user()
    return {
        "id": user.id,
        "name": user.name,
        "role": user.role.value,
        "plan": user.plan,
        "llm_configured": settings.llm_configured,
        "model": settings.LLM_MODEL,
    }
