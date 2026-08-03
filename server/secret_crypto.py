"""Envelope encryption for control-plane secrets stored in SQLite."""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config import settings

_PREFIX = "enc:v1:"


class SecretKeyUnavailable(RuntimeError):
    pass


def _key_path() -> Path:
    configured = settings.SSO_LOCAL_KEY_PATH.strip()
    return Path(configured) if configured else Path(str(settings.DB_PATH) + ".sso.key")


def _master_key() -> bytes:
    configured = settings.SSO_SECRET_ENCRYPTION_KEY
    if configured:
        return hashlib.sha256(configured.encode("utf-8")).digest()
    if settings.ENVIRONMENT in {"production", "prod"}:
        raise SecretKeyUnavailable(
            "AGENTMATE_SSO_SECRET_ENCRYPTION_KEY is required in production"
        )
    path = _key_path()
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = os.urandom(32)
        try:
            with path.open("xb") as handle:
                handle.write(raw)
        except FileExistsError:
            raw = path.read_bytes()
    if len(raw) != 32:
        raise SecretKeyUnavailable(f"invalid local SSO key file: {path}")
    return raw


def is_encrypted(value: str) -> bool:
    return value.startswith(_PREFIX)


def encrypt(value: str, *, context: str) -> str:
    if not value:
        return ""
    nonce = os.urandom(12)
    ciphertext = AESGCM(_master_key()).encrypt(
        nonce, value.encode("utf-8"), context.encode("utf-8"),
    )
    return _PREFIX + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt(value: str, *, context: str) -> str:
    if not value:
        return ""
    if not is_encrypted(value):
        return value
    try:
        raw = base64.urlsafe_b64decode(value[len(_PREFIX):].encode("ascii"))
        plain = AESGCM(_master_key()).decrypt(
            raw[:12], raw[12:], context.encode("utf-8"),
        )
        return plain.decode("utf-8")
    except SecretKeyUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValueError("sso_secret_decryption_failed") from exc
