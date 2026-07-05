"""Auth dependency (M7 C1: real accounts on a shared backend).

`current_user()` resolves the request's Bearer token to a user, set per request by
the ASGI AuthMiddleware into a contextvar. No token → the fixed local owner, so
single-machine use keeps working without logging in. Routes never change — they
just call `current_user()` (decision A.3).
"""
from __future__ import annotations

from contextvars import ContextVar

from fastapi import Depends

from storage import db
from storage.models import LOCAL_USER_ID, User

# Set by AuthMiddleware for the duration of each request (None → local owner).
_current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)


def resolve_token_to_user_id(token: str | None) -> str | None:
    """A Bearer token → its user id, or None (→ local-owner fallback)."""
    return db.user_id_for_token(token) if token else None


def set_current_user_id(user_id: str | None) -> None:
    _current_user_id.set(user_id)


def current_user() -> User:
    uid = _current_user_id.get() or LOCAL_USER_ID
    user = db.get_user(uid)
    if user is None:
        # Token pointed at a since-deleted user, or the DB wasn't initialised yet.
        db.init_db()
        user = db.get_user(LOCAL_USER_ID)
    assert user is not None
    return user


CurrentUser = Depends(current_user)
