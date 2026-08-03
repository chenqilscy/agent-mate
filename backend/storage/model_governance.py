"""Single source of truth for effective model metadata and Run pricing snapshots (WB-346)."""
from __future__ import annotations

import datetime as dt
import hashlib
import ipaddress
import socket
import time
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from config import settings
from storage import db, provider_seed

CAPABILITIES = ["text", "image", "audio", "video", "tools", "reasoning"]
META_KEYS = (
    "capabilities", "input_cost", "input_cost_cached", "output_cost",
    "context_window", "max_output_tokens", "currency", "note",
)
POLICY_BUDGET_KEYS = (
    "daily_soft_tokens", "daily_hard_tokens", "monthly_soft_tokens", "monthly_hard_tokens",
    "daily_soft_cost", "daily_hard_cost", "monthly_soft_cost", "monthly_hard_cost",
)
DEFAULT_POLICY: dict[str, Any] = {
    "allowlist": [], "fallback_chain": [], "currency": "USD",
    **{key: 0 for key in POLICY_BUDGET_KEYS},
    "provider_health_ttl_seconds": 900,
    "credential_max_age_days": 90,
}


def normalize_policy(raw: dict[str, Any] | None) -> dict[str, Any]:
    value = raw if isinstance(raw, dict) else {}
    policy = dict(DEFAULT_POLICY)
    for key in ("allowlist", "fallback_chain"):
        items = value.get(key) if isinstance(value.get(key), list) else []
        policy[key] = list(dict.fromkeys(
            str(item).strip()[:200] for item in items if str(item).strip()
        ))[:50]
    for key in POLICY_BUDGET_KEYS:
        try:
            policy[key] = max(0, float(value.get(key) or 0))
        except (TypeError, ValueError):
            policy[key] = 0
        if key.endswith("_tokens"):
            policy[key] = int(min(policy[key], 1_000_000_000))
        else:
            policy[key] = min(policy[key], 1_000_000_000.0)
    policy["currency"] = (str(value.get("currency") or "USD").strip().upper()[:8] or "USD")
    try:
        policy["provider_health_ttl_seconds"] = max(
            60, min(86400, int(value.get("provider_health_ttl_seconds") or 900)),
        )
    except (TypeError, ValueError):
        policy["provider_health_ttl_seconds"] = 900
    try:
        policy["credential_max_age_days"] = max(
            0, min(3650, int(value.get("credential_max_age_days", 90))),
        )
    except (TypeError, ValueError):
        policy["credential_max_age_days"] = 90
    return policy


def validate_endpoint_url(value: str, *, shared_backend: bool | None = None) -> str:
    """Validate model endpoints and fail closed on shared-backend SSRF targets."""
    raw = (value or "").strip().rstrip("/")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("模型接入地址必须是合法的 HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("模型接入地址不能包含凭据、查询参数或 fragment")
    if shared_backend is None:
        host = (settings.HOST or "").strip().lower()
        shared_backend = host not in {"127.0.0.1", "localhost", "::1", "[::1]"}
    if shared_backend:
        hostname = parsed.hostname.lower().rstrip(".")
        if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
            raise ValueError("共享后端不能访问本机或保留地址")
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(hostname, parsed.port)}
        except OSError as exc:
            raise ValueError("模型接入地址当前无法解析") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address.split("%", 1)[0])
            if not ip.is_global:
                raise ValueError("共享后端不能访问本机、私网或保留地址")
    netloc = parsed.hostname
    if ":" in netloc and not netloc.startswith("["):
        netloc = f"[{netloc}]"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""))


def endpoint_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def provider_id_for_ref(model_ref: str) -> str:
    if model_ref.startswith("@") and ":" in model_ref:
        return model_ref[1:].partition(":")[0]
    return ""


def _current_provider_endpoint_hash(owner_id: str, provider_id: str) -> str:
    provider = provider_seed.PROVIDERS_BY_ID.get(provider_id)
    if not provider:
        return ""
    config = db.get_provider_config(owner_id, provider_id) or {}
    base = str(config.get("base_url") or provider["base_url"]).strip().rstrip("/")
    return endpoint_hash(base)


def model_is_runnable(owner_id: str, model_ref: str) -> bool:
    if model_ref.startswith("@") and ":" in model_ref:
        provider_id, _, model_id = model_ref[1:].partition(":")
        provider = provider_seed.PROVIDERS_BY_ID.get(provider_id)
        if not provider or not model_id or not db.get_provider_key(owner_id, provider_id):
            return False
        overrides = db.list_provider_model_overrides(owner_id, provider_id)
        hidden = {item["model_id"] for item in overrides if item["hidden"]}
        added = {item["model_id"] for item in overrides if not item["hidden"]}
        return model_id in (set(provider["models"]) | added) - hidden
    custom = db.get_custom_model_by_name(owner_id, model_ref, include_secrets=False)
    # Custom rows intentionally allow a blank per-row key to use the backend .env
    # credential fallback; existence is therefore the runnable contract.
    return bool(custom)


def _policy_layers(owner_id: str, project_id: str | None) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    user_policy = normalize_policy(db.get_user_model_policy(owner_id))
    project = db.get_project(project_id) if project_id else None
    org_entry = db.get_server_org_model_policy(project.org_id if project else None)
    org_policy = normalize_policy(org_entry["policy"]) if org_entry else None
    return user_policy, org_policy, org_entry


