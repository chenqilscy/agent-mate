"""Model menu + custom-model management (WB-124).

Drives the composer model picker. Two kinds of entries:
  - builtin: the prototype menu (multiplier / level / limited-offer). These don't map
    to a real provider locally; users may *hide* the ones they don't use.
  - custom: owner-scoped rows in `custom_models`, each carrying its own provider
    (model_id + api_base + api_key). Selecting one actually routes there at run time
    (agent.runtime.resolve_model_config). The api_key is backend-only and NEVER
    returned to the frontend (铁律#4) — the list exposes only `api_base` + `has_key`.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from auth.deps import current_user
from config import settings
from storage import db

router = APIRouter(prefix="/api", tags=["models"])

# [icon, color, name, level, mult, off]
_BUILTIN = [
    ["A", "#3B4048", "Auto", "High", "", ""],
    ["H", "#1B74E4", "Hy3 preview", "High", "0.04x", "限时折扣"],
    ["Z", "#17181C", "GLM-5.2", "Medium", "0.79x", ""],
    ["Z", "#17181C", "GLM-5.1", "Medium", "0.79x", ""],
    ["M", "#E5484D", "MiniMax-M3", "Medium", "0.25x", ""],
    ["K", "#17181C", "Kimi-K2.7-Code", "Medium", "0.57x", ""],
    ["🐋", "", "Deepseek-V4-Flash", "High", "0.06x", ""],
    ["🐋", "", "Deepseek-V4-Pro", "High", "0.16x", ""],
]


def _pack_builtin(hidden: set[str]) -> list[dict]:
    return [
        {
            "icon": r[0],
            "color": r[1],
            "name": r[2],
            "level": r[3],
            "mult": r[4],
            "off": r[5],
            "group": "builtin",
            "builtin": True,
            "hidden": r[2] in hidden,
        }
        for r in _BUILTIN
    ]


def _pack_custom(row: dict) -> dict:
    """DB custom-model row (already secret-stripped) → frontend ModelOption shape."""
    return {
        "id": row["id"],
        "icon": row.get("icon") or "🧩",
        "color": row.get("color") or "",
        "name": row["name"],
        "level": "",
        "mult": row.get("mult") or "",
        "off": "",
        "group": "custom",
        "model_id": row.get("model_id") or "",
        "api_base": row.get("api_base") or "",
        "has_key": bool(row.get("has_key")),
    }


@router.get("/models")
def list_models(all: bool = False) -> dict:
    """Picker list (default) or full management list (`?all=true` includes hidden
    builtins with a `hidden` flag)."""
    user = current_user()
    hidden = set(db.list_hidden_builtins(user.id))
    builtin = _pack_builtin(hidden)
    if not all:
        builtin = [m for m in builtin if not m["hidden"]]
    custom = [_pack_custom(r) for r in db.list_custom_models(user.id, include_secrets=False)]
    models = builtin + custom
    # Seed first-visit selection to whatever resolves to the .env model (so what's
    # shown = what runs), else the raw id. Only affects the very first pick (WB-005).
    default = next(
        (
            m["name"]
            for m in models
            if m.get("model_id") == settings.LLM_MODEL or m["name"].endswith(":" + settings.LLM_MODEL)
        ),
        settings.LLM_MODEL,
    )
    return {"default": default, "effective": settings.LLM_MODEL, "models": models}


class CustomModelIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    model_id: str = Field(min_length=1, max_length=120)
    api_base: str | None = Field(default=None, max_length=300)
    api_key: str | None = Field(default=None, max_length=400)
    icon: str = Field(default="🧩", max_length=8)
    color: str = Field(default="", max_length=16)
    mult: str = Field(default="", max_length=12)


class CustomModelPatch(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    model_id: str | None = Field(default=None, max_length=120)
    api_base: str | None = Field(default=None, max_length=300)
    # None/omitted = keep existing key; "" = clear it; non-empty = replace.
    api_key: str | None = Field(default=None, max_length=400)
    icon: str | None = Field(default=None, max_length=8)
    color: str | None = Field(default=None, max_length=16)
    mult: str | None = Field(default=None, max_length=12)


@router.post("/models/custom")
def create_custom(body: CustomModelIn) -> dict:
    user = current_user()
    if db.get_custom_model_by_name(user.id, body.name.strip()):
        raise HTTPException(409, "已有同名自定义模型")
    row = db.create_custom_model(
        user.id,
        name=body.name.strip(),
        model_id=body.model_id.strip(),
        api_base=(body.api_base or "").strip() or None,
        api_key=(body.api_key or "").strip() or None,
        icon=body.icon,
        color=body.color,
        mult=body.mult,
    )
    return _pack_custom(row)


@router.patch("/models/custom/{model_id}")
def update_custom(model_id: str, body: CustomModelPatch) -> dict:
    user = current_user()
    # Guard the unique-name constraint before writing (clearer than a 500 on IntegrityError).
    if body.name is not None:
        clash = db.get_custom_model_by_name(user.id, body.name.strip())
        if clash and clash["id"] != model_id:
            raise HTTPException(409, "已有同名自定义模型")
    fields: dict = {}
    for k in ("name", "model_id", "api_base", "icon", "color", "mult"):
        v = getattr(body, k)
        if v is not None:
            fields[k] = v.strip() if k in ("name", "model_id", "api_base") else v
    # api_base "" → None (clear); api_key passthrough (None keep / "" clear / value set).
    if "api_base" in fields:
        fields["api_base"] = fields["api_base"] or None
    if body.api_key is not None:
        fields["api_key"] = body.api_key.strip()
    row = db.update_custom_model(model_id, user.id, **fields)
    if not row:
        raise HTTPException(404, "自定义模型不存在")
    return _pack_custom(row)


@router.delete("/models/custom/{model_id}")
def delete_custom(model_id: str) -> dict:
    user = current_user()
    ok = db.delete_custom_model(model_id, user.id)
    if not ok:
        raise HTTPException(404, "自定义模型不存在")
    return {"ok": True}


class HideBuiltinIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    hidden: bool


@router.post("/models/builtin/hide")
def hide_builtin(body: HideBuiltinIn) -> dict:
    user = current_user()
    if body.name not in {r[2] for r in _BUILTIN}:
        raise HTTPException(404, "未知的内置模型")
    db.set_builtin_hidden(user.id, body.name, body.hidden)
    return {"ok": True, "name": body.name, "hidden": body.hidden}
