"""用户记忆（WB-148）：列表 / 手动增删清 / 自动抽取开关，按 owner 存 DB。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent import memory
from auth.deps import current_user
from storage import db

router = APIRouter(prefix="/api/memory", tags=["memory"])


class AddBody(BaseModel):
    content: str = Field(max_length=300)


class EnabledBody(BaseModel):
    enabled: bool


def _payload(owner_id: str) -> dict:
    return {
        "enabled": memory.capture_enabled(owner_id),
        "items": db.list_memories(owner_id),
    }


@router.get("")
def get_memory() -> dict:
    return _payload(current_user().id)


@router.post("")
def add(body: AddBody) -> dict:
    owner = current_user().id
    row = db.add_memory(owner, body.content, source="manual")
    if row is None:
        raise HTTPException(status_code=400, detail="内容为空或与已有记忆重复")
    return row


@router.delete("/{mem_id}")
def remove(mem_id: str) -> dict:
    owner = current_user().id
    ok = db.delete_memory(owner, mem_id)
    if not ok:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"ok": True}


@router.post("/clear")
def clear() -> dict:
    return {"ok": True, "removed": db.clear_memories(current_user().id)}


@router.put("/enabled")
def set_enabled(body: EnabledBody) -> dict:
    owner = current_user().id
    memory.set_capture_enabled(owner, body.enabled)
    return {"enabled": memory.capture_enabled(owner)}
