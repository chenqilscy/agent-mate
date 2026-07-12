"""Model menu — built-in provider channels + custom models (WB-128, supersedes the
WB-124 fake-builtin list).

Two real sources feed the composer model picker:
  - **providers**: a curated registry of real vendors (DeepSeek / 智谱 / MiniMax / Kimi /
    通义 / OpenAI, see storage/provider_seed.py). Each has a fixed base_url + real model
    names; the user supplies an API key per provider and its models become runnable.
    Keys are backend-only, per-owner, NEVER returned to the frontend (铁律#4).
  - **custom**: free-form fallback (WB-124) for anything not in the preset list.

There is no fake "Auto"/multiplier anymore — a pick resolves to a real provider at run
time (agent.runtime.resolve_model_config). The `.env` model remains the local backstop,
surfaced honestly as a 「默认」entry.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from auth.deps import current_user
from config import settings
from storage import db, provider_seed

router = APIRouter(prefix="/api", tags=["models"])


def _effective_base_path(owner_id: str, prov: dict) -> tuple[str, str]:
    """有效 base_url + chat_path = 用户覆盖（WB-129）∨ 预置默认。"""
    cfg = db.get_provider_config(owner_id, prov["id"]) or {}
    base = cfg.get("base_url") or prov["base_url"]
    path = cfg.get("chat_path") or prov.get("chat_path") or provider_seed.DEFAULT_CHAT_PATH
    return base, path


def _provider_models_mgmt(owner_id: str, prov: dict) -> list[dict]:
    """厂商模型的**管理视图**：预置模型（带 hidden 标记）+ 用户新增模型。"""
    preset = prov["models"]
    overrides = db.list_provider_model_overrides(owner_id, prov["id"])
    hidden = {o["model_id"] for o in overrides if o["hidden"]}
    added = [o["model_id"] for o in overrides if not o["hidden"] and o["model_id"] not in preset]
    out = [{"model_id": m, "preset": True, "hidden": m in hidden} for m in preset]
    out += [{"model_id": m, "preset": False, "hidden": False} for m in added]
    return out


def _sel_key_provider(pid: str, model_id: str) -> str:
    return f"@{pid}:{model_id}"


def _pack_custom(row: dict) -> dict:
    """WB-124 custom-model row (secret-stripped) → picker/management shape."""
    return {
        "key": row["name"],
        "id": row["id"],
        "icon": row.get("icon") or "🧩",
        "color": row.get("color") or "",
        "name": row["name"],
        "group": "custom",
        "model_id": row.get("model_id") or "",
        "api_base": row.get("api_base") or "",
        "has_key": bool(row.get("has_key")),
    }


@router.get("/models")
def list_models() -> dict:
    """Composed model menu: providers (grouped, for the config modal), custom, and a flat
    `models` list of directly-selectable entries (for the picker)."""
    user = current_user()
    keyed = db.list_provider_keys(user.id)

    providers: list[dict] = []
    picker: list[dict] = []
    for prov in provider_seed.PROVIDERS:
        has_key = prov["id"] in keyed
        mgmt = _provider_models_mgmt(user.id, prov)
        eff_base, eff_path = _effective_base_path(user.id, prov)
        providers.append({
            "id": prov["id"],
            "name": prov["name"],
            "icon": prov["icon"],
            "color": prov["color"],
            # 有效值（含用户覆盖）+ 预置默认（供「恢复默认」判断，WB-129）。
            "base_url": eff_base,
            "chat_path": eff_path,
            "default_base_url": prov["base_url"],
            "default_chat_path": prov.get("chat_path") or provider_seed.DEFAULT_CHAT_PATH,
            "key_hint": prov["key_hint"],
            "site": prov["site"],
            "has_key": has_key,
            "models": mgmt,
        })
        if has_key:
            for m in mgmt:
                if m["hidden"]:
                    continue
                picker.append({
                    "key": _sel_key_provider(prov["id"], m["model_id"]),
                    "icon": prov["icon"],
                    "color": prov["color"],
                    "name": m["model_id"],
                    "provider": prov["id"],
                    "providerName": prov["name"],
                    "group": "provider",
                })

    custom = [_pack_custom(r) for r in db.list_custom_models(user.id, include_secrets=False)]

    # 「默认」= .env 后端配置的模型，永远可用（local-first 兜底，取代假 Auto）。key="" → resolve 回退 .env。
    backstop = {
        "key": "",
        "icon": "⚙️",
        "color": "",
        "name": f"默认 · {settings.LLM_MODEL}",
        "group": "default",
    }
    models = [backstop] + picker + custom
    # 首屏默认选中：第一个可用厂商模型，否则默认兜底。
    default = picker[0]["key"] if picker else ""
    return {
        "default": default,
        "effective": settings.LLM_MODEL,
        "providers": providers,
        "custom": custom,
        "models": models,
    }


# ---- provider keys + model overrides (WB-128) --------------------------

def _require_provider(pid: str) -> dict:
    prov = provider_seed.PROVIDERS_BY_ID.get(pid)
    if not prov:
        raise HTTPException(404, "未知厂商")
    return prov


class ProviderKeyIn(BaseModel):
    api_key: str = Field(default="", max_length=800)  # 空串 = 撤销该厂商


@router.put("/providers/{pid}/key")
def set_provider_key(pid: str, body: ProviderKeyIn) -> dict:
    user = current_user()
    _require_provider(pid)
    db.set_provider_key(user.id, pid, body.api_key.strip())
    return {"ok": True, "provider": pid, "has_key": bool(body.api_key.strip())}


class ProviderConfigIn(BaseModel):
    # 空串 = 恢复该字段为预置默认。两者都空 = 全恢复默认。
    base_url: str = Field(default="", max_length=300)
    chat_path: str = Field(default="", max_length=120)


@router.patch("/providers/{pid}/config")
def set_provider_config(pid: str, body: ProviderConfigIn) -> dict:
    user = current_user()
    prov = _require_provider(pid)
    db.set_provider_config(user.id, pid, body.base_url, body.chat_path)
    base, path = _effective_base_path(user.id, prov)
    return {"ok": True, "base_url": base, "chat_path": path}


@router.post("/providers/{pid}/models/fetch")
async def fetch_provider_models(pid: str) -> dict:
    """在线列举厂商真实模型（WB-129）：用有效 base+key 打 OpenAI 兼容 `GET {base}/models`。
    治「硬编码模型名过时」——真实数据来自厂商。个别厂商不支持则如实返回错误，让用户手动加。"""
    user = current_user()
    prov = _require_provider(pid)
    key = db.get_provider_key(user.id, pid)
    if not key:
        raise HTTPException(400, "请先为该厂商填写 API Key")
    base, _ = _effective_base_path(user.id, prov)
    url = f"{base.rstrip('/')}/models"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {key}"})
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"连接失败：{e}"}
    if resp.status_code >= 400:
        return {"ok": False, "error": f"该厂商未返回模型列表（HTTP {resp.status_code}），请手动添加"}
    try:
        data = resp.json()
        # OpenAI 兼容：{"data": [{"id": "..."}]}；个别厂商直接给 list。
        items = data.get("data", data) if isinstance(data, dict) else data
        ids = sorted({str(m["id"]) for m in items if isinstance(m, dict) and m.get("id")})
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "厂商返回格式非标准，请手动添加"}
    if not ids:
        return {"ok": False, "error": "厂商未返回任何模型，请手动添加"}
    return {"ok": True, "models": ids}


class ProviderModelIn(BaseModel):
    model_id: str = Field(min_length=1, max_length=120)


@router.post("/providers/{pid}/models")
def add_provider_model(pid: str, body: ProviderModelIn) -> dict:
    user = current_user()
    _require_provider(pid)
    db.add_provider_model(user.id, pid, body.model_id.strip())
    return {"ok": True}


class ProviderModelHideIn(BaseModel):
    model_id: str = Field(min_length=1, max_length=120)
    hidden: bool


@router.post("/providers/{pid}/models/hide")
def hide_provider_model(pid: str, body: ProviderModelHideIn) -> dict:
    user = current_user()
    prov = _require_provider(pid)
    if body.model_id in prov["models"]:
        db.set_provider_model_hidden(user.id, pid, body.model_id.strip(), body.hidden)
    else:
        # 用户新增的模型：恢复=保留(hidden=0)，隐藏其实等价于删除该新增行。
        if body.hidden:
            db.remove_provider_model(user.id, pid, body.model_id.strip())
        else:
            db.add_provider_model(user.id, pid, body.model_id.strip())
    return {"ok": True}


# ---- custom models (WB-124, free-form fallback) ------------------------

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
    if body.name is not None:
        clash = db.get_custom_model_by_name(user.id, body.name.strip())
        if clash and clash["id"] != model_id:
            raise HTTPException(409, "已有同名自定义模型")
    fields: dict = {}
    for k in ("name", "model_id", "api_base", "icon", "color", "mult"):
        v = getattr(body, k)
        if v is not None:
            fields[k] = v.strip() if k in ("name", "model_id", "api_base") else v
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
