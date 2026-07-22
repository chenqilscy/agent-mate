"""Typed platform setting registry with environment fallback (WB-291).

Only settings with a real hot-reload execution path appear here. Bootstrap values
such as the database path, bind address, PBKDF work factor and build version stay
deployment-only in :mod:`config` and are rejected by the admin API.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from typing import Any, Literal
from urllib.parse import urlsplit

from config import settings


ValueType = Literal["string", "integer", "secret"]


@dataclass(frozen=True)
class Definition:
    key: str
    group: str
    label: str
    description: str
    value_type: ValueType
    env_name: str
    setting_attr: str
    secret: bool = False
    minimum: int | None = None
    maximum: int | None = None
    placeholder: str = ""


DEFINITIONS = (
    Definition(
        key="knowledge.weknora_url", group="knowledge", label="WeKnora 服务地址",
        description="项目知识库统一使用的 WeKnora API 地址。保存后立即影响新请求。",
        value_type="string", env_name="AGENTMATE_SERVER_WEKNORA_URL",
        setting_attr="WEKNORA_URL", placeholder="http://127.0.0.1:37201",
    ),
    Definition(
        key="knowledge.weknora_api_key", group="knowledge", label="WeKnora API Key",
        description="平台租户凭据，只写不回读；留空表示保持当前值。",
        value_type="secret", env_name="AGENTMATE_SERVER_WEKNORA_API_KEY",
        setting_attr="WEKNORA_API_KEY", secret=True, placeholder="sk-...",
    ),
    Definition(
        key="knowledge.weknora_embedding_model_id", group="knowledge", label="默认嵌入模型 ID",
        description="可留空，届时自动选择 WeKnora 中首个 embedding 模型。",
        value_type="string", env_name="AGENTMATE_SERVER_WEKNORA_EMBEDDING_MODEL_ID",
        setting_attr="WEKNORA_EMBEDDING_MODEL_ID",
    ),
    Definition(
        key="collaboration.invite_ttl_seconds", group="collaboration", label="邀请有效期（秒）",
        description="0 表示永不过期；修改只影响之后创建的邀请。",
        value_type="integer", env_name="AGENTMATE_SERVER_INVITE_TTL",
        setting_attr="INVITE_TTL", minimum=0, maximum=31_536_000,
    ),
)

BY_KEY = {definition.key: definition for definition in DEFINITIONS}

DEPLOYMENT_ONLY_KEYS = {
    "server.database_path", "server.storage_path", "server.host", "server.port",
    "security.pbkdf2_iterations", "security.master_key", "release.app_version",
}


def definition(key: str) -> Definition:
    try:
        return BY_KEY[key]
    except KeyError as exc:
        if key in DEPLOYMENT_ONLY_KEYS:
            raise ValueError(f"{key} 是启动级配置，不能通过页面热更新。") from exc
        raise ValueError(f"未知平台设置：{key}") from exc


def _stored(defn: Definition) -> str | None:
    import db
    return db.get_platform_secret(defn.key) if defn.secret else db.get_setting(defn.key)


def effective_with_source(key: str) -> tuple[Any, str]:
    defn = definition(key)
    stored = _stored(defn)
    if stored is not None:
        raw: Any = stored
        source = "database"
    else:
        raw = getattr(settings, defn.setting_attr)
        source = "environment" if os.getenv(defn.env_name) is not None else "default"
    if defn.value_type == "integer":
        try:
            return int(raw), source
        except (TypeError, ValueError):
            return int(getattr(settings, defn.setting_attr)), source
    return str(raw or ""), source


def effective(key: str) -> Any:
    return effective_with_source(key)[0]


def _validate_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    try:
        parsed = urlsplit(normalized)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(f"WeKnora 地址无效：{exc}") from exc
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("WeKnora 地址必须是包含主机名的 http(s) URL。")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("WeKnora 地址不能包含用户名或密码。")
    return normalized


def validate(key: str, value: Any) -> str:
    defn = definition(key)
    if defn.value_type == "integer":
        if isinstance(value, bool):
            raise ValueError(f"{defn.label} 必须是整数。")
        if isinstance(value, float) and not value.is_integer():
            raise ValueError(f"{defn.label} 必须是整数。")
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{defn.label} 必须是整数。") from exc
        if defn.minimum is not None and parsed < defn.minimum:
            raise ValueError(f"{defn.label} 不能小于 {defn.minimum}。")
        if defn.maximum is not None and parsed > defn.maximum:
            raise ValueError(f"{defn.label} 不能大于 {defn.maximum}。")
        return str(parsed)
    text = str(value or "").strip()
    if len(text) > (2_000 if defn.secret else 1_000):
        raise ValueError(f"{defn.label} 过长。")
    if key == "knowledge.weknora_url":
        return _validate_url(text)
    return text


def set_value(key: str, value: Any, *, actor_id: str) -> None:
    import db
    defn = definition(key)
    normalized = validate(key, value)
    if _stored(defn) == normalized:
        return
    before, _ = effective_with_source(key)
    if defn.secret:
        if not normalized:
            return  # empty secret means keep unchanged; clearing is explicit
        db.set_platform_secret(key, normalized)
        before_audit = "configured" if before else "not_configured"
        after_audit = "configured"
    else:
        db.set_setting(key, normalized)
        before_audit = str(before)
        after_audit = normalized
    db.add_platform_setting_audit(
        setting_key=key, actor_id=actor_id, action="set",
        before_value=before_audit, after_value=after_audit,
    )


def clear_value(key: str, *, actor_id: str) -> None:
    import db
    defn = definition(key)
    before, _ = effective_with_source(key)
    if defn.secret:
        db.set_platform_secret(key, None)
        before_audit = "configured" if before else "not_configured"
    else:
        db.delete_setting(key)
        before_audit = str(before)
    after, source = effective_with_source(key)
    db.add_platform_setting_audit(
        setting_key=key, actor_id=actor_id, action="clear",
        before_value=before_audit,
        after_value=("configured" if after else "not_configured") if defn.secret else f"{after} ({source})",
    )


def public_item(defn: Definition) -> dict[str, Any]:
    value, source = effective_with_source(defn.key)
    item = asdict(defn)
    item.pop("setting_attr", None)
    item.update({
        "source": source,
        "configured": bool(value) if defn.secret else True,
        "value": None if defn.secret else value,
        "hot_reload": True,
    })
    return item


def public_registry() -> list[dict[str, Any]]:
    return [public_item(item) for item in DEFINITIONS]
