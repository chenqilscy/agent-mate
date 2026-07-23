"""Current Server account or anonymous guest scope (drives authStore)."""
from __future__ import annotations

from fastapi import APIRouter

from auth.deps import current_user
from config import settings
from storage.models import LOCAL_USER_ID

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me")
def get_me() -> dict:
    user = current_user()
    return {
        "id": user.id,
        "name": user.name,
        "authenticated": user.id != LOCAL_USER_ID,
        "role": user.role.value,
        "plan": user.plan,
        "llm_configured": settings.llm_configured,
        "model": settings.LLM_MODEL,
    }
