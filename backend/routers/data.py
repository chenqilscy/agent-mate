"""数据管理（WB-149）：导出用户数据 + 清空个人对话。全部只读/删自己的数据，按 owner 隔离。"""
from __future__ import annotations

from fastapi import APIRouter

from agent.personalization import get_personalization
from auth.deps import current_user
from storage import db

router = APIRouter(prefix="/api/data", tags=["data"])


@router.get("/summary")
def summary() -> dict:
    owner = current_user().id
    sessions = db.list_sessions(owner)
    messages = sum(len(db.list_messages(s.id)) for s in sessions)
    return {
        "sessions": len(sessions),
        "messages": messages,
        "memories": db.count_memories(owner),
    }


@router.get("/export")
def export() -> dict:
    """dump 本人全部数据：账号 + 个性化设置 + 记忆 + 会话（含消息）。前端下载为 JSON。"""
    u = current_user()
    owner = u.id
    sessions = []
    for s in db.list_sessions(owner):
        sessions.append({
            **s.to_dict(),
            "messages": [m.to_dict() for m in db.list_messages(s.id)],
        })
    return {
        "user": {"id": u.id, "name": u.name},
        "settings": get_personalization(owner),
        "memories": db.list_memories(owner),
        "sessions": sessions,
    }


@router.post("/clear-conversations")
def clear_conversations() -> dict:
    """真删本人的个人对话（kind='chat'）。不可恢复。"""
    return {"ok": True, "removed": db.clear_conversations(current_user().id)}
