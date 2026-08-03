"""Process-local health ledger for recurring background loops (WB-359)."""
from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.Lock()
_components: dict[str, dict[str, Any]] = {}


def _entry(name: str) -> dict[str, Any]:
    return _components.setdefault(name, {
        "name": name,
        "last_attempt_at": None,
        "last_success_at": None,
        "last_failure_at": None,
        "consecutive_failures": 0,
        "last_error": None,
    })


def record_success(name: str, now: float | None = None) -> None:
    ts = time.time() if now is None else float(now)
    with _lock:
        state = _entry(name)
        state.update({
            "last_attempt_at": ts,
            "last_success_at": ts,
            "consecutive_failures": 0,
            "last_error": None,
        })


def record_failure(name: str, error: BaseException, now: float | None = None) -> None:
    ts = time.time() if now is None else float(now)
    with _lock:
        state = _entry(name)
        state.update({
            "last_attempt_at": ts,
            "last_failure_at": ts,
            "consecutive_failures": int(state["consecutive_failures"]) + 1,
            "last_error": f"{type(error).__name__}: {error}"[:1000],
        })


def snapshot() -> dict[str, Any]:
    with _lock:
        components = [dict(_components[name]) for name in sorted(_components)]
    return {
        "healthy": bool(components) and all(
            item["consecutive_failures"] == 0 for item in components
        ),
        "components": components,
    }


def reset_for_tests() -> None:
    with _lock:
        _components.clear()
