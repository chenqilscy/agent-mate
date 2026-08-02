"""Unified durable background execution worker (WB-345)."""
from __future__ import annotations

import asyncio
import inspect
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from config import settings
from agent import worker_health
from storage import background_job_store as jobs

log = logging.getLogger("agentmate.background_worker")
Job = dict[str, Any]
AsyncJobHandler = Callable[[Job], Awaitable[None]]
Callback = Callable[[Job], Awaitable[None] | None]


class TerminalJobError(RuntimeError):
    def __init__(self, message: str, *, code: str = "job_failed") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class HandlerSpec:
    run: AsyncJobHandler
    recover: Callback | None = None
    failed: Callback | None = None


_handlers: dict[str, HandlerSpec] = {}
_tasks: dict[str, asyncio.Task[None]] = {}
_loop_task: asyncio.Task[None] | None = None
_worker_id = f"local-{uuid.uuid4()}"
_stopping = False


def register_handler(
    kind: str, run: AsyncJobHandler, *, recover: Callback | None = None,
    failed: Callback | None = None,
) -> None:
    _handlers[kind] = HandlerSpec(run=run, recover=recover, failed=failed)


async def _call(callback: Callback | None, job: Job) -> None:
    if callback is None:
        return
    try:
        result = callback(job)
        if inspect.isawaitable(result):
            await result
    except Exception:  # noqa: BLE001
        log.exception("background job callback failed: kind=%s id=%s", job.get("kind"), job.get("id"))


async def _heartbeat(job_id: str) -> None:
    interval = max(1.0, settings.BACKGROUND_JOB_LEASE_SECONDS / 3)
    while True:
        await asyncio.sleep(interval)
        if not jobs.heartbeat(
            job_id, _worker_id, time.time(), settings.BACKGROUND_JOB_LEASE_SECONDS,
        ):
            return


async def _run_claimed(job: Job) -> None:
    spec = _handlers.get(str(job["kind"]))
    if spec is None:
        failed = jobs.finish_failure(
            job["id"], _worker_id, error_code="handler_missing",
            error_message=f"No background handler registered for {job['kind']}",
            retry_at=time.time(), force_terminal=True,
        )
        if failed:
            await _call(None, failed)
        return
    heartbeat_task = asyncio.create_task(_heartbeat(job["id"]))
    try:
        await spec.run(job)
    except asyncio.CancelledError:
        current = jobs.get(job["id"])
        if current and current["status"] == "running":
            jobs.release(job["id"], _worker_id)
        raise
    except TerminalJobError as exc:
        failed = jobs.finish_failure(
            job["id"], _worker_id, error_code=exc.code, error_message=str(exc),
            retry_at=time.time(), force_terminal=True,
        )
        if failed:
            await _call(spec.failed, failed)
    except Exception as exc:  # noqa: BLE001
        delay = settings.BACKGROUND_JOB_RETRY_BACKOFF_SECONDS * (2 ** max(0, int(job["attempt"]) - 1))
        failed = jobs.finish_failure(
            job["id"], _worker_id, error_code="handler_error", error_message=str(exc),
            retry_at=time.time() + delay,
        )
        if failed and failed["status"] == "failed":
            await _call(spec.failed, failed)
    else:
        jobs.finish_success(job["id"], _worker_id)
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)


async def _guard(job_id: str) -> None:
    try:
        claimed = jobs.claim(
            job_id, _worker_id, time.time(), settings.BACKGROUND_JOB_LEASE_SECONDS,
        )
        if claimed:
            await _run_claimed(claimed)
    finally:
        _tasks.pop(job_id, None)


def _launch(job_id: str) -> asyncio.Task[None] | None:
    existing = _tasks.get(job_id)
    if existing and not existing.done():
        return existing
    if _stopping or len(_tasks) >= settings.BACKGROUND_JOB_MAX_CONCURRENCY:
        return None
    task = asyncio.create_task(_guard(job_id))
    _tasks[job_id] = task
    return task


def enqueue(
    *, owner_id: str, kind: str, entity_id: str, idempotency_key: str,
    payload: dict[str, Any] | None = None, max_attempts: int = 3,
) -> tuple[Job, bool, asyncio.Task[None] | None]:
    job, created = jobs.enqueue(
        owner_id=owner_id, kind=kind, entity_id=entity_id,
        idempotency_key=idempotency_key, payload=payload, max_attempts=max_attempts,
    )
    task = _launch(job["id"]) if job.get("status") in {"queued", "retry_wait"} else _tasks.get(job["id"])
    return job, created, task


def task_for_entity(owner_id: str, kind: str, entity_id: str) -> asyncio.Task[None] | None:
    job = jobs.get_for_entity(owner_id, kind, entity_id)
    return _tasks.get(job["id"]) if job else None


def cancel_entity(owner_id: str, kind: str, entity_id: str) -> asyncio.Task[None] | None:
    job = jobs.get_for_entity(owner_id, kind, entity_id)
    if not job:
        return None
    jobs.cancel(job["id"])
    task = _tasks.get(job["id"])
    if task and not task.done():
        task.cancel()
    return task


async def scan_once(now: float | None = None) -> None:
    current = time.time() if now is None else float(now)
    for recovered in jobs.recover_expired(current):
        if recovered["status"] == "failed":
            spec = _handlers.get(str(recovered["kind"]))
            await _call(spec.failed if spec else None, recovered)
    slots = max(0, settings.BACKGROUND_JOB_MAX_CONCURRENCY - len(_tasks))
    if slots:
        for job in jobs.list_due(current, slots):
            _launch(job["id"])


async def _scan_tick() -> None:
    try:
        await scan_once()
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        worker_health.record_failure("background_worker.scan", exc)
        log.exception("background job scan failed")
    else:
        worker_health.record_success("background_worker.scan")


async def _loop() -> None:
    while True:
        await _scan_tick()
        await asyncio.sleep(settings.BACKGROUND_JOB_SCAN_SECONDS)


async def start() -> None:
    global _loop_task, _stopping
    if _loop_task and not _loop_task.done():
        return
    _stopping = False
    jobs.ensure_tables()
    for spec in list(_handlers.values()):
        await _call(spec.recover, {})
    await _scan_tick()
    _loop_task = asyncio.create_task(_loop())


async def stop() -> None:
    global _loop_task, _stopping
    _stopping = True
    loop_task, _loop_task = _loop_task, None
    if loop_task:
        loop_task.cancel()
        await asyncio.gather(loop_task, return_exceptions=True)
    active = list(_tasks.values())
    for task in active:
        task.cancel()
    if active:
        await asyncio.gather(*active, return_exceptions=True)
    _tasks.clear()
    _stopping = False
