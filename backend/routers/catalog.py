"""Catalog — 橱窗目录（WB-060/WB-321）。

目录内容是全用户可见的 builtin 数据；灵感收藏按 owner 存本地 SQLite。前端 catalogStore
消费目录、保留静态兜底。功能定义（专家人格 / 连接器 spec，WB-059）在各自路由，不在此。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from auth.deps import current_user
from storage import db

router = APIRouter(prefix="/api", tags=["catalog"])
_INSPIRATION_FAVORITES_KEY = "catalog.inspiration_favorites"


@router.get("/catalog")
def get_catalog() -> dict:
    """所有橱窗目录，按 export 名分组（EXP_GRID / EXP_TEAMS / CONNS / CONN_META / AUTO / INSP / …）。"""
    return db.showcase_all()


def _inspiration_ids() -> set[str]:
    rows = db.showcase_all().get("INSP_TEMPLATES", [])
    if not isinstance(rows, list):
        return set()
    return {
        str(row["id"])
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"]
    }


def _inspiration_favorites(owner_id: str) -> set[str]:
    raw = db.get_user_setting(owner_id, _INSPIRATION_FAVORITES_KEY)
    try:
        values = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        values = []
    if not isinstance(values, list):
        return set()
    valid = _inspiration_ids()
    return {str(value) for value in values if str(value) in valid}


class InspirationFavoriteBody(BaseModel):
    favorite: bool


@router.get("/catalog/inspiration-favorites")
def get_inspiration_favorites() -> dict:
    return {"ids": sorted(_inspiration_favorites(current_user().id))}


@router.put("/catalog/inspiration-favorites/{template_id}")
def put_inspiration_favorite(template_id: str, body: InspirationFavoriteBody) -> dict:
    valid = _inspiration_ids()
    if template_id not in valid:
        raise HTTPException(status_code=404, detail="inspiration template not found")
    owner_id = current_user().id
    favorites = _inspiration_favorites(owner_id)
    if body.favorite:
        favorites.add(template_id)
    else:
        favorites.discard(template_id)
    db.set_user_setting(
        owner_id,
        _INSPIRATION_FAVORITES_KEY,
        json.dumps(sorted(favorites), ensure_ascii=False) if favorites else None,
    )
    return {"ids": sorted(favorites)}
