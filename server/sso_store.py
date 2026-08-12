"""Durable federated-identity state and account linking (WB-362)."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import time
from typing import Any
from urllib.parse import urlparse

import db
import secret_crypto
from config import settings

PROVIDERS = {
    "google": "Google",
    "wechat": "微信",
    "telegram": "Telegram",
}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def provider_config(provider: str) -> dict[str, Any] | None:
    if provider not in PROVIDERS:
        return None
    row = db.get_conn().execute(
        "SELECT * FROM sso_provider_configs WHERE provider=?", (provider,)
    ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["client_secret"] = secret_crypto.decrypt(
        str(result.get("client_secret") or ""), context=provider,
    )
    return result


def public_providers() -> list[dict[str, str]]:
    rows = db.get_conn().execute(
        "SELECT provider FROM sso_provider_configs "
        "WHERE enabled=1 AND client_id<>'' AND client_secret<>'' ORDER BY provider"
    ).fetchall()
    result = []
    for row in rows:
        provider = str(row["provider"])
        try:
            config = provider_config(provider)
        except (ValueError, secret_crypto.SecretKeyUnavailable):
            continue
        if config and config.get("client_secret") and provider in PROVIDERS:
            result.append({"id": provider, "label": PROVIDERS[provider]})
    return result


def admin_providers() -> list[dict[str, Any]]:
    result = []
    for provider, label in PROVIDERS.items():
        row = db.get_conn().execute(
            "SELECT * FROM sso_provider_configs WHERE provider=?", (provider,),
        ).fetchone()
        config = dict(row) if row else {}
        stored = str(config.get("client_secret") or "")
        decryptable = False
        if stored:
            try:
                decryptable = bool(secret_crypto.decrypt(stored, context=provider))
            except (ValueError, secret_crypto.SecretKeyUnavailable):
                decryptable = False
        result.append({
            "id": provider,
            "label": label,
            "enabled": bool(config.get("enabled")),
            "client_id": str(config.get("client_id") or ""),
            "secret_configured": bool(stored),
            "secret_decryptable": decryptable,
            "secret_key_id": secret_crypto.key_id(stored),
            "updated_at": float(config.get("updated_at") or 0),
        })
    return result


def set_provider(
    provider: str, *, enabled: bool, client_id: str,
    client_secret: str | None, updated_by: str,
) -> dict[str, Any]:
    if provider not in PROVIDERS:
        raise ValueError("unsupported_provider")
    old_row = db.get_conn().execute(
        "SELECT * FROM sso_provider_configs WHERE provider=?", (provider,),
    ).fetchone()
    old_stored = str(old_row["client_secret"] or "") if old_row else ""
    old = dict(old_row) if old_row else {}
    if client_secret is None:
        secret = secret_crypto.decrypt(old_stored, context=provider) if old_stored else ""
    else:
        secret = client_secret.strip()
    if enabled and (not client_id.strip() or not secret):
        raise ValueError("provider_credentials_required")
    encrypted = secret_crypto.encrypt(secret, context=provider)
    now = time.time()
    conn = db.get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "INSERT INTO sso_provider_configs "
            "(provider,enabled,client_id,client_secret,updated_by,updated_at) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(provider) DO UPDATE SET enabled=excluded.enabled,client_id=excluded.client_id,"
            "client_secret=excluded.client_secret,updated_by=excluded.updated_by,updated_at=excluded.updated_at",
            (provider, int(enabled), client_id.strip(), encrypted, updated_by, now),
        )
        actions: list[tuple[str, dict[str, Any]]] = []
        if bool(old.get("enabled")) != enabled:
            actions.append(("enabled" if enabled else "disabled", {}))
        if str(old.get("client_id") or "") != client_id.strip():
            actions.append(("client_id_changed", {
                "before_configured": bool(old.get("client_id")),
                "after_configured": bool(client_id.strip()),
            }))
        if client_secret is not None:
            actions.append(("client_secret_rotated", {
                "before_configured": bool(old_stored),
                "after_configured": bool(secret),
            }))
        for action, details in actions or [("configuration_saved", {})]:
            conn.execute(
                "INSERT INTO sso_provider_audit "
                "(id,provider,actor_id,action,details,created_at) VALUES (?,?,?,?,?,?)",
                (db.new_uuid(), provider, updated_by, action,
                 json.dumps(details, ensure_ascii=False), now),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return next(item for item in admin_providers() if item["id"] == provider)


def migrate_plaintext_provider_secrets() -> int:
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT provider,client_secret FROM sso_provider_configs WHERE client_secret<>''"
    ).fetchall()
    changed = 0
    conn.execute("BEGIN IMMEDIATE")
    try:
        for row in rows:
            stored = str(row["client_secret"] or "")
            if secret_crypto.is_encrypted(stored) and not secret_crypto.needs_rotation(stored):
                continue
            provider = str(row["provider"])
            plain = secret_crypto.decrypt(stored, context=provider) if secret_crypto.is_encrypted(stored) else stored
            action = (
                "client_secret_key_rotated" if secret_crypto.is_encrypted(stored)
                else "client_secret_encrypted_migration"
            )
            conn.execute(
                "UPDATE sso_provider_configs SET client_secret=?,updated_at=? WHERE provider=?",
                (secret_crypto.encrypt(plain, context=provider), time.time(), provider),
            )
            conn.execute(
                "INSERT INTO sso_provider_audit "
                "(id,provider,actor_id,action,details,created_at) VALUES (?,?,?,?,?,?)",
                (db.new_uuid(), provider, "system", action,
                 json.dumps({"from_key_id": secret_crypto.key_id(stored),
                             "to_key_id": secret_crypto.current_key_id()}, ensure_ascii=False), time.time()),
            )
            changed += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return changed


def list_provider_audit(limit: int = 100) -> list[dict[str, Any]]:
    rows = db.get_conn().execute(
        "SELECT * FROM sso_provider_audit ORDER BY created_at DESC,rowid DESC LIMIT ?",
        (max(1, min(limit, 500)),),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["details"] = json.loads(item["details"] or "{}")
        except (json.JSONDecodeError, TypeError):
            item["details"] = {}
        result.append(item)
    return result


def provider_readiness() -> dict[str, Any]:
    parsed = urlparse(settings.SSO_PUBLIC_BASE_URL)
    loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    public_https = parsed.scheme == "https" and bool(parsed.hostname) and not loopback
    production = settings.ENVIRONMENT in {"production", "prod"}
    external_key = bool(settings.SSO_SECRET_ENCRYPTION_KEY)
    blockers: list[str] = []
    warnings: list[str] = []
    if not public_https:
        (blockers if production else warnings).append("public_https_callback_required")
    if production and not external_key:
        blockers.append("external_encryption_key_required")
    if settings.SSO_REGISTRATION_POLICY not in {"open", "invite_only", "existing_only", "disabled"}:
        blockers.append("invalid_registration_policy")
    if db.count_accounts() == 0 and not settings.BOOTSTRAP_ADMIN_SECRET:
        blockers.append("bootstrap_admin_secret_required")
    providers: list[dict[str, Any]] = []
    for provider, label in PROVIDERS.items():
        row = db.get_conn().execute(
            "SELECT enabled,client_id,client_secret FROM sso_provider_configs WHERE provider=?",
            (provider,),
        ).fetchone()
        config = dict(row) if row else {}
        configured = bool(config.get("client_id")) and bool(config.get("client_secret"))
        provider_blockers: list[str] = []
        decryptable = False
        if config.get("client_secret"):
            try:
                decryptable = bool(secret_crypto.decrypt(
                    str(config["client_secret"]), context=provider,
                ))
            except (ValueError, secret_crypto.SecretKeyUnavailable):
                provider_blockers.append("secret_decryption_failed")
        if bool(config.get("enabled")) and not configured:
            provider_blockers.append("credentials_required")
        if bool(config.get("enabled")) and not public_https:
            provider_blockers.append("public_https_callback_required")
        providers.append({
            "id": provider,
            "label": label,
            "enabled": bool(config.get("enabled")),
            "configured": configured,
            "callback_url": (
                f"{settings.SSO_PUBLIC_BASE_URL}/api/auth/sso/{provider}/callback"
            ),
            "ready_for_external_test": bool(config.get("enabled")) and configured and decryptable and public_https,
            "secret_key_id": secret_crypto.key_id(str(config.get("client_secret") or "")),
            "blockers": provider_blockers,
        })
    return {
        "ready": not blockers and all(
            not item["blockers"] for item in providers if item["enabled"]
        ),
        "environment": settings.ENVIRONMENT,
        "registration_policy": settings.SSO_REGISTRATION_POLICY,
        "public_base_url": settings.SSO_PUBLIC_BASE_URL,
        "public_https": public_https,
        "secret_protection": "external_master_key" if external_key else "local_development_key",
        "blockers": blockers,
        "warnings": warnings,
        "providers": providers,
    }


def check_rate_limit(rate_key: str) -> bool:
    window = int(time.time() // 60)
    conn = db.get_conn()
    conn.execute(
        "DELETE FROM auth_rate_windows WHERE window_start<?", (window - 2,)
    )
    conn.execute(
        "INSERT INTO auth_rate_windows(rate_key,window_start,count) VALUES (?,?,1) "
        "ON CONFLICT(rate_key,window_start) DO UPDATE SET count=count+1",
        (rate_key[:200], window),
    )
    row = conn.execute(
        "SELECT count FROM auth_rate_windows WHERE rate_key=? AND window_start=?",
        (rate_key[:200], window),
    ).fetchone()
    conn.commit()
    return bool(row and int(row["count"]) <= settings.AUTH_RATE_LIMIT_PER_MINUTE)


def create_signup_invite(created_by: str, ttl_seconds: int = 86400) -> tuple[dict, str]:
    raw = "ami_" + secrets.token_urlsafe(24)
    now = time.time()
    item = {
        "id": db.new_uuid(), "created_by": created_by, "created_at": now,
        "expires_at": now + max(60, min(ttl_seconds, 30 * 86400)),
    }
    db.get_conn().execute(
        "INSERT INTO sso_signup_invites(id,code_hash,created_by,created_at,expires_at) VALUES (?,?,?,?,?)",
        (item["id"], _hash(raw), created_by, item["created_at"], item["expires_at"]),
    )
    db.get_conn().commit()
    return item, raw


def create_attempt(
    provider: str, *, mode: str = "login", account_id: str | None = None,
    invite_code: str = "",
) -> tuple[dict[str, Any], str, str]:
    if not provider_config(provider) or provider not in PROVIDERS:
        raise ValueError("provider_unavailable")
    state = secrets.token_urlsafe(32)
    attempt_token = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    nonce = secrets.token_urlsafe(24)
    now = time.time()
    item = {
        "id": db.new_uuid(), "provider": provider, "mode": mode,
        "code_verifier": verifier, "nonce": nonce,
        "expires_at": now + settings.SSO_STATE_TTL_SECONDS,
    }
    db.get_conn().execute(
        "DELETE FROM sso_attempts WHERE expires_at<?", (now - 86400,)
    )
    db.get_conn().execute(
        "INSERT INTO sso_attempts "
        "(id,state_hash,attempt_token_hash,provider,mode,account_id,invite_code_hash,"
        "code_verifier,nonce,status,created_at,expires_at) VALUES (?,?,?,?,?,?,?,?,?,'pending',?,?)",
        (item["id"], _hash(state), _hash(attempt_token), provider, mode, account_id,
         _hash(invite_code) if invite_code else None, verifier, nonce, now, item["expires_at"]),
    )
    db.get_conn().commit()
    return item, state, attempt_token


def consume_state(provider: str, state: str) -> dict[str, Any] | None:
    conn = db.get_conn()
    now = time.time()
    row = conn.execute(
        "SELECT * FROM sso_attempts WHERE provider=? AND state_hash=? AND status='pending' "
        "AND expires_at>?", (provider, _hash(state), now),
    ).fetchone()
    if not row:
        return None
    changed = conn.execute(
        "UPDATE sso_attempts SET status='processing' WHERE id=? AND status='pending'",
        (row["id"],),
    )
    conn.commit()
    return dict(row) if changed.rowcount == 1 else None


def fail_attempt(attempt_id: str, code: str) -> None:
    db.get_conn().execute(
        "UPDATE sso_attempts SET status='error',error_code=?,completed_at=? WHERE id=?",
        (code[:80], time.time(), attempt_id),
    )
    db.get_conn().commit()


def _unique_name(display_name: str, email: str, provider: str) -> str:
    base = (display_name or email.split("@", 1)[0] or provider).strip()
    base = re.sub(r"[\x00-\x1f]", "", base)[:50] or provider
    candidate = base
    suffix = 1
    while db.find_account_by_name(candidate):
        suffix += 1
        candidate = f"{base[:50]}-{suffix}"
    return candidate


def resolve_identity(attempt: dict[str, Any], identity: dict[str, Any]) -> str:
    provider = str(attempt["provider"])
    subject = str(identity.get("subject") or "").strip()
    if not subject:
        raise ValueError("missing_subject")
    email = str(identity.get("email") or "").strip().lower()
    display_name = str(identity.get("name") or "").strip()
    conn = db.get_conn()
    existing = conn.execute(
        "SELECT * FROM external_identities WHERE provider=? AND subject=?",
        (provider, subject),
    ).fetchone()
    if attempt["mode"] == "link":
        account_id = str(attempt.get("account_id") or "")
        if not account_id or not db.get_account(account_id):
            raise ValueError("link_account_missing")
        if existing and existing["account_id"] != account_id:
            raise ValueError("identity_already_linked")
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO external_identities "
                "(id,account_id,provider,subject,email,display_name,created_at,last_login_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (db.new_uuid(), account_id, provider, subject, email, display_name,
                 time.time(), time.time()),
            )
            db.record_auth_audit(
                action="sso_identity_linked", account_id=account_id, actor_id=account_id,
                provider=provider, details={"subject_hash": _hash(subject)}, conn=conn,
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise ValueError("provider_already_linked") from exc
        except Exception:
            conn.rollback()
            raise
        return account_id
    if existing:
        account = db.get_account(str(existing["account_id"]))
        if not account or account.suspended_at > 0:
            raise ValueError("account_suspended")
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE external_identities SET last_login_at=?,email=?,display_name=? WHERE id=?",
                (time.time(), email, display_name, existing["id"]),
            )
            db.record_auth_audit(
                action="sso_identity_verified", account_id=str(existing["account_id"]),
                actor_id=str(existing["account_id"]), provider=provider, conn=conn,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return str(existing["account_id"])
    if email:
        same_email = conn.execute(
            "SELECT id FROM accounts WHERE lower(email)=? LIMIT 1", (email,)
        ).fetchone()
        if same_email:
            raise ValueError("explicit_link_required")
    policy = settings.SSO_REGISTRATION_POLICY
    if policy == "disabled" or policy == "existing_only":
        raise ValueError("registration_disabled")
    invite = None
    if policy == "invite_only":
        invite_hash = attempt.get("invite_code_hash")
        if not invite_hash:
            raise ValueError("signup_invite_required")
        invite = conn.execute(
            "SELECT * FROM sso_signup_invites WHERE code_hash=? AND consumed_at IS NULL AND expires_at>?",
            (invite_hash, time.time()),
        ).fetchone()
        if not invite:
            raise ValueError("invalid_signup_invite")
    now = time.time()
    account_id = db.new_uuid()
    disabled_password_hash = db.hash_password(secrets.token_urlsafe(48))
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute(
            "SELECT 1 FROM external_identities WHERE provider=? AND subject=?",
            (provider, subject),
        ).fetchone():
            raise ValueError("identity_already_linked")
        if email and conn.execute(
            "SELECT 1 FROM accounts WHERE lower(email)=? LIMIT 1", (email,),
        ).fetchone():
            raise ValueError("explicit_link_required")
        if invite:
            claimed = conn.execute(
                "UPDATE sso_signup_invites SET consumed_by=?,consumed_at=? "
                "WHERE id=? AND consumed_at IS NULL",
                (account_id, now, invite["id"]),
            )
            if claimed.rowcount != 1:
                raise ValueError("invalid_signup_invite")
        first_account = int(conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]) == 0
        conn.execute(
            "INSERT INTO accounts "
            "(id,name,email,plan,password_hash,created_at,is_platform_admin,password_login_enabled) "
            "VALUES (?,?,?,?,?,?,?,0)",
            (account_id, _unique_name(display_name, email, provider), email, "体验版",
             disabled_password_hash, now, int(first_account)),
        )
        db.record_auth_audit(
            action="bootstrap_first_admin" if first_account else "account_registered_sso",
            account_id=account_id, actor_id=account_id,
            provider=provider, details={"email_present": bool(email)}, conn=conn,
        )
        db.record_auth_audit(
            action="sso_identity_linked", account_id=account_id, actor_id=account_id,
            provider=provider, details={"subject_hash": _hash(subject)}, conn=conn,
        )
        conn.execute(
            "INSERT INTO external_identities "
            "(id,account_id,provider,subject,email,display_name,created_at,last_login_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (db.new_uuid(), account_id, provider, subject, email, display_name, now, now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return account_id


def complete_attempt(attempt_id: str, account_id: str) -> None:
    db.get_conn().execute(
        "UPDATE sso_attempts SET status='completed',result_account_id=?,completed_at=? WHERE id=?",
        (account_id, time.time(), attempt_id),
    )
    db.get_conn().commit()


def poll_attempt(attempt_id: str, attempt_token: str) -> dict[str, Any] | None:
    conn = db.get_conn()
    row = conn.execute("SELECT * FROM sso_attempts WHERE id=?", (attempt_id,)).fetchone()
    if not row or not secrets.compare_digest(str(row["attempt_token_hash"]), _hash(attempt_token)):
        return None
    if float(row["expires_at"]) <= time.time():
        return {"status": "expired"}
    if row["status"] == "error":
        return {"status": "error", "error_code": row["error_code"]}
    if row["status"] != "completed":
        return {"status": "pending"}
    conn.execute("BEGIN IMMEDIATE")
    try:
        claimed = conn.execute(
            "UPDATE sso_attempts SET consumed_at=? WHERE id=? AND consumed_at IS NULL",
            (time.time(), attempt_id),
        )
        if claimed.rowcount != 1:
            conn.rollback()
            return {"status": "consumed"}
        token, expires_at = db.create_token(str(row["result_account_id"]), conn=conn)
        db.record_auth_audit(
            action="sso_login", account_id=str(row["result_account_id"]),
            actor_id=str(row["result_account_id"]), provider=str(row["provider"]), conn=conn,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    account = db.get_account(str(row["result_account_id"]))
    return {
        "status": "completed", "token": token, "expires_at": expires_at,
        "account": account.to_dict() if account else None,
    }


def list_identities(account_id: str) -> list[dict[str, Any]]:
    rows = db.get_conn().execute(
        "SELECT provider,email,display_name,created_at,last_login_at FROM external_identities "
        "WHERE account_id=? ORDER BY created_at", (account_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def unlink_identity(account_id: str, provider: str, *, actor_id: str = "") -> bool:
    conn = db.get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        account = conn.execute(
            "SELECT password_login_enabled FROM accounts WHERE id=?", (account_id,)
        ).fetchone()
        if account is None:
            raise ValueError("account_not_found")
        identity = conn.execute(
            "SELECT 1 FROM external_identities WHERE account_id=? AND provider=?",
            (account_id, provider),
        ).fetchone()
        if identity is None:
            conn.rollback()
            return False
        count = int(conn.execute(
            "SELECT COUNT(*) FROM external_identities WHERE account_id=?", (account_id,)
        ).fetchone()[0])
        if not bool(account["password_login_enabled"]) and count <= 1:
            raise ValueError("last_login_method")
        changed = conn.execute(
            "DELETE FROM external_identities WHERE account_id=? AND provider=?",
            (account_id, provider),
        )
        if changed.rowcount == 1:
            db.record_auth_audit(
                action="sso_identity_unlinked", account_id=account_id,
                actor_id=actor_id or account_id, provider=provider, conn=conn,
            )
            db.revoke_account_sessions(
                account_id, actor_id=actor_id or account_id,
                action="identity_unlinked", conn=conn,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return changed.rowcount == 1
