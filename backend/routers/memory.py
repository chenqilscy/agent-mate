"""用户记忆（WB-148；WB-162 编辑；WB-166/167 认知记忆；WB-168 白盒管理）。按 owner 存 DB。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent import memory
from auth.deps import current_user
from storage import db

router = APIRouter(prefix="/api/memory", tags=["memory"])


class AddBody(BaseModel):
    content: str = Field(max_length=300)


class EditBody(BaseModel):
    content: str = Field(max_length=300)


class EnabledBody(BaseModel):
    enabled: bool


class SearchBody(BaseModel):
    query: str = Field(max_length=300)
    top_k: int = Field(default=8, ge=1, le=50)


class ImportanceBody(BaseModel):
    importance: float = Field(ge=0.0, le=1.0)


_VALID_STATUS = {"active", "archived", "superseded"}


def _payload(owner_id: str, status: str = "active") -> dict:
    return {
        "enabled": memory.capture_enabled(owner_id),
        "items": memory.list_with_strength(owner_id, status=status),
        "stats": memory.memory_stats(owner_id),
    }


@router.get("")
def get_memory(status: str = "active") -> dict:
    if status not in _VALID_STATUS:
        status = "active"
    return _payload(current_user().id, status)


@router.get("/stats")
def stats() -> dict:
    return memory.memory_stats(current_user().id)


@router.post("/search")
def search(body: SearchBody) -> dict:
    return memory.search_memories(current_user().id, body.query, body.top_k)


@router.get("/decaying")
def decaying(threshold: float = 0.1) -> dict:
    """衰退预览：现算强度低于阈值的 active 记忆（按强度升序，最濒危在前）。"""
    items = [m for m in memory.list_with_strength(current_user().id) if m["strength"] < threshold]
    items.sort(key=lambda m: m["strength"])
    return {"threshold": threshold, "items": items}


@router.post("")
def add(body: AddBody) -> dict:
    owner = current_user().id
    row = db.add_memory(owner, body.content, source="manual")
    if row is None:
        raise HTTPException(status_code=400, detail="内容为空或与已有记忆重复")
    return row


@router.post("/clear")
def clear() -> dict:
    return {"ok": True, "removed": db.clear_memories(current_user().id)}


@router.put("/enabled")
def set_enabled(body: EnabledBody) -> dict:
    owner = current_user().id
    memory.set_capture_enabled(owner, body.enabled)
    return {"enabled": memory.capture_enabled(owner)}


@router.get("/{mem_id}")
def detail(mem_id: str) -> dict:
    """单条详情 + 溯源链（谁取代了它 / 它取代了谁）。"""
    owner = current_user().id
    mem = db.get_memory(owner, mem_id)
    if mem is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    mem["strength"] = memory.strength_of(mem)
    superseded_by = db.get_memory(owner, mem["superseded_by"]) if mem.get("superseded_by") else None
    superseded = db.find_superseded_by(owner, mem_id)
    return {"memory": mem, "superseded_by": superseded_by, "superseded": superseded}


@router.put("/{mem_id}")
def edit(mem_id: str, body: EditBody) -> dict:
    """原地编辑一条记忆（WB-162）。内容为空 / 记忆不存在 / 与已有记忆重复 → 400。"""
    owner = current_user().id
    row = db.update_memory(owner, mem_id, body.content)
    if row is None:
        raise HTTPException(status_code=400, detail="内容为空、记忆不存在或与已有记忆重复")
    return row


@router.patch("/{mem_id}/importance")
def set_importance(mem_id: str, body: ImportanceBody) -> dict:
    row = db.set_memory_importance(current_user().id, mem_id, body.importance)
    if row is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    row["strength"] = memory.strength_of(row)
    return row


@router.post("/{mem_id}/archive")
def archive(mem_id: str) -> dict:
    owner = current_user().id
    if db.get_memory(owner, mem_id) is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return db.set_memory_status(owner, mem_id, "archived")


@router.post("/{mem_id}/rollback")
def rollback(mem_id: str) -> dict:
    """归档/被更替 → 恢复 active（清 superseded_by 链）。"""
    owner = current_user().id
    if db.get_memory(owner, mem_id) is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return db.set_memory_status(owner, mem_id, "active")


@router.delete("/{mem_id}")
def remove(mem_id: str) -> dict:
    ok = db.delete_memory(current_user().id, mem_id)
    if not ok:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"ok": True}
