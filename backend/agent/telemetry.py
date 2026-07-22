"""Optional Langfuse observability for the AgentMate runtime.

The integration is deliberately opt-in and fail-open: tracing must never change
the local chat/SSE path.  Content capture is a separate opt-in so enabling
latency/token observability does not upload prompts, files, reasoning, or tool
results by default.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import logging
import re
from typing import Any, Iterator

from config import settings


_log = logging.getLogger("agentmate.telemetry")
_client: Any | None = None
_client_initialized = False
_init_warning_emitted = False

_SENSITIVE_KEY_PARTS = (
    "authorization", "api_key", "apikey", "cookie", "credential",
    "password", "passwd", "secret", "token",
)
_BEARER_RE = re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]+")
_KEY_RE = re.compile(r"(?i)\b(?:sk|pk)-[a-z0-9_-]{12,}\b")
_MAX_CAPTURED_STRING = 8_000


def _sensitive_key(key: str) -> bool:
    lowered = key.lower()
    # Token usage counters are observability data, not credentials. Keep the
    # allowlist narrow so fields such as access_token / refresh_token still redact.
    if lowered in {
        "prompt_tokens", "completion_tokens", "total_tokens",
        "input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens",
    } or lowered.endswith("_token_count"):
        return False
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def configured() -> bool:
    """Return whether tracing is explicitly enabled and fully configured."""
    return bool(
        settings.LANGFUSE_ENABLED
        and settings.LANGFUSE_PUBLIC_KEY
        and settings.LANGFUSE_SECRET_KEY
        and settings.LANGFUSE_BASE_URL
    )


def _sample_rate() -> float:
    try:
        return min(1.0, max(0.0, float(settings.LANGFUSE_SAMPLE_RATE)))
    except (TypeError, ValueError):
        return 1.0


def _get_client() -> Any | None:
    global _client, _client_initialized, _init_warning_emitted
    if _client_initialized:
        return _client
    _client_initialized = True
    if not configured():
        return None
    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            base_url=settings.LANGFUSE_BASE_URL,
            environment=settings.LANGFUSE_TRACING_ENVIRONMENT,
            sample_rate=_sample_rate(),
            tracing_enabled=True,
        )
    except Exception as exc:  # noqa: BLE001 - observability is never fatal
        _client = None
        if not _init_warning_emitted:
            _log.warning("Langfuse 初始化失败，已关闭本进程追踪：%s", type(exc).__name__)
            _init_warning_emitted = True
    return _client


def _propagate_attributes(**kwargs: Any):
    from langfuse import propagate_attributes

    return propagate_attributes(**kwargs)


def _redact_text(value: str) -> str:
    value = _BEARER_RE.sub("Bearer [REDACTED]", value)
    value = _KEY_RE.sub("[REDACTED_KEY]", value)
    if len(value) > _MAX_CAPTURED_STRING:
        return value[:_MAX_CAPTURED_STRING] + f"\n[TRUNCATED {len(value) - _MAX_CAPTURED_STRING} chars]"
    return value


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, item in list(value.items())[:128]:
            key = str(raw_key)[:120]
            if _sensitive_key(key):
                result[key] = "[REDACTED]"
            else:
                result[key] = _redact(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in list(value)[:128]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _redact_text(str(value))


def _summarize(value: Any) -> Any:
    if isinstance(value, str):
        return {"type": "text", "chars": len(value)}
    if isinstance(value, dict):
        return {
            "type": "object",
            "keys": [str(key)[:120] for key in list(value.keys())[:128]],
            "fields": len(value),
        }
    if isinstance(value, (list, tuple)):
        return {"type": "list", "items": len(value)}
    if value is None:
        return None
    return {"type": type(value).__name__}


def safe_payload(value: Any) -> Any:
    """Prepare observation input/output according to the content opt-in."""
    return _redact(value) if settings.LANGFUSE_CAPTURE_CONTENT else _summarize(value)


def _safe_metadata(value: dict[str, Any] | None) -> dict[str, Any] | None:
    return _redact(value) if value else None


def _safe_status(value: str | None) -> str | None:
    if not value:
        return None
    if not settings.LANGFUSE_CAPTURE_CONTENT:
        return f"details suppressed ({len(value)} chars)"
    return _redact_text(value)[:500]


def anonymous_user_id(user_id: str) -> str:
    return hashlib.sha256(f"agentmate:{user_id}".encode("utf-8")).hexdigest()[:24]


class Observation:
    """Exception-safe facade over a Langfuse observation or a no-op."""

    def __init__(self, inner: Any | None = None) -> None:
        self.inner = inner

    @property
    def enabled(self) -> bool:
        return self.inner is not None

    def update(self, **kwargs: Any) -> None:
        if self.inner is None:
            return
        if "input" in kwargs:
            kwargs["input"] = safe_payload(kwargs["input"])
        if "output" in kwargs:
            kwargs["output"] = safe_payload(kwargs["output"])
        if "metadata" in kwargs:
            kwargs["metadata"] = _safe_metadata(kwargs["metadata"])
        if "status_message" in kwargs:
            kwargs["status_message"] = _safe_status(kwargs["status_message"])
        try:
            self.inner.update(**kwargs)
        except Exception as exc:  # noqa: BLE001 - telemetry must not alter chat
            _log.debug("Langfuse observation update failed: %s", type(exc).__name__)


@contextmanager
def observation(
    *,
    as_type: str,
    name: str,
    input: Any = None,
    metadata: dict[str, Any] | None = None,
    model: str | None = None,
    model_parameters: dict[str, Any] | None = None,
) -> Iterator[Observation]:
    client = _get_client()
    if client is None:
        yield Observation()
        return

    kwargs: dict[str, Any] = {
        "as_type": as_type,
        "name": name,
        "input": safe_payload(input),
        "metadata": _safe_metadata(metadata),
    }
    if model:
        kwargs["model"] = model
    if model_parameters:
        kwargs["model_parameters"] = model_parameters

    try:
        manager = client.start_as_current_observation(**kwargs)
        inner = manager.__enter__()
    except Exception as exc:  # noqa: BLE001
        _log.debug("Langfuse observation start failed: %s", type(exc).__name__)
        yield Observation()
        return

    wrapped = Observation(inner)
    try:
        yield wrapped
    except BaseException as exc:
        wrapped.update(level="ERROR", status_message=str(exc))
        try:
            manager.__exit__(type(exc), exc, exc.__traceback__)
        except Exception as close_exc:  # noqa: BLE001
            _log.debug("Langfuse observation close failed: %s", type(close_exc).__name__)
        raise
    else:
        try:
            manager.__exit__(None, None, None)
        except Exception as exc:  # noqa: BLE001
            _log.debug("Langfuse observation close failed: %s", type(exc).__name__)


@contextmanager
def chat_observation(
    *,
    session_id: str,
    user_id: str,
    user_text: str,
    project_id: str | None,
    mode: str,
    selected_model: str | None,
    refs_count: int,
    skills_count: int,
    connectors_count: int,
) -> Iterator[Observation]:
    metadata = {
        "project_id": project_id or "",
        "mode": mode,
        "selected_model": selected_model or "default",
        "refs_count": refs_count,
        "skills_count": skills_count,
        "connectors_count": connectors_count,
    }
    with observation(
        as_type="agent",
        name="agentmate.chat",
        input=user_text,
        metadata=metadata,
    ) as root:
        attributes = None
        if root.enabled:
            try:
                attributes = _propagate_attributes(
                    user_id=anonymous_user_id(user_id),
                    session_id=session_id,
                    trace_name="agentmate.chat",
                    tags=["agentmate", mode],
                )
                attributes.__enter__()
            except Exception as exc:  # noqa: BLE001
                attributes = None
                _log.debug("Langfuse attribute propagation failed: %s", type(exc).__name__)
        try:
            yield root
        except BaseException as exc:
            if attributes is not None:
                try:
                    attributes.__exit__(type(exc), exc, exc.__traceback__)
                except Exception:  # noqa: BLE001
                    pass
            raise
        else:
            if attributes is not None:
                try:
                    attributes.__exit__(None, None, None)
                except Exception:  # noqa: BLE001
                    pass


def generation_observation(
    *, name: str, model: str, messages: list[dict[str, Any]], temperature: float,
    round_number: int,
):
    return observation(
        as_type="generation",
        name=name,
        input=messages,
        model=model,
        model_parameters={"temperature": temperature},
        metadata={"round": round_number},
    )


def tool_observation(
    *, name: str, arguments: Any, source: str, metadata: dict[str, Any] | None = None,
):
    return observation(
        as_type="retriever" if name == "knowledge_retrieve" else "tool",
        name=name,
        input=arguments,
        metadata={"source": source, **(metadata or {})},
    )


def shutdown() -> None:
    """Flush and stop the background exporter during application shutdown."""
    global _client, _client_initialized
    client = _client
    if client is not None:
        try:
            client.shutdown()
        except Exception as exc:  # noqa: BLE001
            _log.warning("Langfuse shutdown failed: %s", type(exc).__name__)
    _client = None
    _client_initialized = False


def reconfigure() -> None:
    """Apply hot-reloaded device settings to the next observation."""
    global _init_warning_emitted
    shutdown()
    _init_warning_emitted = False
