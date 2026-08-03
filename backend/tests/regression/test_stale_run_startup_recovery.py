"""Crash-leftover Run reconciliation contract (WB-378)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import settings
from storage import db
from storage.models import LOCAL_USER_ID


class StaleRunStartupRecoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db = settings.DB_PATH
        db.close_thread_connection()
        settings.DB_PATH = Path(self.tmp.name) / "agentmate-test.db"
        db.init_db()

    def tearDown(self) -> None:
        db.close_thread_connection()
        settings.DB_PATH = self.old_db
        self.tmp.cleanup()

    def _run(self, status: str, *, kind: str = "chat"):
        session = db.create_session(owner_id=LOCAL_USER_ID, title=status, kind=kind)
        db.touch_session(session.id, status="running")
        run, _ = db.create_run(
            session_id=session.id, owner_id=LOCAL_USER_ID, project_id=None,
            mode="plan" if status == "planning" else "exec", workspace="default",
        )
        if status == "waiting_approval":
            db.set_run_status(run.id, "waiting_approval", checkpoint={"questions": [{"q": "继续？"}]})
        return session, db.get_run(run.id)

    def test_all_interactive_active_states_pause_atomically_and_can_retry(self) -> None:
        pairs = [self._run(status) for status in ("planning", "waiting_approval", "running")]
        automation_session, automation_run = self._run("running", kind="automation")
        completed_session = db.create_session(owner_id=LOCAL_USER_ID, title="done")
        db.touch_session(completed_session.id, status="done")
        completed, _ = db.create_run(
            session_id=completed_session.id, owner_id=LOCAL_USER_ID,
            project_id=None, mode="exec", workspace="default",
        )
        db.set_run_status(completed.id, "completed")

        recovered = db.recover_stale_runs(recovered_at=1234.5)
        self.assertEqual(3, len(recovered))
        for session, original in pairs:
            current = db.get_run(original.id)
            self.assertEqual("paused", current.status)
            self.assertEqual("process_restarted", current.error_code)
            self.assertEqual(original.status, current.checkpoint["previous_status"])
            self.assertEqual(1234.5, current.checkpoint["recovered_at"])
            self.assertEqual("idle", db.get_session(session.id).status)
            retry, created = db.create_retry_run(current.id, LOCAL_USER_ID)
            self.assertTrue(created)
            self.assertEqual(current.id, retry.retry_of)

        self.assertEqual("running", db.get_run(automation_run.id).status)
        self.assertEqual("running", db.get_session(automation_session.id).status)
        self.assertEqual("completed", db.get_run(completed.id).status)
        self.assertEqual([], db.recover_stale_runs(recovered_at=1235.0))

    def test_backend_startup_invokes_reconciliation_before_workers(self) -> None:
        session, run = self._run("running")
        from main import _startup

        with (
            patch("device_settings.apply_all"),
            patch("storage.orchestration_store.ensure_tables"),
            patch.object(db, "migrate_skill_identities", return_value={"changed": 0, "dropped": 0}),
        ):
            _startup()
        self.assertEqual("paused", db.get_run(run.id).status)
        self.assertEqual("idle", db.get_session(session.id).status)


if __name__ == "__main__":
    unittest.main()
