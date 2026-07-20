"""目录（WB-061 预埋 + WB-066 运营 Admin）。

`GET` 全账号可读（builtin 下发源）；写端点（POST/PATCH/DELETE）**仅平台管理员**（首个注册账号自举），
用于运营内置目录——增/改/删/排序一条 → 客户端 pull 后反映（本地 override 叠加、离线 builtin 兜底）。
org 级目录运营（团队 Admin）留后续。
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import db
from auth import CurrentAccount
from models import Account

router = APIRouter(prefix="/api", tags=["catalog"])
_SKILL_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_PLACEMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _require_admin(account: Account) -> None:
    if not account.is_platform_admin:
        raise HTTPException(403, "platform admin only")


@router.get("/catalog")
def list_all_catalog(all: bool = False, account: Account = CurrentAccount) -> dict:
    """所有 builtin 目录项（跨 category），供客户端一次性下行覆盖本地。
    `?all=true`（仅平台管理员）连停用项一并返回，供门户高级 JSON 视图。"""
    inc = all and account.is_platform_admin
    items = db.list_all_catalog_items(scope="builtin", include_disabled=inc)
    if not inc:
        # 推荐位需要把“已配置但全部停用”与“从未配置”区分开：前者应诚实显示空，
        # 后者才允许 App local-first 回退。因此下行携带推荐位 enabled 状态。
        items.extend(
            row for row in _skill_recommendations()
            if not any(current["id"] == row["id"] for current in items)
        )
        items.sort(key=lambda row: (row["category"], row["sort"]))
    return {"items": items}


@router.get("/catalog/{category}")
def list_catalog(category: str, all: bool = False, account: Account = CurrentAccount) -> dict:
    """某 category 目录项。`?all=true`（仅平台管理员）含停用项 + `enabled` 标志，供门户 CRUD 列表。"""
    inc = all and account.is_platform_admin
    return {"category": category, "items": db.list_catalog_items(category, scope="builtin", include_disabled=inc)}


class CatalogItemBody(BaseModel):
    category: str
    kind: str = ""
    data: Any = None  # 目录卡：数组(如 EXP_GRID 元组) 或对象(如 CONN_META)
    sort: int = 0


_MAX_SKILL_FILES = 128
_MAX_SKILL_FILES_BYTES = 1024 * 1024
_RESERVED_SKILL_FILES = {"skill.md", "_skillhub_meta.json", "_meta.json", ".disabled"}


def _validate_app_skill(data: Any, *, ignore_id: str = "") -> None:
    if not isinstance(data, dict):
        raise HTTPException(400, "APP_SKILLS data must be an object")
    slug = str(data.get("slug", "")).strip()
    name = str(data.get("name", "")).strip()
    if not _SKILL_SLUG_RE.fullmatch(slug):
        raise HTTPException(400, "invalid skill slug")
    if not name:
        raise HTTPException(400, "skill name is required")
    files = data.get("files", [])
    if not isinstance(files, list):
        raise HTTPException(400, "skill files must be a list")
    if len(files) > _MAX_SKILL_FILES:
        raise HTTPException(413, f"skill files exceed {_MAX_SKILL_FILES} entries")
    seen: set[str] = set()
    total = 0
    for entry in files:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not isinstance(entry.get("content"), str):
            raise HTTPException(400, "each skill file requires string path and content")
        raw_path = entry["path"].replace("\\", "/").strip()
        path = PurePosixPath(raw_path)
        if (
            not raw_path or len(raw_path) > 240 or path.is_absolute()
            or any(part in {"", ".", ".."} or ":" in part or "\x00" in part for part in path.parts)
        ):
            raise HTTPException(400, "invalid skill file path")
        canonical = path.as_posix().casefold()
        if path.name.casefold() in _RESERVED_SKILL_FILES:
            raise HTTPException(400, f"reserved skill file: {path.name}")
        if canonical in seen:
            raise HTTPException(409, "duplicate skill file path")
        seen.add(canonical)
        total += len(entry["content"].encode("utf-8"))
        if total > _MAX_SKILL_FILES_BYTES:
            raise HTTPException(413, "skill files exceed 1MB")
    for row in db.list_catalog_items("APP_SKILLS", scope="builtin", include_disabled=True):
        if row["id"] != ignore_id and isinstance(row.get("data"), dict) and row["data"].get("slug") == slug:
            raise HTTPException(409, "skill slug already exists")


def _skill_recommendations() -> list[dict]:
    return db.list_catalog_items(
        "SKILL_RECOMMENDATIONS", scope="builtin", include_disabled=True,
    )


def _validate_skill_recommendation(data: Any, *, ignore_id: str = "") -> None:
    """推荐位只保存引用和运营元数据；安装包、Key 与文件内容仍留在 App 本机。"""
    if not isinstance(data, dict):
        raise HTTPException(400, "SKILL_RECOMMENDATIONS data must be an object")
    provider = str(data.get("provider", "")).strip().lower()
    slug = str(data.get("skill_slug", "")).strip()
    placement = str(data.get("placement", "skills.recommended")).strip()
    if provider not in {"agentmate", "skillhub"}:
        raise HTTPException(400, "provider must be agentmate or skillhub")
    if not _SKILL_SLUG_RE.fullmatch(slug):
        raise HTTPException(400, "invalid recommendation skill slug")
    if not _PLACEMENT_RE.fullmatch(placement):
        raise HTTPException(400, "invalid recommendation placement")
    if provider == "agentmate":
        exists = any(
            isinstance(row.get("data"), dict) and row["data"].get("slug") == slug
            for row in db.list_catalog_items("APP_SKILLS", scope="builtin", include_disabled=True)
        )
        if not exists:
            raise HTTPException(400, "referenced AgentMate skill does not exist")
    elif not str(data.get("title", "")).strip() or not str(data.get("description", "")).strip():
        raise HTTPException(400, "SkillHub recommendation title and description are required")
    try:
        starts_at = float(data.get("starts_at") or 0)
        ends_at = float(data.get("ends_at") or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "invalid recommendation schedule") from exc
    if starts_at < 0 or ends_at < 0 or (starts_at and ends_at and ends_at <= starts_at):
        raise HTTPException(400, "recommendation end time must be later than start time")
    for row in _skill_recommendations():
        current = row.get("data") if isinstance(row.get("data"), dict) else {}
        if row["id"] != ignore_id and (
            str(current.get("provider", "")).lower(), current.get("skill_slug"),
            current.get("placement", "skills.recommended"),
        ) == (provider, slug, placement):
            raise HTTPException(409, "skill recommendation already exists in this placement")


def _skill_is_recommended(slug: str) -> bool:
    return any(
        isinstance(row.get("data"), dict)
        and str(row["data"].get("provider", "")).lower() == "agentmate"
        and row["data"].get("skill_slug") == slug
        for row in _skill_recommendations()
    )


@router.post("/catalog")
def create_item(body: CatalogItemBody, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    if body.category == "APP_SKILLS":
        _validate_app_skill(body.data)
    elif body.category == "SKILL_RECOMMENDATIONS":
        _validate_skill_recommendation(body.data)
    iid = db.create_catalog_item(
        category=body.category, data=body.data, scope="builtin", kind=body.kind, sort=body.sort,
    )
    return {"id": iid}


class UpdateItemBody(BaseModel):
    data: Any = None
    sort: int | None = None
    enabled: bool | None = None


@router.patch("/catalog/item/{item_id}")
def update_item(item_id: str, body: UpdateItemBody, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    item = db.get_catalog_item(item_id)
    if not item:
        raise HTTPException(404, "catalog item not found")
    if item["category"] == "APP_SKILLS" and body.data is not None:
        _validate_app_skill(body.data, ignore_id=item_id)
        old_slug = str(item.get("data", {}).get("slug", "")) if isinstance(item.get("data"), dict) else ""
        new_slug = str(body.data.get("slug", "")) if isinstance(body.data, dict) else ""
        if old_slug and old_slug != new_slug and _skill_is_recommended(old_slug):
            raise HTTPException(409, "skill is referenced by a recommendation")
    elif item["category"] == "SKILL_RECOMMENDATIONS" and body.data is not None:
        _validate_skill_recommendation(body.data, ignore_id=item_id)
    if not db.update_catalog_item(item_id, data=body.data, sort=body.sort, enabled=body.enabled):
        raise HTTPException(404, "catalog item not found")
    return {"ok": True}


@router.delete("/catalog/item/{item_id}")
def delete_item(item_id: str, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    item = db.get_catalog_item(item_id)
    if not item:
        raise HTTPException(404, "catalog item not found")
    if item["category"] == "APP_SKILLS" and isinstance(item.get("data"), dict):
        slug = str(item["data"].get("slug", ""))
        if slug and _skill_is_recommended(slug):
            raise HTTPException(409, "skill is referenced by a recommendation")
    if not db.delete_catalog_item(item_id):
        raise HTTPException(404, "catalog item not found")
    return {"ok": True}
