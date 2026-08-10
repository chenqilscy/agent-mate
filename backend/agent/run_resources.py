"""Per-Run resource arbitration for concurrent Server Run execution.

Only Server-owned Runs bind a context. Interactive local chats keep their
existing behavior. Locks are acquired at tool-call boundaries so read-only
work can overlap while shared mutable resources remain serialized.
"""
from __future__ import annotations

import asyncio
import contextvars
import threading
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Iterator


@dataclass(frozen=True)
class RunResourceContext:
    run_id: str
    owner_id: str
    workspace_key: str


_current: contextvars.ContextVar[RunResourceContext | None] = contextvars.ContextVar(
    "server_run_resource_context", default=None,
)
_locks: dict[tuple[int, str], asyncio.Lock] = {}
_state_guard = threading.Lock()
_waiting: dict[str, set[str]] = {}
_holding: dict[str, set[str]] = {}


@contextmanager
def bind(*, run_id: str, owner_id: str, workspace_key: str) -> Iterator[None]:
    token = _current.set(RunResourceContext(
        run_id=run_id, owner_id=owner_id, workspace_key=workspace_key,
    ))
    try:
        yield
    finally:
        _current.reset(token)
        with _state_guard:
            _waiting.pop(run_id, None)
            _holding.pop(run_id, None)


def _resource_keys(context: RunResourceContext, permissions: tuple[str, ...] | list[str]) -> list[str]:
    declared = set(permissions)
    keys: set[str] = set()
    if any(permission.endswith((".write", ".manage")) for permission in declared):
        keys.add(f"workspace:{context.owner_id}:{context.workspace_key}")
    if "browser.state" in declared:
        keys.add(f"browser-profile:{context.owner_id}")
    if "host.unrestricted" in declared:
        keys.add("host:unrestricted")
    return sorted(keys)


def _lock(key: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    identity = (id(loop), key)
    lock = _locks.get(identity)
    if lock is None:
        lock = asyncio.Lock()
        _locks[identity] = lock
    return lock


def _set_state(run_id: str, target: dict[str, set[str]], key: str, present: bool) -> None:
    with _state_guard:
        values = target.setdefault(run_id, set())
        if present:
            values.add(key)
        else:
            values.discard(key)
            if not values:
                target.pop(run_id, None)


@asynccontextmanager
async def acquire(permissions: tuple[str, ...] | list[str]) -> AsyncIterator[None]:
    context = _current.get()
    if context is None:
        yield
        return
    acquired: list[tuple[str, asyncio.Lock]] = []
    try:
        for key in _resource_keys(context, permissions):
            lock = _lock(key)
            if lock.locked():
                _set_state(context.run_id, _waiting, key, True)
            try:
                await lock.acquire()
            finally:
                _set_state(context.run_id, _waiting, key, False)
            acquired.append((key, lock))
            _set_state(context.run_id, _holding, key, True)
        yield
    finally:
        for key, lock in reversed(acquired):
            _set_state(context.run_id, _holding, key, False)
            lock.release()


def snapshot(owner_id: str | None = None) -> dict[str, list[dict[str, object]]]:
    context = _current.get()
    del context  # snapshots are process-wide, not caller-context specific
    with _state_guard:
        waiting = {run_id: sorted(keys) for run_id, keys in _waiting.items()}
        holding = {run_id: sorted(keys) for run_id, keys in _holding.items()}
    # Run ownership is applied by the worker snapshot before exposing this data.
    return {
        "waiting": [{"run_id": run_id, "resources": keys} for run_id, keys in sorted(waiting.items())],
        "holding": [{"run_id": run_id, "resources": keys} for run_id, keys in sorted(holding.items())],
    }
