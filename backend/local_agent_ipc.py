"""In-memory bootstrap secret for the Tauri <-> Local Agent IPC channel.

The token is delivered once through the sidecar stdin pipe. It deliberately
never lives in a command-line argument, environment variable, database or web
frontend state.
"""
from __future__ import annotations

import secrets
import threading


_lock = threading.Lock()
_token = ""


def install_token(token: str) -> None:
    value = token.strip()
    if len(value) < 32 or len(value) > 256:
        raise ValueError("Local Agent IPC token must contain 32-256 characters")
    with _lock:
        global _token
        _token = value


def expected_token() -> str:
    with _lock:
        return _token


def authenticated(supplied: str) -> bool:
    expected = expected_token()
    return len(expected) >= 32 and bool(supplied) and secrets.compare_digest(supplied, expected)


def clear_token() -> None:
    with _lock:
        global _token
        _token = ""
