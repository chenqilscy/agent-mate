"""Federated login broker, account linking and provider administration (WB-362)."""
from __future__ import annotations

import html

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

import db
import sso_protocol
import sso_store
import secret_crypto
from auth import CurrentAccount, bearer_token
from console_session import console_auth_payload, wants_console_session
from models import Account

router = APIRouter(prefix="/api", tags=["sso"])


def _optional_account(authorization: str) -> Account | None:
    token = bearer_token(authorization)
    account_id = db.account_id_for_token(token) if token else None
    return db.get_account(account_id) if account_id else None


def _admin(account: Account) -> None:
    if not account.is_platform_admin:
        raise HTTPException(403, "platform admin only")


@router.get("/auth/sso/providers")
def providers() -> dict:
    return {"providers": sso_store.public_providers()}


@router.get("/admin/sso/providers")
def admin_providers(account: Account = CurrentAccount) -> dict:
    _admin(account)
    return {"providers": sso_store.admin_providers()}


@router.get("/admin/sso/audit")
def provider_audit(limit: int = 100, account: Account = CurrentAccount) -> dict:
    _admin(account)
    return {"audit": sso_store.list_provider_audit(limit)}


@router.get("/admin/sso/readiness")
def readiness(account: Account = CurrentAccount) -> dict:
    _admin(account)
    return sso_store.provider_readiness()


@router.post("/admin/sso/rotate-encryption")
def rotate_encryption(account: Account = CurrentAccount) -> dict:
    _admin(account)
    try:
        changed = sso_store.migrate_plaintext_provider_secrets()
    except (ValueError, secret_crypto.SecretKeyUnavailable) as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"rotated": changed, "key_id": secret_crypto.current_key_id()}


class ProviderBody(BaseModel):
    enabled: bool = False
    client_id: str = Field(default="", max_length=300)
    client_secret: str | None = Field(default=None, max_length=1000)


@router.put("/admin/sso/providers/{provider}")
def update_provider(provider: str, body: ProviderBody, account: Account = CurrentAccount) -> dict:
    _admin(account)
    try:
        item = sso_store.set_provider(
            provider, enabled=body.enabled, client_id=body.client_id,
            client_secret=body.client_secret, updated_by=account.id,
        )
    except (ValueError, secret_crypto.SecretKeyUnavailable) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"provider": item}


class InviteBody(BaseModel):
    ttl_seconds: int = Field(default=86400, ge=60, le=2592000)


@router.post("/admin/sso/signup-invites")
def create_signup_invite(body: InviteBody, account: Account = CurrentAccount) -> dict:
    _admin(account)
    item, code = sso_store.create_signup_invite(account.id, body.ttl_seconds)
    return {"invite": item, "code": code}


class StartBody(BaseModel):
    provider: str
    mode: str = "login"
    invite_code: str = Field(default="", max_length=300)


@router.post("/auth/sso/start")
def start_sso(
    body: StartBody, request: Request, authorization: str = Header(default=""),
) -> dict:
    account = _optional_account(authorization)
    if body.mode not in ("login", "link"):
        raise HTTPException(400, "invalid_mode")
    if body.mode == "link" and not account:
        raise HTTPException(401, "authentication_required")
    ip = request.client.host if request.client else "unknown"
    if not sso_store.check_rate_limit(f"sso-start:{ip}"):
        raise HTTPException(429, "too_many_attempts")
    try:
        config = sso_store.provider_config(body.provider)
    except (ValueError, secret_crypto.SecretKeyUnavailable) as exc:
        raise HTTPException(503, "provider_secret_unavailable") from exc
    if not config or not config.get("enabled") or not config.get("client_id") or not config.get("client_secret"):
        raise HTTPException(404, "provider_unavailable")
    attempt, state, attempt_token = sso_store.create_attempt(
        body.provider, mode=body.mode, account_id=account.id if account else None,
        invite_code=body.invite_code,
    )
    return {
        "attempt_id": attempt["id"], "attempt_token": attempt_token,
        "auth_url": sso_protocol.authorization_url(body.provider, config, attempt, state),
        "expires_at": attempt["expires_at"],
    }


@router.get("/auth/sso/{provider}/callback", response_class=HTMLResponse)
def callback(
    provider: str, state: str = Query(default=""), code: str = Query(default=""),
    error: str = Query(default=""),
) -> str:
    attempt = sso_store.consume_state(provider, state)
    if not attempt:
        raise HTTPException(400, "invalid_or_replayed_state")
    try:
        if error or not code:
            raise ValueError("provider_denied")
        config = sso_store.provider_config(provider)
        if not config or not config.get("enabled"):
            raise ValueError("provider_unavailable")
        identity = sso_protocol.exchange_identity(provider, config, attempt, code)
        account_id = sso_store.resolve_identity(attempt, identity)
        sso_store.complete_attempt(str(attempt["id"]), account_id)
        title = "登录成功"
        message = "身份已验证，可以关闭此窗口并返回 AgentMate。"
    except Exception as exc:  # provider/network/identity failures all fail closed
        code_name = str(exc) if isinstance(exc, ValueError) else "provider_exchange_failed"
        sso_store.fail_attempt(str(attempt["id"]), code_name)
        title = "登录未完成"
        message = "身份验证失败，请返回 AgentMate 后重试。"
    return (
        "<!doctype html><meta charset='utf-8'><title>AgentMate SSO</title>"
        "<body style='font-family:system-ui;padding:48px;max-width:620px;margin:auto'>"
        f"<h1>{html.escape(title)}</h1><p>{html.escape(message)}</p></body>"
    )


class PollBody(BaseModel):
    attempt_id: str
    attempt_token: str


@router.post("/auth/sso/poll")
def poll_sso(body: PollBody, request: Request, response: Response) -> dict:
    result = sso_store.poll_attempt(body.attempt_id, body.attempt_token)
    if result is None:
        raise HTTPException(401, "invalid_attempt")
    if result["status"] in ("expired", "consumed"):
        raise HTTPException(409, result["status"])
    if result.get("status") == "completed" and wants_console_session(request):
        return {
            "status": "completed",
            **console_auth_payload(
                request,
                response,
                token=str(result["token"]),
                expires_at=float(result["expires_at"]),
                account=result["account"],
            ),
        }
    return result


@router.get("/auth/identities")
def identities(account: Account = CurrentAccount) -> dict:
    return {"identities": sso_store.list_identities(account.id)}


@router.delete("/auth/identities/{provider}")
def unlink(provider: str, account: Account = CurrentAccount) -> dict:
    try:
        removed = sso_store.unlink_identity(account.id, provider, actor_id=account.id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not removed:
        raise HTTPException(404, "identity_not_found")
    return {"ok": True}
