"""Single source of truth for effective model metadata and Run pricing snapshots (WB-346)."""
from __future__ import annotations

import time
from typing import Any

from config import settings
from storage import db, provider_seed

CAPABILITIES = ["text", "image", "audio", "video", "tools", "reasoning"]
META_KEYS = (
    "capabilities", "input_cost", "input_cost_cached", "output_cost",
    "context_window", "currency", "note",
)


def default_capabilities(model_id: str) -> list[str]:
    """Conservative editable fallback when no curated or owner metadata exists."""
    model = (model_id or "").lower()
    caps = ["text", "tools"]
    if any(marker in model for marker in (
        "4o", "-vl", "vl-", "vision", "omni", "multimodal", "glm-4v",
        "pixtral", "gemini", "claude-3", "claude-4", "4.5v", "-vision",
    )):
        caps.append("image")
    if any(marker in model for marker in (
        "reasoner", "o1", "o3", "o4", "r1", "deepseek-r", "think", "reasoning", "qwq",
    )):
        caps.append("reasoning")
    return caps


def effective_meta(
    owner_id: str, model_ref: str, model_id: str,
    stored: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve owner override > curated provider default > conservative fallback."""
    custom = (stored if stored is not None else db.list_model_meta(owner_id)).get(model_ref)
    if custom:
        return {**{key: custom.get(key) for key in META_KEYS}, "source": "custom"}
    curated = provider_seed.MODEL_DEFAULTS.get((model_id or "").lower())
    if curated:
        output = {key: curated.get(key) for key in META_KEYS}
        output["capabilities"] = curated.get("capabilities") or default_capabilities(model_id)
        return {**output, "source": "preset"}
    return {
        **{key: None for key in META_KEYS},
        "capabilities": default_capabilities(model_id),
        "source": "default",
    }


def effective_model_ref(owner_id: str, selection: str | None) -> str:
    return (selection or "").strip() or db.get_default_model(owner_id)


def build_run_snapshot(owner_id: str, selection: str | None, model_id: str) -> dict[str, Any]:
    """Capture only non-secret execution metadata; credentials and endpoints never enter Runs."""
    model_ref = effective_model_ref(owner_id, selection)
    meta = effective_meta(owner_id, model_ref, model_id)
    provider_id = ""
    if model_ref.startswith("@") and ":" in model_ref:
        provider_id = model_ref[1:].partition(":")[0]
    currency = str(meta.get("currency") or "").strip() or None
    return {
        "model_ref": model_ref,
        "model_id": model_id,
        "provider_id": provider_id or None,
        "capabilities": list(meta.get("capabilities") or []),
        "context_window": meta.get("context_window"),
        "pricing": {
            "input_per_million": meta.get("input_cost"),
            "cached_input_per_million": meta.get("input_cost_cached"),
            "output_per_million": meta.get("output_cost"),
            "currency": currency,
            "unit": "per_million_tokens",
            "source": meta.get("source") or "default",
            "note": meta.get("note"),
        },
        "captured_at": time.time(),
    }


def estimate_cost(
    snapshot: dict[str, Any], prompt_tokens: int, completion_tokens: int,
    cached_prompt_tokens: int = 0,
) -> tuple[float | None, str | None]:
    """Estimate provider cost without currency conversion or invented cache-hit usage."""
    prompt = max(0, int(prompt_tokens))
    completion = max(0, int(completion_tokens))
    if prompt + completion <= 0:
        return None, None
    pricing = snapshot.get("pricing") if isinstance(snapshot, dict) else None
    if not isinstance(pricing, dict):
        return None, None
    input_cost = pricing.get("input_per_million")
    cached_input_cost = pricing.get("cached_input_per_million")
    output_cost = pricing.get("output_per_million")
    currency = str(pricing.get("currency") or "").strip()
    if input_cost is None or output_cost is None or not currency:
        return None, None
    cached = min(prompt, max(0, int(cached_prompt_tokens)))
    uncached = prompt - cached
    cached_rate = float(cached_input_cost) if cached_input_cost is not None else float(input_cost)
    estimated = (
        uncached * float(input_cost)
        + cached * cached_rate
        + completion * float(output_cost)
    ) / 1_000_000
    return round(estimated, 10), currency


def account_has_model_configuration(owner_id: str) -> bool:
    """Reflect the actual owner-scoped credential sources instead of only `.env`."""
    # provider_keys also stores non-LLM credentials such as WeKnora; only curated
    # model providers count as an enabled LLM channel.
    if db.list_provider_keys(owner_id) & set(provider_seed.PROVIDERS_BY_ID):
        return True
    custom = db.list_custom_models(owner_id, include_secrets=False)
    if any(bool(item.get("has_key")) for item in custom):
        return True
    return settings.llm_configured
