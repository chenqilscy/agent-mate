"""Shared process-wide admission control for background Agent/LLM executions."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from config import settings

_condition: asyncio.Condition | None = None
_condition_loop: asyncio.AbstractEventLoop | None = None
_active = 0
_waiting = 0
_per_owner: dict[str, int] = {}


@asynccontextmanager
async def slot(owner_id: str) -> AsyncIterator[None]:
    """Wait for both the global and owner quota; cancellation never leaks a slot."""
    global _active, _waiting
    owner = owner_id or "anonymous"
    admitted = False
    condition = _get_condition()
    async with condition:
        _waiting += 1
        try:
            await condition.wait_for(lambda: (
                _active < settings.BACKGROUND_AGENT_MAX_CONCURRENCY
                and _per_owner.get(owner, 0) < settings.BACKGROUND_AGENT_PER_OWNER_CONCURRENCY
            ))
            _active += 1
            _per_owner[owner] = _per_owner.get(owner, 0) + 1
            admitted = True
        finally:
            _waiting -= 1
    try:
        yield
    finally:
        if admitted:
            async with condition:
                _active -= 1
                remaining = _per_owner.get(owner, 0) - 1
                if remaining > 0:
                    _per_owner[owner] = remaining
                else:
                    _per_owner.pop(owner, None)
                condition.notify_all()


def _get_condition() -> asyncio.Condition:
    global _condition, _condition_loop
    loop = asyncio.get_running_loop()
    if _condition is None or (_condition_loop is not loop and _active == 0 and _waiting == 0):
        _condition = asyncio.Condition()
        _condition_loop = loop
    return _condition


def snapshot() -> dict:
    return {
        "active": _active,
        "waiting": _waiting,
        "max_concurrency": settings.BACKGROUND_AGENT_MAX_CONCURRENCY,
        "per_owner_max_concurrency": settings.BACKGROUND_AGENT_PER_OWNER_CONCURRENCY,
        "owners": dict(_per_owner),
    }
