"""账号鉴权（WB-061）：注册 / 登录 / 登出 / 我，以及 token 校验端点（供本地 backend 客户端调用）。"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

import db
from auth import CurrentAccount, bearer_token
from models import Account

router = APIRouter(prefix="/api", tags=["auth"])


class RegisterBody(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=4, max_length=200)
    email: str = Field(default="", max_length=120)


class LoginBody(BaseModel):
    name: str
    password: str


@router.post("/auth/register")
def register(body: RegisterBody) -> dict:
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "empty name")
    if db.find_account_by_name(name):
        raise HTTPException(409, "name already taken")
    acc = db.create_account(name=name, password=body.password, email=body.email.strip())
    token, expires_at = db.create_token(acc.id)
    return {"token": token, "expires_at": expires_at, "account": acc.to_dict()}


@router.post("/auth/login")
def login(body: LoginBody) -> dict:
    rec = db.get_account_by_name((body.name or "").strip())
    if not rec or not db.verify_password(body.password, rec[1]):
        raise HTTPException(401, "invalid credentials")
    token, expires_at = db.create_token(rec[0].id)
    return {"token": token, "expires_at": expires_at, "account": rec[0].to_dict()}


@router.post("/auth/logout")
def logout(authorization: str = Header(default="")) -> dict:
    tok = bearer_token(authorization)
    if tok:
        db.delete_token(tok)
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
