"""自定义专家（我的专家 · WB-049）—— owner 维度持久化。

召唤自造专家时，其 persona 在 agent/runtime.py 里注入系统提示、优先于内置 EXPERTS，
所以创建的专家是「真生效」的，不是展示壳。所有路由按 current_user 过滤。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth.deps import current_user
from storage import db

router = APIRouter(prefix="/api", tags=["experts"])


class CreateExpertBody(BaseModel):
    name: str
    subtitle: str = ""
    avatar: str = "🧑"
    intro: str = ""
    persona: str = ""
    tags: list[str] = []


@router.get("/experts")
def list_experts() -> dict:
    user = current_user()
    return {"experts": [e.to_dict() for e in db.list_experts(user.id)]}


@router.post("/experts")
def create_expert(body: CreateExpertBody) -> dict:
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(400, "empty expert name")
    # persona 决定「专家是否真有专长」：留空则用 intro 兜底，仍空则退化为通用人格。
    persona = (body.persona or "").strip() or (body.intro or "").strip()
    user = current_user()
    e = db.create_expert(
        owner_id=user.id,
        name=name,
        subtitle=(body.subtitle or "").strip(),
        avatar=(body.avatar or "🧑").strip() or "🧑",
        intro=(body.intro or "").strip(),
        persona=persona,
        tags=[t.strip() for t in (body.tags or []) if t.strip()],
    )
    return e.to_dict()


@router.delete("/experts/{expert_id}")
def delete_expert(expert_id: str) -> dict:
    user = current_user()
    if not db.delete_expert(expert_id, user.id):
        raise HTTPException(404, "expert not found")
    return {"ok": True}
