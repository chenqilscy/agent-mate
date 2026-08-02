"""WB-354 local transition alerts and scheduler reuse coverage."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND)); sys.path.insert(0, str(ROOT))

import project_health_service  # noqa: E402
from agent import scheduler  # noqa: E402
from config import settings  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class ProjectHealthTransitionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_url = settings.AGENTMATE_SERVER_URL
        self._close()
        settings.DB_PATH = Path(self.tmp.name) / "app.db"
        settings.AGENTMATE_SERVER_URL = "http://server.invalid"
        db.init_db(); scheduler._last_health_scan_at = 0
        self.project = db.create_project(owner_id=LOCAL_USER_ID, name="local-transition")

    def tearDown(self) -> None:
        scheduler._running.clear(); scheduler._last_health_scan_at = 0
        self._close(); settings.DB_PATH = self.old_db
        settings.AGENTMATE_SERVER_URL = self.old_url; self.tmp.cleanup()

    @staticmethod
    def _close() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close(); db._local.conn = None

    def test_local_transition_is_idempotent_and_server_mirror_is_never_inferred(self) -> None:
        self.assertIsNone(project_health_service.observe_local_project_health(self.project.id, LOCAL_USER_ID))
        item = db.create_work_item(
            project_id=self.project.id, owner_id=LOCAL_USER_ID, title="blocked", status="paused",
        )
        event = project_health_service.observe_local_project_health(self.project.id, LOCAL_USER_ID)
        self.assertEqual("attention", event["to_status"])
        self.assertIsNone(project_health_service.observe_local_project_health(self.project.id, LOCAL_USER_ID))
        notifications = [row for row in db.list_notifications(LOCAL_USER_ID) if row["kind"] == "project_health"]
        self.assertEqual(1, len(notifications))

        db.update_work_item(item.id, status="done")
        recovered = project_health_service.observe_local_project_health(self.project.id, LOCAL_USER_ID)
        self.assertEqual("recovered", recovered["direction"])
        self.assertEqual(2, len(project_health_service.resolve_project_health_events(
            self.project.id, LOCAL_USER_ID,
        )["events"]))

        db.mirror_server_project(
            id="server-project-354", name="server", owner_id=LOCAL_USER_ID,
            instruction="", created_at=1, updated_at=1,
        )
        self.assertIsNone(project_health_service.observe_local_project_health(
            "server-project-354", LOCAL_USER_ID,
        ))
        self.assertEqual([], db.list_project_health_events("server-project-354"))

    async def test_existing_scheduler_throttles_local_and_server_scans(self) -> None:
        with patch.object(db, "list_server_identities", return_value=[(LOCAL_USER_ID, "token")]), patch.object(
            scheduler.server_client, "scan_project_health", return_value=None,
        ) as remote_scan:
            await scheduler._scan_once(1_000)
            await scheduler._scan_once(1_100)
            await scheduler._scan_once(1_301)
        self.assertEqual(2, remote_scan.call_count)
        self.assertEqual([], db.list_project_health_events(self.project.id))


if __name__ == "__main__":
    unittest.main()
