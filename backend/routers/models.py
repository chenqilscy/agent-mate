"""Model menu — built-in provider channels + custom models (WB-128, supersedes the
WB-124 fake-builtin list).

Two real sources feed the composer model picker:
  - **providers**: a curated registry of real vendors (DeepSeek / 智谱 / MiniMax / Kimi /
    通义 / OpenAI, see storage/provider_seed.py). Each has a fixed base_url + real model
    names; the user supplies an API key per provider and its models become runnable.
    Keys are backend-only, per-owner, NEVER returned to the frontend (铁律#4).
  - **custom**: free-form fallback (WB-124) for anything not in the preset list.

There is no fake "Auto"/multiplier anymore — a pick resolves to a real provider at run
time (agent.runtime.resolve_model_config). The 「默认模型」(what an empty selection follows)
is a user choice set here via PUT /models/default and stored per-owner in DB — it no longer
reads .env's LLM_MODEL (WB-136). No default set → chat surfaces an honest error.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from auth.deps import current_user
from storage import db, model_governance, provider_seed

router = APIRouter(prefix="/api", tags=["models"])


def _effective_base_path(owner_id: str, prov: dict) -> tuple[str, str]:
    """有效 base_url + chat_path = 用户覆盖（WB-129）∨ 预置默认。"""
    cfg = db.get_provider_config(owner_id, prov["id"]) or {}
    base = cfg.get("base_url") or prov["base_url"]
    path = cfg.get("chat_path") or prov.get("chat_path") or provider_seed.DEFAULT_CHAT_PATH
    return base, path


# 能力词表（WB-132）：模态 + 工具 + 推理。前端徽标一一对应。
CAPABILITIES = model_governance.CAPABILITIES


def _default_capabilities(model_id: str) -> list[str]:
    return model_governance.default_capabilities(model_id)


def _effective_meta(owner_id: str, model_ref: str, model_id: str, stored: dict[str, dict]) -> dict:
    return model_governance.effective_meta(owner_id, model_ref, model_id, stored)


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


def _resolve_runnable_name(owner_id: str, ref: str) -> str | None:
    """ref 若指向一个当前可运行的模型，返回其显示名；否则 None（WB-136 默认模型校验）。
    可运行 = 厂商有 key 且该模型可见 ∨ 存在同名自定义模型。"""
    if ref.startswith("@") and ":" in ref:
        pid, _, mid = ref[1:].partition(":")
        prov = provider_seed.PROVIDERS_BY_ID.get(pid)
        if not prov or not mid or pid not in db.list_provider_keys(owner_id):
            return None
        visible = {m["model_id"] for m in _provider_models_mgmt(owner_id, prov) if not m["hidden"]}
        return mid if mid in visible else None
    row = db.get_custom_model_by_name(owner_id, ref, include_secrets=False)
    return row["name"] if row else None


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
    stored_meta = db.list_model_meta(user.id)  # WB-132: 批量取，逐模型附有效 meta

    providers: list[dict] = []
    picker: list[dict] = []
    for prov in provider_seed.PROVIDERS:
        has_key = prov["id"] in keyed
        mgmt = _provider_models_mgmt(user.id, prov)
        for m in mgmt:  # WB-132: 每个厂商模型附能力/成本（覆盖∨启发式默认）
            ref = _sel_key_provider(prov["id"], m["model_id"])
            m["meta"] = _effective_meta(user.id, ref, m["model_id"], stored_meta)
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
                    "meta": m["meta"],
                })

    custom = [_pack_custom(r) for r in db.list_custom_models(user.id, include_secrets=False)]
    for cm in custom:  # WB-132: 自定义模型也附 meta（ref = 自定义名）
        cm["meta"] = _effective_meta(user.id, cm["name"], cm.get("model_id") or "", stored_meta)

    # 「默认模型」= 用户在「配置模型」里选定、按 owner 存 DB 的 ref（WB-136，取代 .env LLM_MODEL）。
    # 校验它仍指向一个可运行模型（厂商有 key 的模型 ∨ 自定义）；失效（撤 key/删模型）则自愈清空。
    runnable = {p["key"]: p["name"] for p in picker}
    runnable.update({c["key"]: c["name"] for c in custom})
    default_model = db.get_default_model(user.id)
    if default_model and default_model not in runnable:
        db.set_default_model(user.id, "")  # 自愈：不再可用就清掉
        default_model = ""

    # 模型菜单顶部的「默认」条：key="" 表示「跟随默认」；名字显所选默认（未设置则如实标注）。
    backstop = {
        "key": "",
        "icon": "⭐",
        "color": "",
        "name": f"默认 · {runnable[default_model]}" if default_model else "默认（未设置）",
        "group": "default",
    }
    models = [backstop] + picker + custom
    return {
        "default_model": default_model,
        "providers": providers,
        "custom": custom,
        "models": models,
    }


class ModelGovernanceIn(BaseModel):
    default_run_token_budget: int = Field(default=0, ge=0, le=10_000_000)


def _model_governance_payload(owner_id: str) -> dict:
    return {
        "policy": {
            "default_run_token_budget": db.get_model_default_run_token_budget(owner_id),
        },
        "usage": db.get_model_governance_summary(owner_id),
    }


@router.get("/models/governance")
def get_model_governance() -> dict:
    return _model_governance_payload(current_user().id)


@router.put("/models/governance")
def set_model_governance(body: ModelGovernanceIn) -> dict:
    user = current_user()
    db.set_model_default_run_token_budget(user.id, body.default_run_token_budget)
    return _model_governance_payload(user.id)


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
    prov = _require_provider(pid)
    key = body.api_key.strip()
    db.set_provider_key(user.id, pid, key)
    # 便利（WB-136）：刚启用一个厂商、且当前还没设默认模型 → 自动把默认设为它第一个可见模型，
    # 这样「配好一个厂商就能直接用」，无需再手动设默认（取代旧 App.tsx 首屏回填）。
    if key and not db.get_default_model(user.id):
        visible = [m["model_id"] for m in _provider_models_mgmt(user.id, prov) if not m["hidden"]]
        if visible:
            db.set_default_model(user.id, _sel_key_provider(pid, visible[0]))
    return {"ok": True, "provider": pid, "has_key": bool(key)}


class DefaultModelIn(BaseModel):
    model_ref: str = Field(default="", max_length=200)  # ''=清除默认


@router.put("/models/default")
def set_default_model(body: DefaultModelIn) -> dict:
    """设/清「默认模型」（WB-136）——未显式选模型时跟随它。ref 必须是当前可运行的模型
    （厂商有 key 的模型 ∨ 自定义模型），否则拒绝；''=清除。取代 .env LLM_MODEL。"""
    user = current_user()
    ref = body.model_ref.strip()
    if ref and not _resolve_runnable_name(user.id, ref):
        raise HTTPException(400, "该模型当前不可运行（需先给对应厂商配 Key，或选一个自定义模型）")
    db.set_default_model(user.id, ref)
    return {"ok": True, "default_model": ref}


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


# ---- model meta: capabilities + cost (WB-132) --------------------------

class ModelMetaIn(BaseModel):
    model_ref: str = Field(min_length=1, max_length=200)
    capabilities: list[str] = Field(default=[], max_length=12)
    input_cost: float | None = Field(default=None, ge=0)
    input_cost_cached: float | None = Field(default=None, ge=0)  # 缓存命中输入价（WB-134）
    output_cost: float | None = Field(default=None, ge=0)
    context_window: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)  # ¥/$ 等（WB-134）
    note: str | None = Field(default=None, max_length=300)
    reset: bool = False  # true = 清除覆盖，回准确默认/启发式


@router.put("/models/meta")
def set_model_meta(body: ModelMetaIn) -> dict:
    user = current_user()
    if body.reset:
        db.delete_model_meta(user.id, body.model_ref)
        return {"ok": True, "reset": True}
    caps = [c for c in body.capabilities if c in CAPABILITIES]  # 只收白名单能力
    db.set_model_meta(
        user.id, body.model_ref,
        capabilities=caps, input_cost=body.input_cost, input_cost_cached=body.input_cost_cached,
        output_cost=body.output_cost, context_window=body.context_window,
        currency=(body.currency or None), note=(body.note or None),
    )
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
