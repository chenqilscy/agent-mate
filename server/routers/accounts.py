"""平台用户管理（WB-163）—— 平台管理员维护全部账号。

Console（Server）是账号权威源；此路由让平台管理员在管理端做账号 CRUD：列表 / 建 / 改
（名/邮箱/套餐/管理员）/ 重置密码 / 删。全部 `is_platform_admin` 门禁（同 settings.py）。
绝不回传 password_hash（铁律#4）。守卫：不能删自己 / 最后一个平台管理员 / 仍拥有项目的账号。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db
import sso_store
from auth import CurrentAccount
from models import Account

router = APIRouter(prefix="/api", tags=["accounts"])


def _require_admin(account: Account) -> None:
    if not account.is_platform_admin:
        raise HTTPException(403, "platform admin only")


@router.get("/accounts")
def list_accounts(account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    return {"accounts": db.list_accounts()}


class CreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=12, max_length=200)
    email: str = Field(default="", max_length=120)
    plan: str = Field(default="体验版", max_length=40)
    is_platform_admin: bool = False


@router.post("/accounts")
def create_account(body: CreateBody, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "empty name")
    if db.find_account_by_name(name):
        raise HTTPException(409, "name already taken")
    acc = db.create_account(
        name=name, password=body.password, email=body.email.strip(),
        plan=body.plan.strip() or "体验版", is_platform_admin=body.is_platform_admin,
    )
    db.record_auth_audit(
        action="account_created", account_id=acc.id, actor_id=account.id,
        details={"platform_admin": body.is_platform_admin},
    )
    return {"account": db.get_account_admin_view(acc.id)}


class UpdateBody(BaseModel):
    name: str | None = Field(default=None, max_length=60)
    email: str | None = Field(default=None, max_length=120)
    plan: str | None = Field(default=None, max_length=40)
    is_platform_admin: bool | None = None


@router.patch("/accounts/{account_id}")
def update_account(account_id: str, body: UpdateBody, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    target = db.get_account(account_id)
    if target is None:
        raise HTTPException(404, "account not found")
    name = body.name.strip() if body.name is not None else None
    if name is not None:
        if not name:
            raise HTTPException(400, "empty name")
        clash = db.find_account_by_name(name)
        if clash and clash.id != account_id:
            raise HTTPException(409, "name already taken")
    try:
        db.update_account(
            account_id, name=name, email=body.email, plan=body.plan,
            is_platform_admin=body.is_platform_admin, actor_id=account.id,
        )
    except ValueError as exc:
        if str(exc) == "last_platform_admin":
            raise HTTPException(409, "不能撤销最后一个平台管理员") from exc
        raise
    return {"account": db.get_account_admin_view(account_id)}


class PasswordBody(BaseModel):
    password: str = Field(min_length=12, max_length=200)


@router.post("/accounts/{account_id}/password")
def reset_password(account_id: str, body: PasswordBody, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    if db.get_account(account_id) is None:
        raise HTTPException(404, "account not found")
    db.set_account_password(account_id, body.password, actor_id=account.id)
    return {"ok": True}


class PasswordLoginBody(BaseModel):
    enabled: bool


@router.put("/accounts/{account_id}/password-login")
def password_login(
    account_id: str, body: PasswordLoginBody, account: Account = CurrentAccount,
) -> dict:
    _require_admin(account)
    if db.get_account(account_id) is None:
        raise HTTPException(404, "account not found")
    try:
        db.set_password_login_enabled(account_id, body.enabled, actor_id=account.id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"account": db.get_account_admin_view(account_id)}


class SuspensionBody(BaseModel):
    suspended: bool


@router.put("/accounts/{account_id}/suspension")
def suspension(
    account_id: str, body: SuspensionBody, account: Account = CurrentAccount,
) -> dict:
    _require_admin(account)
    target = db.get_account(account_id)
    if target is None:
        raise HTTPException(404, "account not found")
    try:
        db.set_account_suspended(account_id, body.suspended, actor_id=account.id)
    except ValueError as exc:
        detail = {
            "cannot_suspend_self": "不能暂停自己",
            "last_platform_admin": "不能暂停最后一个平台管理员",
        }.get(str(exc))
        if detail:
            raise HTTPException(409, detail) from exc
        raise
    return {"account": db.get_account_admin_view(account_id)}


@router.post("/accounts/{account_id}/sessions/revoke")
def revoke_sessions(account_id: str, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    if db.get_account(account_id) is None:
        raise HTTPException(404, "account not found")
    return {"revoked": db.revoke_account_sessions(account_id, actor_id=account.id)}


@router.get("/accounts/{account_id}/identities")
def account_identities(account_id: str, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    if db.get_account(account_id) is None:
        raise HTTPException(404, "account not found")
    return {"identities": db.list_account_identities(account_id)}


@router.delete("/accounts/{account_id}/identities/{provider}")
def unlink_account_identity(
    account_id: str, provider: str, account: Account = CurrentAccount,
) -> dict:
    _require_admin(account)
    try:
        removed = sso_store.unlink_identity(account_id, provider, actor_id=account.id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not removed:
        raise HTTPException(404, "identity not found")
    return {"ok": True}


@router.get("/accounts/auth-audit")
def auth_audit(
    account_id: str = "", limit: int = 100, account: Account = CurrentAccount,
) -> dict:
    _require_admin(account)
    return {"audit": db.list_auth_audit(limit=limit, account_id=account_id)}


@router.delete("/accounts/{account_id}")
def delete_account(account_id: str, account: Account = CurrentAccount) -> dict:
    _require_admin(account)
    target = db.get_account(account_id)
    if target is None:
        raise HTTPException(404, "account not found")
    try:
        db.delete_account(account_id, actor_id=account.id)
    except ValueError as exc:
        code = str(exc)
        detail = {
            "cannot_delete_self": "不能删除自己",
            "last_platform_admin": "不能删除最后一个平台管理员",
        }.get(code)
        if code.startswith("account_owns_projects:"):
            detail = f"该账号仍拥有 {code.partition(':')[2]} 个项目，请先移交或删除后再删账号"
        elif code.startswith("account_owns_orgs:"):
            detail = f"该账号仍拥有 {code.partition(':')[2]} 个组织，请先移交或删除后再删账号"
        if detail:
            raise HTTPException(409, detail) from exc
        raise
    return {"ok": True}
