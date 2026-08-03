"""Envelope encryption for control-plane secrets stored in SQLite."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config import settings

_V1_PREFIX = "enc:v1:"
_V2_PREFIX = "enc:v2:"
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


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


def current_key_id() -> str:
    key_id = settings.SSO_SECRET_ENCRYPTION_KEY_ID or (
        "primary" if settings.SSO_SECRET_ENCRYPTION_KEY else "local"
    )
    if not _KEY_ID_RE.fullmatch(key_id):
        raise SecretKeyUnavailable("invalid SSO encryption key id")
    return key_id


def _keyring() -> dict[str, bytes]:
    result = {current_key_id(): _master_key()}
    raw = settings.SSO_SECRET_ENCRYPTION_PREVIOUS_KEYS or "{}"
    try:
        previous = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SecretKeyUnavailable("invalid previous SSO encryption keyring") from exc
    if not isinstance(previous, dict):
        raise SecretKeyUnavailable("previous SSO encryption keyring must be an object")
    for key_id, secret in previous.items():
        key_id = str(key_id)
        if not _KEY_ID_RE.fullmatch(key_id) or not isinstance(secret, str) or not secret:
            raise SecretKeyUnavailable("invalid previous SSO encryption key entry")
        result.setdefault(key_id, hashlib.sha256(secret.encode("utf-8")).digest())
    return result


def is_encrypted(value: str) -> bool:
    return value.startswith(_V1_PREFIX) or value.startswith(_V2_PREFIX)


def key_id(value: str) -> str:
    if value.startswith(_V2_PREFIX):
        rest = value[len(_V2_PREFIX):]
        return rest.split(":", 1)[0] if ":" in rest else ""
    return "legacy" if value.startswith(_V1_PREFIX) else "plaintext"


def needs_rotation(value: str) -> bool:
    return bool(value) and (not value.startswith(_V2_PREFIX) or key_id(value) != current_key_id())


def encrypt(value: str, *, context: str) -> str:
    if not value:
        return ""
    nonce = os.urandom(12)
    active_key_id = current_key_id()
    ciphertext = AESGCM(_keyring()[active_key_id]).encrypt(
        nonce, value.encode("utf-8"), context.encode("utf-8"),
    )
    return f"{_V2_PREFIX}{active_key_id}:" + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt(value: str, *, context: str) -> str:
    if not value:
        return ""
    if not is_encrypted(value):
        return value
    try:
        ring = _keyring()
        if value.startswith(_V2_PREFIX):
            rest = value[len(_V2_PREFIX):]
            cipher_key_id, encoded = rest.split(":", 1)
            key = ring.get(cipher_key_id)
            if key is None:
                raise SecretKeyUnavailable(f"SSO encryption key unavailable: {cipher_key_id}")
            candidates = [key]
        else:
            encoded = value[len(_V1_PREFIX):]
            candidates = list(ring.values())
        raw = base64.urlsafe_b64decode(encoded.encode("ascii"))
        for key in candidates:
            try:
                plain = AESGCM(key).decrypt(raw[:12], raw[12:], context.encode("utf-8"))
                return plain.decode("utf-8")
            except Exception:  # noqa: BLE001 - legacy v1 tries the configured keyring
                continue
        raise ValueError("sso_secret_decryption_failed")
    except SecretKeyUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValueError("sso_secret_decryption_failed") from exc
