"""Recurring worker health and recovery visibility (WB-359)."""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch, PropertyMock

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import background_worker, scheduler, worker_health  # noqa: E402
from config import settings  # noqa: E402
from storage import background_job_store as jobs, db  # noqa: E402


class BackgroundLoopHealthTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        worker_health.reset_for_tests()

    async def test_scheduler_failure_is_logged_and_next_success_recovers(self) -> None:
        with (
            patch.object(type(settings), "server_enabled", new_callable=PropertyMock, return_value=False),
            patch.object(scheduler, "_scan_once", AsyncMock(side_effect=OSError("db offline"))),
            self.assertLogs("agentmate.scheduler", level="ERROR") as captured,
        ):
            await scheduler._tick()
        failed = worker_health.snapshot()
        component = failed["components"][0]
        self.assertFalse(failed["healthy"])
        self.assertEqual(1, component["consecutive_failures"])
        self.assertIn("OSError: db offline", component["last_error"])
        self.assertTrue(any("automation_scheduler.scan" in line for line in captured.output))

        with (
            patch.object(type(settings), "server_enabled", new_callable=PropertyMock, return_value=False),
            patch.object(scheduler, "_scan_once", AsyncMock()),
        ):
            await scheduler._tick()
        recovered = worker_health.snapshot()["components"][0]
        self.assertEqual(0, recovered["consecutive_failures"])
        self.assertIsNone(recovered["last_error"])
        self.assertIsNotNone(recovered["last_success_at"])

    async def test_server_outbox_and_durable_worker_are_independently_visible(self) -> None:
        with (
            patch.object(type(settings), "server_enabled", new_callable=PropertyMock, return_value=True),
            patch.object(scheduler, "_scan_once", AsyncMock()),
            patch.object(scheduler.server_sync, "flush_outbox", side_effect=RuntimeError("server down")),
            patch.object(scheduler, "_poll_relay_once", AsyncMock()),
            self.assertLogs("agentmate.scheduler", level="ERROR"),
        ):
            await scheduler._tick()
        by_name = {item["name"]: item for item in worker_health.snapshot()["components"]}
        self.assertEqual(0, by_name["automation_scheduler.scan"]["consecutive_failures"])
        self.assertEqual(1, by_name["server_sync.outbox"]["consecutive_failures"])

        with (
            patch.object(background_worker, "scan_once", AsyncMock(side_effect=ValueError("bad lease"))),
            self.assertLogs("agentmate.background_worker", level="ERROR"),
        ):
            await background_worker._scan_tick()
        by_name = {item["name"]: item for item in worker_health.snapshot()["components"]}
        self.assertEqual(1, by_name["background_worker.scan"]["consecutive_failures"])

    async def test_handler_failure_is_unhealthy_and_queue_summary_is_owner_scoped(self) -> None:
        old_path = settings.DB_PATH
        temp = tempfile.TemporaryDirectory()
        old_handler = background_worker._handlers.get("health_failure")
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None
        settings.DB_PATH = Path(temp.name) / "health.db"
        try:
            db.init_db()
            jobs.ensure_tables()

            async def fail(_job: dict) -> None:
                raise RuntimeError("handler exploded")

            background_worker.register_handler("health_failure", fail)
            job, _ = jobs.enqueue(
                owner_id="owner-a", kind="health_failure", entity_id="entity",
                idempotency_key="failure",
            )
            jobs.enqueue(
                owner_id="owner-b", kind="health_failure", entity_id="hidden",
                idempotency_key="other-owner",
            )
            claimed = jobs.claim(job["id"], background_worker._worker_id, time.time(), 30)
            assert claimed is not None
            await background_worker._run_claimed(claimed)

            snapshot = worker_health.snapshot()
            component = next(
                item for item in snapshot["components"]
                if item["name"] == "background_job.health_failure"
            )
            self.assertFalse(snapshot["healthy"])
            self.assertEqual(1, component["consecutive_failures"])
            summary = jobs.health_summary("owner-a", now=time.time() + 60)
            self.assertEqual(1, summary["counts"]["retry_wait"])
            self.assertEqual(1, summary["due"])
            self.assertEqual(1, sum(summary["counts"].values()))
        finally:
            if old_handler is None:
                background_worker._handlers.pop("health_failure", None)
            else:
                background_worker._handlers["health_failure"] = old_handler
            conn = getattr(db._local, "conn", None)
            if conn is not None:
                conn.close()
                db._local.conn = None
            settings.DB_PATH = old_path
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()
