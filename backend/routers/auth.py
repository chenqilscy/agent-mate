"""Accounts / auth (M7 C1). Register + login return a Bearer token the frontend
sends on every request; the AuthMiddleware resolves it to the current user. No
token → the fixed local owner, so nothing breaks without logging in."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from storage import db
from storage.models import Role

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterBody(BaseModel):
    name: str
    password: str


class LoginBody(BaseModel):
    name: str
    password: str


def _user_view(user) -> dict:
    return {"id": user.id, "name": user.name, "role": user.role.value, "plan": user.plan}


@router.post("/register")
def register(body: RegisterBody) -> dict:
    name = (body.name or "").strip()
    if not name or not body.password:
        raise HTTPException(400, "用户名和密码必填")
    if len(body.password) < 4:
        raise HTTPException(400, "密码至少 4 位")
    if db.get_user_by_name(name) is not None:
        raise HTTPException(409, "该用户名已被占用")
    user = db.create_user(name=name, password=body.password, role=Role.OWNER)
    return {"token": db.create_token(user.id), "user": _user_view(user)}


@router.post("/login")
def login(body: LoginBody) -> dict:
    found = db.get_user_by_name((body.name or "").strip())
    if found is None or not db.verify_password(body.password or "", found[1]):
        raise HTTPException(401, "用户名或密码错误")
    user = found[0]
    return {"token": db.create_token(user.id), "user": _user_view(user)}


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)) -> dict:
    if authorization and authorization[:7].lower() == "bearer ":
        db.delete_token(authorization[7:].strip())
    return {"ok": True}
