"""Owner-scoped execution monitoring and operational statistics (WB-286)."""
from __future__ import annotations

from fastapi import APIRouter, Query

from auth.deps import current_user
from channels import manager
from storage import db

router = APIRouter(prefix="/api", tags=["operations"])


@router.get("/ops/summary")
def ops_summary(days: int = Query(default=7, ge=1, le=90)) -> dict:
    user = current_user()
    summary = db.get_ops_summary(user.id, days=days)
    channels = [
        manager.channel_public(channel)
        for assistant in db.list_assistants(user.id)
        for channel in db.list_channels(assistant["id"])
    ]
    enabled_channels = [channel for channel in channels if channel["enabled"]]
    summary["assistants"].update({
        "channels": len(channels),
        "channels_running": sum(1 for channel in enabled_channels if channel["running"]),
        "channels_attention": sum(1 for channel in enabled_channels if not channel["running"]),
    })
    return summary
