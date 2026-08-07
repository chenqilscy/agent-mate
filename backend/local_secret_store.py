"""At-rest protection for Local Agent credentials (WB-434).

Windows desktop builds use the current user's DPAPI profile. Other platforms
use a private, mode-0600 Fernet key beside the Local Agent database until their
native keychain adapters land. Only encrypted envelopes are persisted in
SQLite; callers always work with plaintext in process memory only.
"""
from __future__ import annotations

import base64
import ctypes
import os
import sys
from ctypes import wintypes
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from config import settings


_DPAPI_PREFIX = "dpapi:v1:"
_FERNET_PREFIX = "fernet:v1:"


if sys.platform == "win32":
    class _DataBlob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _dpapi_protect(raw: bytes) -> bytes:
    source, source_buffer = _blob(raw)
    output = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptProtectData(
        ctypes.byref(source), "AgentMate Local Agent", None, None, None, 0x1,
        ctypes.byref(output),
    )
    del source_buffer
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)


def _dpapi_unprotect(raw: bytes) -> bytes:
    source, source_buffer = _blob(raw)
    output = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0x1, ctypes.byref(output),
    )
    del source_buffer
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)


def _fallback_key_path() -> Path:
    return Path(settings.LOCAL_AGENT_DB_PATH).with_suffix(".secrets.key")


def _fallback_fernet() -> Fernet:
    path = _fallback_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        key = path.read_bytes()
    except FileNotFoundError:
        key = Fernet.generate_key()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            key = path.read_bytes()
        else:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(key)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return Fernet(key)


def protect(value: str) -> str:
    raw = value.encode("utf-8")
    if sys.platform == "win32":
        encrypted = _dpapi_protect(raw)
        return _DPAPI_PREFIX + base64.b64encode(encrypted).decode("ascii")
    return _FERNET_PREFIX + _fallback_fernet().encrypt(raw).decode("ascii")


def unprotect(envelope: str) -> str:
    if envelope.startswith(_DPAPI_PREFIX):
        if sys.platform != "win32":
            raise ValueError("Windows DPAPI secret is unavailable on this platform")
        raw = base64.b64decode(envelope[len(_DPAPI_PREFIX):], validate=True)
        return _dpapi_unprotect(raw).decode("utf-8")
    if envelope.startswith(_FERNET_PREFIX):
        try:
            return _fallback_fernet().decrypt(
                envelope[len(_FERNET_PREFIX):].encode("ascii"),
            ).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Local Agent secret cannot be decrypted") from exc
    # One-time compatibility for development snapshots created before WB-434.
    # The next successful write upgrades the value to an encrypted envelope.
    return envelope
