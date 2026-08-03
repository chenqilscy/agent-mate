"""账号鉴权（WB-061）：注册 / 登录 / 登出 / 我，以及 token 校验端点（供本地 backend 客户端调用）。"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

import db
import sso_store
from auth import CurrentAccount, bearer_token
from config import settings
from models import Account

router = APIRouter(prefix="/api", tags=["auth"])


@router.get("/auth/capabilities")
def capabilities() -> dict:
    return {
        "password_registration": settings.SSO_REGISTRATION_POLICY == "open",
        "registration_policy": settings.SSO_REGISTRATION_POLICY,
        "min_password_length": settings.MIN_PASSWORD_LENGTH,
        "bootstrap_available": bool(settings.BOOTSTRAP_ADMIN_SECRET) and db.count_accounts() == 0,
    }


class RegisterBody(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=12, max_length=200)
    email: str = Field(default="", max_length=120)


class LoginBody(BaseModel):
    name: str
    password: str


def _validate_password(password: str) -> None:
    if len(password) < settings.MIN_PASSWORD_LENGTH:
        raise HTTPException(400, f"password must be at least {settings.MIN_PASSWORD_LENGTH} characters")


@router.post("/auth/register")
def register(body: RegisterBody, request: Request) -> dict:
    ip = request.client.host if request.client else "unknown"
    if not sso_store.check_rate_limit(f"register:{ip}"):
        raise HTTPException(429, "too_many_attempts")
    if settings.SSO_REGISTRATION_POLICY != "open":
        raise HTTPException(403, "password_registration_disabled")
    _validate_password(body.password)
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "empty name")
    if db.find_account_by_name(name):
        raise HTTPException(409, "name already taken")
    acc = db.create_account(
        name=name, password=body.password, email=body.email.strip(),
        is_platform_admin=False,
    )
    db.record_auth_audit(action="password_registered", account_id=acc.id, actor_id=acc.id)
    token, expires_at = db.create_token(acc.id)
    return {"token": token, "expires_at": expires_at, "account": acc.to_dict()}


class BootstrapBody(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=12, max_length=200)
    email: str = Field(default="", max_length=120)
    bootstrap_secret: str = Field(min_length=1, max_length=1000)


@router.post("/auth/bootstrap")
def bootstrap(body: BootstrapBody, request: Request) -> dict:
    ip = request.client.host if request.client else "unknown"
    if not sso_store.check_rate_limit(f"bootstrap:{ip}"):
        raise HTTPException(429, "too_many_attempts")
    configured = settings.BOOTSTRAP_ADMIN_SECRET
    if not configured or not secrets.compare_digest(body.bootstrap_secret, configured):
        raise HTTPException(403, "bootstrap_unavailable")
    _validate_password(body.password)
    try:
        account = db.bootstrap_admin(
            name=body.name.strip(), password=body.password, email=body.email.strip(),
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    token, expires_at = db.create_token(account.id)
    return {"token": token, "expires_at": expires_at, "account": account.to_dict()}


@router.post("/auth/login")
def login(body: LoginBody, request: Request) -> dict:
    name = (body.name or "").strip()
    ip = request.client.host if request.client else "unknown"
    if not sso_store.check_rate_limit(f"login:{ip}:{name.lower()}"):
        raise HTTPException(429, "too_many_attempts")
    rec = db.get_account_by_name(name)
    if not rec or not db.verify_password(body.password, rec[1]):
        raise HTTPException(401, "invalid credentials")
    if db.password_needs_rehash(rec[1]):
        db.upgrade_password_hash(rec[0].id, body.password)
    token, expires_at = db.create_token(rec[0].id)
    db.record_auth_audit(action="password_login", account_id=rec[0].id, actor_id=rec[0].id)
    return {"token": token, "expires_at": expires_at, "account": rec[0].to_dict()}


@router.post("/auth/logout")
def logout(authorization: str = Header(default="")) -> dict:
    tok = bearer_token(authorization)
    if tok:
        account_id = db.account_id_for_token(tok) or ""
        db.delete_token(tok)
        if account_id:
            db.record_auth_audit(action="logout", account_id=account_id, actor_id=account_id)
    return {"ok": True}


@router.get("/me")
def me(account: Account = CurrentAccount) -> dict:
    return {"account": account.to_dict()}


@router.get("/auth/verify")
def verify(authorization: str = Header(default=""), account: Account = CurrentAccount) -> dict:
    """token → account。本地 backend 作为客户端持 Server token 调此端点解析出账号（WB-062 会用）。"""
    expires_at = db.token_expires_at(bearer_token(authorization))
    if expires_at is None:
        raise HTTPException(401, "unauthorized")
    return {"account": account.to_dict(), "expires_at": expires_at}
