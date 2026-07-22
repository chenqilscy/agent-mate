"""Typed, hot-reloadable device setting registry (WB-291).

Device settings affect this AgentMate installation, not a Server account or one
project. Environment variables remain bootstrap/disaster-recovery fallbacks.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import os
from typing import Any, Literal
from urllib.parse import urlsplit

from config import settings
from storage import db


ValueType = Literal["string", "boolean", "number", "secret", "choice"]


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
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()
    placeholder: str = ""


DEFINITIONS = (
    Definition("observability.enabled", "observability", "启用 Langfuse", "默认关闭；配置完整后对新对话立即生效。", "boolean", "LANGFUSE_ENABLED", "LANGFUSE_ENABLED"),
    Definition("observability.base_url", "observability", "Langfuse 地址", "自托管或云端 Langfuse 服务地址。", "string", "LANGFUSE_BASE_URL", "LANGFUSE_BASE_URL", placeholder="http://127.0.0.1:3000"),
    Definition("observability.public_key", "observability", "Public Key", "Langfuse 项目公钥。", "string", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_PUBLIC_KEY"),
    Definition("observability.secret_key", "observability", "Secret Key", "只写不回读，留空表示保持当前值。", "secret", "LANGFUSE_SECRET_KEY", "LANGFUSE_SECRET_KEY", secret=True),
    Definition("observability.environment", "observability", "环境标签", "写入 trace 的 environment 标签。", "string", "LANGFUSE_TRACING_ENVIRONMENT", "LANGFUSE_TRACING_ENVIRONMENT"),
    Definition("observability.sample_rate", "observability", "采样率", "0 到 1；1 表示全部采样。", "number", "LANGFUSE_SAMPLE_RATE", "LANGFUSE_SAMPLE_RATE", minimum=0, maximum=1),
    Definition("observability.capture_content", "observability", "采集对话正文", "高敏选项；关闭时只上传类型、长度和运行指标。", "boolean", "LANGFUSE_CAPTURE_CONTENT", "LANGFUSE_CAPTURE_CONTENT"),
    Definition("voice.asr_enabled", "voice", "启用本地语音识别", "音频始终留在本机。", "boolean", "ASR_ENABLED", "ASR_ENABLED"),
    Definition("voice.asr_model", "voice", "ASR 模型", "修改后释放已加载模型，下一次使用时重新加载。", "choice", "ASR_MODEL", "ASR_MODEL", choices=("tiny", "base", "small", "medium", "large-v3")),
    Definition("voice.asr_device", "voice", "计算设备", "CPU 适合通用设备；CUDA 需要兼容显卡环境。", "choice", "ASR_DEVICE", "ASR_DEVICE", choices=("cpu", "cuda")),
    Definition("voice.asr_compute_type", "voice", "计算精度", "CPU 推荐 int8，CUDA 可使用 float16。", "choice", "ASR_COMPUTE_TYPE", "ASR_COMPUTE_TYPE", choices=("int8", "int8_float16", "float16", "float32")),
    Definition("collaboration.server_url", "collaboration", "AgentMate Server 地址", "留空即纯本地；保存后登录、同步与项目知识请求立即使用新地址。", "string", "AGENTMATE_SERVER_URL", "AGENTMATE_SERVER_URL", placeholder="http://127.0.0.1:8100"),
    Definition("collaboration.timeline_upload", "collaboration", "上传团队时间线", "只上传执行元数据与短标题，不上传对话正文、凭据或工作区文件。", "boolean", "AGENTMATE_SERVER_TIMELINE_UPLOAD", "AGENTMATE_SERVER_TIMELINE_UPLOAD"),
)

BY_KEY = {item.key: item for item in DEFINITIONS}
_BOOTSTRAP = {item.setting_attr: getattr(settings, item.setting_attr) for item in DEFINITIONS}

DEPLOYMENT_ONLY_KEYS = {
    "runtime.database_path", "runtime.workspace_path", "runtime.host", "runtime.port",
    "runtime.skills_directory", "runtime.asr_model_directory", "release.app_version",
    "release.tool_contract_version",
}


def definition(key: str) -> Definition:
    try:
        return BY_KEY[key]
    except KeyError as exc:
        if key in DEPLOYMENT_ONLY_KEYS:
            raise ValueError(f"{key} 是启动级配置，不能通过页面热更新。") from exc
        raise ValueError(f"未知本机设置：{key}") from exc


def _stored(item: Definition) -> str | None:
    return db.get_device_secret(item.key) if item.secret else db.get_device_setting(item.key)


def _parse(item: Definition, raw: Any) -> Any:
    if item.value_type == "boolean":
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    if item.value_type == "number":
        return float(raw)
    return str(raw or "")


def effective_with_source(key: str) -> tuple[Any, str]:
    item = definition(key)
    stored = _stored(item)
    if stored is not None:
        return _parse(item, stored), "database"
    source = "environment" if os.getenv(item.env_name) is not None else "default"
    return _parse(item, _BOOTSTRAP[item.setting_attr]), source


def effective(key: str) -> Any:
    return effective_with_source(key)[0]


def _validate_url(label: str, value: str, *, allow_empty: bool = True) -> str:
    text = value.strip().rstrip("/")
    if not text and allow_empty:
        return ""
    try:
        parsed = urlsplit(text)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(f"{label}无效：{exc}") from exc
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"{label}必须是包含主机名的 http(s) URL。")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{label}不能包含用户名或密码。")
    return text


def validate(key: str, value: Any) -> str:
    item = definition(key)
    if item.value_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError(f"{item.label}必须是布尔值。")
        return "1" if value else "0"
    if item.value_type == "number":
        if isinstance(value, bool):
            raise ValueError(f"{item.label}必须是数字。")
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{item.label}必须是数字。") from exc
        if not math.isfinite(parsed):
            raise ValueError(f"{item.label}必须是有限数字。")
        if item.minimum is not None and parsed < item.minimum:
            raise ValueError(f"{item.label}不能小于 {item.minimum}。")
        if item.maximum is not None and parsed > item.maximum:
            raise ValueError(f"{item.label}不能大于 {item.maximum}。")
        return str(parsed)
    text = str(value or "").strip()
    if len(text) > (2_000 if item.secret else 1_000):
        raise ValueError(f"{item.label}过长。")
    if item.value_type == "choice" and text not in item.choices:
        raise ValueError(f"{item.label}必须是：{', '.join(item.choices)}。")
    if key in {"observability.base_url", "collaboration.server_url"}:
        return _validate_url(item.label, text)
    return text


def set_value(key: str, value: Any, *, actor_id: str) -> None:
    item = definition(key)
    normalized = validate(key, value)
    if _stored(item) == normalized:
        return
    before, _source = effective_with_source(key)
    if item.secret:
        if not normalized:
            return
        db.set_device_secret(key, normalized)
        before_audit = "configured" if before else "not_configured"
        after_audit = "configured"
    else:
        db.set_device_setting(key, normalized)
        before_audit = str(before)
        after_audit = normalized
    db.add_device_setting_audit(
        setting_key=key, actor_id=actor_id, action="set",
        before_value=before_audit, after_value=after_audit,
    )


def clear_value(key: str, *, actor_id: str) -> None:
    item = definition(key)
    before, _source = effective_with_source(key)
    if item.secret:
        db.set_device_secret(key, None)
        before_audit = "configured" if before else "not_configured"
    else:
        db.set_device_setting(key, None)
        before_audit = str(before)
    after, source = effective_with_source(key)
    db.add_device_setting_audit(
        setting_key=key, actor_id=actor_id, action="clear",
        before_value=before_audit,
        after_value=("configured" if after else "not_configured") if item.secret else f"{after} ({source})",
    )


def apply_all(*, changed_keys: set[str] | None = None) -> None:
    for item in DEFINITIONS:
        setattr(settings, item.setting_attr, effective(item.key))
    changed = changed_keys or set()
    if not changed or any(key.startswith("observability.") for key in changed):
        from agent import telemetry
        telemetry.reconfigure()
    if not changed or any(key.startswith("voice.") for key in changed):
        from routers import asr
        asr.reset_model()


def public_item(item: Definition) -> dict[str, Any]:
    value, source = effective_with_source(item.key)
    result = asdict(item)
    result.pop("setting_attr", None)
    result["choices"] = list(item.choices)
    result.update({
        "source": source,
        "configured": bool(value) if item.secret else True,
        "value": None if item.secret else value,
        "hot_reload": True,
    })
    return result


def public_registry() -> list[dict[str, Any]]:
    return [public_item(item) for item in DEFINITIONS]
