"""分层记忆（WB-324）：owner 认知记忆 + 本地项目工作空间 MEMORY.md / 每日日志。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agent import memory, mem_embed, workspace_memory
from auth.deps import current_user
from storage import db
from storage.models import Role

router = APIRouter(prefix="/api/memory", tags=["memory"])


class AddBody(BaseModel):
    content: str = Field(max_length=300)
    project_id: str | None = None


class EditBody(BaseModel):
    content: str = Field(max_length=300)


class EnabledBody(BaseModel):
    enabled: bool


class SearchBody(BaseModel):
    query: str = Field(max_length=300)
    top_k: int = Field(default=8, ge=1, le=50)
    project_id: str | None = None


class ImportanceBody(BaseModel):
    importance: float = Field(ge=0.0, le=1.0)


class EmbedBackendBody(BaseModel):
    backend: str  # 'local' | 'glm'


class WorkspaceMemoryBody(BaseModel):
    project_id: str
    content: str = Field(max_length=workspace_memory.CURATED_MAX_CHARS)


_VALID_STATUS = {"active", "archived", "superseded"}


def _scope(project_id: str | None) -> tuple[str, str | None]:
    return ("project", project_id) if project_id else ("user", None)


def _require_project(project_id: str, *, write: bool = False) -> Role:
    role = db.project_access_role(project_id, current_user().id)
    if role is None:
        raise HTTPException(status_code=404, detail="项目不存在或无权访问")
    if write and role == Role.VIEWER:
        raise HTTPException(status_code=403, detail="Viewer 只能查看项目记忆")
    return role


def _require_memory(owner_id: str, mem_id: str, *, write: bool = False) -> dict:
    row = db.get_memory(owner_id, mem_id)
    if row is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    project_id = row.get("project_id") if row.get("scope") == "project" else None
    if project_id:
        _require_project(project_id, write=write)
    return row


def _payload(owner_id: str, status: str = "active", project_id: str | None = None) -> dict:
    scope, project_id = _scope(project_id)
    return {
        "enabled": memory.capture_enabled(owner_id),
        "items": memory.list_with_strength(
            owner_id, status=status, scope=scope, project_id=project_id,
        ),
        "stats": memory.memory_stats(owner_id, scope=scope, project_id=project_id),
    }


@router.get("")
def get_memory(status: str = "active", project_id: str | None = None) -> dict:
    if status not in _VALID_STATUS:
        status = "active"
    if project_id:
        _require_project(project_id)
    return _payload(current_user().id, status, project_id)


@router.get("/stats")
def stats(project_id: str | None = None) -> dict:
    if project_id:
        _require_project(project_id)
    scope, project_id = _scope(project_id)
    return memory.memory_stats(current_user().id, scope=scope, project_id=project_id)


@router.post("/search")
def search(body: SearchBody) -> dict:
    if body.project_id:
        _require_project(body.project_id)
    scope, project_id = _scope(body.project_id)
    return memory.search_memories(
        current_user().id, body.query, body.top_k, scope=scope, project_id=project_id,
    )


@router.get("/decaying")
def decaying(threshold: float = 0.1, project_id: str | None = None) -> dict:
    """衰退预览：现算强度低于阈值的 active 记忆（按强度升序，最濒危在前）。"""
    if project_id:
        _require_project(project_id)
    scope, project_id = _scope(project_id)
    items = [
        m for m in memory.list_with_strength(
            current_user().id, scope=scope, project_id=project_id,
        )
        if m["strength"] < threshold
    ]
    items.sort(key=lambda m: m["strength"])
    return {"threshold": threshold, "items": items}


@router.post("")
def add(body: AddBody) -> dict:
    owner = current_user().id
    if body.project_id:
        _require_project(body.project_id, write=True)
    scope, project_id = _scope(body.project_id)
    row = memory.store_memory(
        owner, body.content, source="manual", scope=scope, project_id=project_id,
    )
    if row is None:
        raise HTTPException(status_code=400, detail="内容为空或与已有记忆重复")
    return row


@router.post("/clear")
def clear(project_id: str | None = None) -> dict:
    if project_id:
        _require_project(project_id, write=True)
    scope, project_id = _scope(project_id)
    return {
        "ok": True,
        "removed": db.clear_memories(
            current_user().id, scope=scope, project_id=project_id,
        ),
    }


@router.put("/enabled")
def set_enabled(body: EnabledBody) -> dict:
    owner = current_user().id
    memory.set_capture_enabled(owner, body.enabled)
    return {"enabled": memory.capture_enabled(owner)}


@router.put("/embed-backend")
def set_embed_backend(body: EmbedBackendBody) -> dict:
    """选记忆嵌入后端（WB-170）：'local'（本地 fastembed）| 'glm'（在线 GLM embedding-3）。
    返回各后端可用性；切换后旧向量下次注入/检索时惰性重嵌入迁移。"""
    if body.backend not in ("local", "glm"):
        raise HTTPException(status_code=400, detail="backend 必须是 local 或 glm")
    owner = current_user().id
    mem_embed.set_backend(owner, body.backend)
    return mem_embed.backends_status(owner)


@router.get("/workspace")
def get_workspace_memory(project_id: str) -> dict:
    role = _require_project(project_id)
    return {
        "project_id": project_id,
        "content": workspace_memory.read_curated(project_id),
        "daily_logs": workspace_memory.list_daily_logs(project_id),
        "can_edit": role != Role.VIEWER,
        "local_only": True,
    }


@router.put("/workspace")
def put_workspace_memory(body: WorkspaceMemoryBody) -> dict:
    _require_project(body.project_id, write=True)
    try:
        content = workspace_memory.write_curated(body.project_id, body.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "project_id": body.project_id,
        "content": content,
        "daily_logs": workspace_memory.list_daily_logs(body.project_id),
        "can_edit": True,
        "local_only": True,
    }


@router.get("/{mem_id}")
def detail(mem_id: str) -> dict:
    """单条详情 + 溯源链（谁取代了它 / 它取代了谁）。"""
    owner = current_user().id
    mem = _require_memory(owner, mem_id)
    mem["strength"] = memory.strength_of(mem)
    superseded_by = db.get_memory(owner, mem["superseded_by"]) if mem.get("superseded_by") else None
    superseded = db.find_superseded_by(owner, mem_id)
    return {"memory": mem, "superseded_by": superseded_by, "superseded": superseded}


@router.put("/{mem_id}")
def edit(mem_id: str, body: EditBody) -> dict:
    """原地编辑一条记忆（WB-162）。内容为空 / 记忆不存在 / 与已有记忆重复 → 400。"""
    owner = current_user().id
    _require_memory(owner, mem_id, write=True)
    row = db.update_memory(owner, mem_id, body.content)
    if row is None:
        raise HTTPException(status_code=400, detail="内容为空、记忆不存在或与已有记忆重复")
    return row


@router.patch("/{mem_id}/importance")
def set_importance(mem_id: str, body: ImportanceBody) -> dict:
    owner = current_user().id
    _require_memory(owner, mem_id, write=True)
    row = db.set_memory_importance(owner, mem_id, body.importance)
    if row is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    row["strength"] = memory.strength_of(row)
    return row


@router.post("/{mem_id}/archive")
def archive(mem_id: str) -> dict:
    owner = current_user().id
    _require_memory(owner, mem_id, write=True)
    return db.set_memory_status(owner, mem_id, "archived")


@router.post("/{mem_id}/rollback")
def rollback(mem_id: str) -> dict:
    """归档/被更替 → 恢复 active（清 superseded_by 链）。"""
    owner = current_user().id
    _require_memory(owner, mem_id, write=True)
    return db.set_memory_status(owner, mem_id, "active")


@router.delete("/{mem_id}")
def remove(mem_id: str) -> dict:
    owner = current_user().id
    _require_memory(owner, mem_id, write=True)
    ok = db.delete_memory(owner, mem_id)
    if not ok:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"ok": True}
