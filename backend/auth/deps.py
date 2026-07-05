"""Auth dependency.

M1: injects the fixed local user (single-machine mode). M7: swap this one
function for a real token/SSO resolver — every route depends on `current_user`,
so the routes themselves never change (decision A.3).
"""
from __future__ import annotations

from fastapi import Depends

from storage import db
from storage.models import LOCAL_USER_ID, User


def current_user() -> User:
    user = db.get_user(LOCAL_USER_ID)
    if user is None:  # DB not yet initialised in an odd startup order
        db.init_db()
        user = db.get_user(LOCAL_USER_ID)
    assert user is not None
    return user


CurrentUser = Depends(current_user)
