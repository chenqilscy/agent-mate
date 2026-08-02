"""WB-351 local computation and explicit stale Server fallback."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from auth.deps import set_current_user_id  # noqa: E402
from config import settings  # noqa: E402
import project_health_service  # noqa: E402
from routers import notifications, project_health  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class ProjectHealthRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH; self.old_url = settings.AGENTMATE_SERVER_URL
        self._close(); settings.DB_PATH = Path(self.tmp.name) / "app.db"
        settings.AGENTMATE_SERVER_URL = "http://server.invalid"
        db.init_db(); set_current_user_id(LOCAL_USER_ID)

    def tearDown(self) -> None:
        set_current_user_id(None); self._close(); settings.DB_PATH = self.old_db
        settings.AGENTMATE_SERVER_URL = self.old_url; self.tmp.cleanup()

    @staticmethod
    def _close() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close(); db._local.conn = None

    def test_local_health_uses_real_local_records(self) -> None:
        project = db.create_project(owner_id=LOCAL_USER_ID, name="local")
        db.create_work_item(
            project_id=project.id, owner_id=LOCAL_USER_ID, title="late",
            status="paused", due_date="2000-01-01",
        )
        db.create_project_governance(
            project_id=project.id, record_type="risk", title="risk", description="",
            status="open", severity="high", owner_id=LOCAL_USER_ID, response="",
            rationale="", created_by=LOCAL_USER_ID,
        )
        result = project_health.project_health(project.id)
        self.assertEqual("attention", result["status"])
        self.assertEqual("local", result["source"])
        self.assertFalse(result["stale"])
        self.assertEqual(1, result["summary"]["blocked_tasks"])
        self.assertEqual(1, result["summary"]["high_risks"])

    def test_server_health_is_authoritative_then_falls_back_stale(self) -> None:
        db.mirror_server_project(
            id="server-project", name="shared", owner_id=LOCAL_USER_ID,
            instruction="", created_at=1, updated_at=1,
        )
        db.mirror_server_work_items("server-project", [{
            "id": "work-1", "project_id": "server-project", "title": "late",
            "status": "todo", "due_date": "2000-01-01", "created_at": 1, "updated_at": 2,
        }])
        authoritative = {
            "status": "healthy", "source": "server", "stale": False,
            "computed_at": 10, "as_of": "2026-08-02",
            "summary": {"overdue_tasks": 7, "critical_risks": 2},
            "reasons": [], "milestones": [],
        }
        with patch.object(project_health_service.server_client, "get_project_health", return_value=authoritative):
            self.assertIs(authoritative, project_health.project_health(
                "server-project", authorization="Bearer token",
            ))
        with patch.object(project_health_service.server_client, "get_project_health", return_value=None):
            stale = project_health.project_health("server-project", authorization="Bearer token")
        self.assertEqual("server-cache", stale["source"])
        self.assertTrue(stale["stale"])
        self.assertEqual(7, stale["summary"]["overdue_tasks"])
        self.assertEqual(2, stale["summary"]["critical_risks"])

        db.reconcile_server_project_access(LOCAL_USER_ID, set())
        self.assertIsNone(db.get_project_health_cache("server-project"))

    def test_message_center_merges_current_server_account_notifications(self) -> None:
        db.create_notification(user_id=LOCAL_USER_ID, kind="local", title="local")
        remote = {"notifications": [{
            "id": "remote-1", "kind": "project_risk", "title": "remote risk",
            "body": "risk", "read": 0, "created_at": 9_999_999_999,
        }], "unread": 1}
        with patch.object(notifications.server_client, "server_notifications", return_value=remote):
            result = notifications.list_notifications("Bearer token")
        self.assertEqual(2, result["unread"])
        self.assertEqual("remote risk", result["notifications"][0]["title"])
        with patch.object(notifications.server_client, "mark_server_notifications", return_value=True) as mark, \
             patch.object(notifications.server_client, "server_notifications", return_value={"notifications": [], "unread": 0}):
            marked = notifications.mark_read(notifications.ReadBody(ids=["remote-1"]), "Bearer token")
        self.assertTrue(marked["ok"]); mark.assert_called_once_with("token", ["remote-1"])


if __name__ == "__main__":
    unittest.main()