def _period_starts(now: float) -> tuple[float, float]:
    local = dt.datetime.fromtimestamp(now).astimezone()
    day = local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    month = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
    return day, month


def policy_decision(
    owner_id: str, selection: str | None, *, project_id: str | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Resolve allowlist, hard budgets and a recent-health fallback before a Run."""
    generated_at = float(now if now is not None else time.time())
    requested = (selection or "").strip() or db.get_default_model(owner_id)
    user_policy, org_policy, org_entry = _policy_layers(owner_id, project_id)
    layers = [("user", user_policy)] + ([("organization", org_policy)] if org_policy else [])
    audit = {
        "requested_model_ref": requested,
        "selected_model_ref": requested,
        "fallback_from": None,
        "selection_reason": "requested" if selection else "account_default",
        "organization": ({"org_id": org_entry["org_id"], "revision": org_entry["revision"]} if org_entry else None),
        "warnings": [],
        "allowed": True,
        "error": "",
    }
    if not requested:
        # Keep the legacy resolver as the source of the user-facing "no default"
        # error. Tests/embedded callers may inject a resolver without persisting a
        # default, and an empty policy must remain behaviorally compatible.
        audit.update(selection_reason="resolution_deferred")
        return audit
    for source, policy in layers:
        allowlist = set(policy["allowlist"])
        if allowlist and requested not in allowlist:
            audit.update(allowed=False, error=f"模型 {requested} 不在{source}策略允许列表中")
            return audit

    day_start, month_start = _period_starts(generated_at)
    hard_remaining: list[int] = []
    for source, policy in layers:
        currency = policy["currency"]
        day_usage = db.get_model_usage_since(owner_id, day_start, currency=currency)
        month_usage = db.get_model_usage_since(owner_id, month_start, currency=currency)
        for period, usage in (("daily", day_usage), ("monthly", month_usage)):
            soft_tokens = int(policy[f"{period}_soft_tokens"])
            hard_tokens = int(policy[f"{period}_hard_tokens"])
            soft_cost = float(policy[f"{period}_soft_cost"])
            hard_cost = float(policy[f"{period}_hard_cost"])
            if soft_tokens and usage["tokens"] >= soft_tokens:
                audit["warnings"].append(f"{source} {period} token 软预算已达到")
            if soft_cost and usage["cost"] >= soft_cost:
                audit["warnings"].append(f"{source} {period} {currency} 软预算已达到")
            if hard_tokens:
                remaining = hard_tokens - int(usage["tokens"])
                if remaining <= 0:
                    audit.update(allowed=False, error=f"{source} {period} token 硬预算已用尽")
                    return audit
                hard_remaining.append(remaining)
            if hard_cost and usage["cost"] >= hard_cost:
                audit.update(allowed=False, error=f"{source} {period} {currency} 硬预算已用尽")
                return audit
    audit["hard_remaining_tokens"] = min(hard_remaining) if hard_remaining else 0

    provider_id = provider_id_for_ref(requested)
    recent_unhealthy = False
    if provider_id:
        health = db.get_provider_health(owner_id, provider_id)
        ttl = min(int(policy["provider_health_ttl_seconds"]) for _, policy in layers)
        recent_unhealthy = bool(
            health and health.get("status") == "unhealthy"
            and health.get("endpoint_hash") == _current_provider_endpoint_hash(owner_id, provider_id)
            and generated_at - float(health.get("checked_at") or 0) <= ttl
        )
    if recent_unhealthy:
        candidates = list(dict.fromkeys(
            candidate for _, policy in layers for candidate in policy["fallback_chain"]
        ))
        for candidate in candidates:
            if candidate == requested or not model_is_runnable(owner_id, candidate):
                continue
            if any(policy["allowlist"] and candidate not in policy["allowlist"] for _, policy in layers):
                continue
            fallback_provider = provider_id_for_ref(candidate)
            fallback_health = db.get_provider_health(owner_id, fallback_provider) if fallback_provider else None
            if (
                fallback_health and fallback_health.get("status") == "unhealthy"
                and fallback_health.get("endpoint_hash") == _current_provider_endpoint_hash(owner_id, fallback_provider)
            ):
                ttl = min(int(policy["provider_health_ttl_seconds"]) for _, policy in layers)
                if generated_at - float(fallback_health.get("checked_at") or 0) <= ttl:
                    continue
            audit.update(
                selected_model_ref=candidate, fallback_from=requested,
                selection_reason="provider_unhealthy_fallback",
            )
            break
        else:
            audit.update(allowed=False, error=f"Provider {provider_id} 最近健康检查失败且没有可用 fallback")
    return audit


def governance_payload(owner_id: str, *, project_id: str | None = None) -> dict[str, Any]:
    user, organization, entry = _policy_layers(owner_id, project_id)
    return {
        "user": user,
        "organization": ({**organization, "org_id": entry["org_id"], "revision": entry["revision"]} if organization and entry else None),
    }


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


def build_run_snapshot(
    owner_id: str, selection: str | None, model_id: str,
    governance: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        "max_output_tokens": meta.get("max_output_tokens"),
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
        "governance": governance or {},
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
