"""Durable background job lease, retry and shutdown regression (WB-345)."""
from __future__ import annotations

import asyncio
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

from agent import background_worker
from config import settings
from storage import background_job_store as jobs, db
from storage.models import LOCAL_USER_ID


class BackgroundJobStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "agentmate.db"
        db._local = threading.local()
        db.init_db()
        jobs.ensure_tables()

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_db
        db._local = threading.local()
        self.tmp.cleanup()

    def test_idempotency_is_owner_and_kind_scoped(self) -> None:
        other = db.create_user(name="job-owner", password="pw")
        first, created = jobs.enqueue(
            owner_id=LOCAL_USER_ID, kind="test", entity_id="entity-1",
            idempotency_key="stable", payload={"safe": True},
        )
        replay, duplicate = jobs.enqueue(
            owner_id=LOCAL_USER_ID, kind="test", entity_id="entity-2",
            idempotency_key="stable", payload={"safe": False},
        )
        isolated, isolated_created = jobs.enqueue(
            owner_id=other.id, kind="test", entity_id="entity-1",
            idempotency_key="stable", payload={},
        )
        self.assertTrue(created)
        self.assertFalse(duplicate)
        self.assertEqual(first["id"], replay["id"])
        self.assertTrue(replay["payload"]["safe"])
        self.assertTrue(isolated_created)
        self.assertNotEqual(first["id"], isolated["id"])

    def test_expired_lease_retries_then_reaches_bounded_failure(self) -> None:
        job, _ = jobs.enqueue(
            owner_id=LOCAL_USER_ID, kind="lease", entity_id="entity",
            idempotency_key="lease", max_attempts=2,
        )
        base = time.time() + 1
        first = jobs.claim(job["id"], "old-worker", base, 5.0)
        self.assertEqual(1, first["attempt"])
        self.assertTrue(jobs.heartbeat(job["id"], "old-worker", base + 2, 5.0))
        self.assertEqual([], jobs.recover_expired(base + 6))
        recovered = jobs.recover_expired(base + 8)[0]
        self.assertEqual("retry_wait", recovered["status"])
        second = jobs.claim(job["id"], "new-worker", base + 8, 5.0)
        self.assertEqual(2, second["attempt"])
        failed = jobs.recover_expired(base + 14)[0]
        self.assertEqual("failed", failed["status"])
        self.assertEqual("worker_restarted", failed["error_code"])


class BackgroundWorkerExecutionTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_scan = settings.BACKGROUND_JOB_SCAN_SECONDS
        self.old_backoff = settings.BACKGROUND_JOB_RETRY_BACKOFF_SECONDS
        settings.DB_PATH = Path(self.tmp.name) / "agentmate.db"
        settings.BACKGROUND_JOB_SCAN_SECONDS = 60
        settings.BACKGROUND_JOB_RETRY_BACKOFF_SECONDS = 0.1
        db._local = threading.local()
        db.init_db()
        jobs.ensure_tables()
        await background_worker.stop()
        await background_worker.start()

    async def asyncTearDown(self) -> None:
        await background_worker.stop()
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_db
        settings.BACKGROUND_JOB_SCAN_SECONDS = self.old_scan
        settings.BACKGROUND_JOB_RETRY_BACKOFF_SECONDS = self.old_backoff
        db._local = threading.local()
        self.tmp.cleanup()

    async def test_handler_retry_converges_to_success(self) -> None:
        kind = f"test-retry-{uuid.uuid4()}"
        attempts: list[int] = []

        async def handler(job: dict) -> None:
            attempts.append(int(job["attempt"]))
            if len(attempts) == 1:
                raise RuntimeError("temporary")

        background_worker.register_handler(kind, handler)
        job, created, task = background_worker.enqueue(
            owner_id=LOCAL_USER_ID, kind=kind, entity_id="entity",
            idempotency_key="retry", max_attempts=2,
        )
        self.assertTrue(created)
        self.assertIsNotNone(task)
        await task
        self.assertEqual("retry_wait", jobs.get(job["id"])["status"])
        await asyncio.sleep(0.12)
        await background_worker.scan_once()
        retry_task = background_worker._tasks[job["id"]]
        await retry_task
        self.assertEqual([1, 2], attempts)
        self.assertEqual("succeeded", jobs.get(job["id"])["status"])

    async def test_controlled_shutdown_requeues_without_consuming_attempt(self) -> None:
        kind = f"test-shutdown-{uuid.uuid4()}"
        started = asyncio.Event()
        blocker = asyncio.Event()

        async def handler(_job: dict) -> None:
            started.set()
            await blocker.wait()

        background_worker.register_handler(kind, handler)
        job, _, _ = background_worker.enqueue(
            owner_id=LOCAL_USER_ID, kind=kind, entity_id="entity",
            idempotency_key="shutdown", max_attempts=2,
        )
        await asyncio.wait_for(started.wait(), 1)
        self.assertEqual(1, jobs.get(job["id"])["attempt"])
        await background_worker.stop()
        released = jobs.get(job["id"])
        self.assertEqual("queued", released["status"])
        self.assertEqual(0, released["attempt"])
        self.assertEqual("worker_stopped", released["error_code"])


if __name__ == "__main__":
    unittest.main()
