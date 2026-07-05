"""Automation scheduler — fires saved automations on their schedule.

Local-first, single process: a lightweight asyncio loop scans the `automations`
table every SCAN_SECONDS and, for each due + enabled automation, runs its prompt
through the real agent (`run_chat`) headless in a fresh session. Nothing faked —
each fire produces a real LLM session persisted like any other chat.

Runs are driven as background tasks (with a timeout) so one slow/hung automation
never blocks the scan loop or the SSE event loop. An in-flight set prevents the
same automation from overlapping itself.
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from agent import runtime
from storage import db
from storage.models import Automation, LOCAL_USER_ID

SCAN_SECONDS = 20
RUN_TIMEOUT = 300  # a single automation run is cancelled after 5 min

_task: Optional[asyncio.Task] = None
_running: set[str] = set()  # automation ids with a fire in flight (no overlap)


async def _execute(auto: Automation, session) -> None:
    """Drive one automation run to completion in `session`, then record status."""
    user = db.get_user(auto.owner_id) or db.get_user(LOCAL_USER_ID)
    status = "ok"
    if user is None:
        status = "error"
    else:
        try:
            async def _drive() -> None:
                async for _ in runtime.run_chat(session, user, auto.prompt, model=auto.model):
                    pass

            await asyncio.wait_for(_drive(), timeout=RUN_TIMEOUT)
        except Exception:  # noqa: BLE001 — a bad run must not kill the scheduler
            status = "error"
    db.mark_automation_run(
        auto.id, last_run_at=time.time(), last_session_id=session.id, last_status=status
    )


async def _fire_guarded(auto: Automation) -> None:
    try:
        session = db.create_session(
            owner_id=auto.owner_id, title=auto.name[:26], kind="automation",
            project_id=auto.project_id,
        )
        db.mark_automation_run(auto.id, last_session_id=session.id, last_status="running")
        await _execute(auto, session)
    finally:
        _running.discard(auto.id)


async def _loop() -> None:
    while True:
        try:
            now = time.time()
            for auto in db.list_due_automations(now):
                if auto.id in _running:
                    continue
                _running.add(auto.id)
                # Reserve the next slot NOW so the following scan won't re-fire this
                # automation while its run is still in flight.
                nxt = db.compute_next_run(auto.trigger_kind, auto.interval_min, auto.at_time, now)
                db.mark_automation_run(auto.id, next_run_at=nxt)
                asyncio.create_task(_fire_guarded(auto))
        except Exception:  # noqa: BLE001 — never let a scan error stop the loop
            pass
        await asyncio.sleep(SCAN_SECONDS)


async def run_now(auto_id: str) -> Optional[str]:
    """Fire an automation immediately (POST /{id}/run). Returns the new session id
    (created synchronously so the client can link to it); the run itself proceeds
    in the background. Does not disturb the automation's scheduled next_run_at."""
    auto = db.get_automation(auto_id)
    if auto is None:
        return None
    session = db.create_session(
        owner_id=auto.owner_id, title=auto.name[:26], kind="automation",
        project_id=auto.project_id,
    )
    db.mark_automation_run(auto_id, last_session_id=session.id, last_status="running")
    _running.add(auto_id)

    async def _bg() -> None:
        try:
            await _execute(auto, session)
        finally:
            _running.discard(auto_id)

    asyncio.create_task(_bg())
    return session.id


def start() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())


async def stop() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except BaseException:  # noqa: BLE001 — swallow CancelledError on shutdown
            pass
        _task = None
