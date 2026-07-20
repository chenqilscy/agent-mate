"""目录（WB-061 预埋 + WB-066 运营 Admin）。

`GET` 全账号可读（builtin 下发源）；写端点（POST/PATCH/DELETE）**仅平台管理员**（首个注册账号自举），
用于运营内置目录——增/改/删/排序一条 → 客户端 pull 后反映（本地 override 叠加、离线 builtin 兜底）。
org 级目录运营（团队 Admin）留后续。
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import db
import skillhub_client
import skillhub_sync
from auth import CurrentAccount
from models import Account

router = APIRouter(prefix="/api", tags=["catalog"])
_SKILL_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _require_admin(account: Account) -> None:
    if not account.is_platform_admin:
        raise HTTPException(403, "platform admin only")


# ── SkillHub 目录镜像 + 查询代理（WB-069）──────────────────────────────────
# 定时镜像的浏览目录仍走上面的 GET /api/catalog（category='skill' + 'skill-category' 骨架）。
# 这里加：管理员手动触发同步；实时查询统一经 Server 代理（跑 CLI search）。


@router.post("/catalog/skills/sync")
def sync_skillhub(account: Account = CurrentAccount) -> dict:
    """手动触发一次 SkillHub 目录镜像同步（平台管理员）。返回条数/分类分布统计。"""
    _require_admin(account)
    return skillhub_sync.sync_once()


@router.get("/catalog/skills/search")
def search_skillhub(q: str = "", limit: int = 12, account: Account = CurrentAccount) -> dict:
    """Server 统一查询代理：实时查 SkillHub（CLI search + 短缓存）。

    CLI 不可用/失败 → 空结果 + cli=false，客户端据此回退本地 backend 直连（离线兜底）。
    """
    return {"query": q, "results": skillhub_client.search(q, limit),
            "cli": skillhub_client.cli_available()}


@router.get("/catalog/skills/rankings")
def rankings_skillhub(type: str = "featured", limit: int = 0, account: Account = CurrentAccount) -> dict:
    """实时榜单代理（WB-186）：补齐 Console 侧的 rankings —— App 原先绕过 Console 直连
    skillhub.cn（本地 CLI），与 search/preview 的 WB-130 口径矛盾。

    Console 走 HTTP showcase（无需 CLI），故没装 CLI 的 App 也能拿到真实榜单。
    `skills=[]` = 取不到，客户端据此回退本地 CLI 直连（离线兜底）。
    """
    return {"type": type, "skills": skillhub_client.rankings(type, limit)}


@router.get("/catalog/skills/{slug}/preview")
def preview_skillhub(slug: str, name: str = "", account: Account = CurrentAccount) -> dict:
    """单技能预览代理（WB-130）：Console 统一对 SkillHub 取数（HTTP 富元数据 + CLI SKILL.md 正文）。

    App 不再直连 SkillHub，改调本端点。`skill=None` = 元数据与正文都取不到，客户端回退本地直连。
    """
    return {"skill": skillhub_client.preview(slug, name), "cli": skillhub_client.cli_available()}


@router.get("/catalog")
def list_all_catalog(all: bool = False, account: Account = CurrentAccount) -> dict:
    """所有 builtin 目录项（跨 category），供客户端一次性下行覆盖本地。
    `?all=true`（仅平台管理员）连停用项一并返回，供门户高级 JSON 视图。"""
    inc = all and account.is_platform_admin
    return {"items": db.list_all_catalog_items(scope="builtin", include_disabled=inc)}


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


def _validate_app_skill(data: Any, *, ignore_id: str = "") -> None:
    if not isinstance(data, dict):
        raise HTTPException(400, "APP_SKILLS data must be an object")
    slug = str(data.get("slug", "")).strip()
    name = str(data.get("name", "")).strip()
    if not _SKILL_SLUG_RE.fullmatch(slug):
        raise HTTPException(400, "invalid skill slug")
    if not name:
        raise HTTPException(400, "skill name is required")
    for row in db.list_catalog_items("APP_SKILLS", scope="builtin", include_disabled=True):
        if row["id"] != ignore_id and isinstance(row.get("data"), dict) and row["data"].get("slug") == slug:
            raise HTTPException(409, "skill slug already exists")


@router.post("/catalog")
def create_item(body: CatalogItemBody, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    if body.category == "APP_SKILLS":
        _validate_app_skill(body.data)
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
    if not db.update_catalog_item(item_id, data=body.data, sort=body.sort, enabled=body.enabled):
        raise HTTPException(404, "catalog item not found")
    return {"ok": True}


@router.delete("/catalog/item/{item_id}")
def delete_item(item_id: str, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    if not db.delete_catalog_item(item_id):
        raise HTTPException(404, "catalog item not found")
    return {"ok": True}
