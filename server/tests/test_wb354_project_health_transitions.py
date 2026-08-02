"""WB-354 Server health transition persistence, alerts and access boundaries."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

from fastapi import HTTPException

SERVER = Path(__file__).resolve().parents[1]
ROOT = SERVER.parent
sys.path.insert(0, str(SERVER)); sys.path.insert(0, str(ROOT))

import db  # noqa: E402
from config import settings  # noqa: E402
from models import Role  # noqa: E402
from project_health_service import observe_project_health  # noqa: E402
from routers.project_health import project_health_events, scan_project_health  # noqa: E402
from routers.work_items import CreateBody, UpdateBody, create_item, update_item  # noqa: E402
from shared.project_health import classify_health_transition  # noqa: E402


class ProjectHealthTransitionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local(); db.init_db()
        self.owner = db.create_account(name="owner-354", password="password123")
        self.member = db.create_account(name="member-354", password="password123")
        self.outsider = db.create_account(name="outsider-354", password="password123")
        self.project = db.create_project(name="transition", owner_id=self.owner.id)
        db.add_project_member(self.project.id, self.member.id, Role.MEMBER)

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path; db._local = threading.local(); self.tmp.cleanup()

    def _health_notifications(self, account_id: str) -> list[dict]:
        return [row for row in db.list_notifications(account_id) if row["kind"] == "project_health"]

    def test_classification_baseline_dedupe_recovery_and_recurrence(self) -> None:
        self.assertIsNone(classify_health_transition("healthy", "healthy"))
        self.assertEqual("worsened", classify_health_transition("healthy", "critical")["direction"])
        self.assertEqual(-1, classify_health_transition("critical", "attention")["rank_delta"])

        self.assertIsNone(observe_project_health(self.project.id))
        item = db.create_work_item(project_id=self.project.id, title="blocked", status="paused")
        attention = observe_project_health(self.project.id, actor_name="owner-354")
        self.assertEqual(("healthy", "attention"), (attention["from_status"], attention["to_status"]))
        self.assertIsNone(observe_project_health(self.project.id))
        self.assertEqual(1, len(self._health_notifications(self.owner.id)))
        self.assertEqual(1, len(self._health_notifications(self.member.id)))

        milestone = db.create_milestone(project_id=self.project.id, name="late", due_date="2000-01-01")
        db.update_work_item(item["id"], milestone_id=milestone["id"])
        critical = observe_project_health(self.project.id)
        self.assertEqual("critical", critical["to_status"])
        self.assertEqual(2, len(self._health_notifications(self.owner.id)))

        db.update_work_item(item["id"], status="done")
        db.update_milestone(milestone["id"], status="closed")
        recovered = observe_project_health(self.project.id)
        self.assertEqual("recovered", recovered["direction"])
        self.assertEqual(2, len(self._health_notifications(self.owner.id)))

        db.update_work_item(item["id"], status="paused")
        db.update_milestone(milestone["id"], status="open")
        recurrence = observe_project_health(self.project.id)
        self.assertEqual("worsened", recurrence["direction"])
        self.assertEqual(3, len(self._health_notifications(self.owner.id)))
        self.assertEqual(4, len(project_health_events(self.project.id, self.member)["events"]))

        with self.assertRaises(HTTPException) as denied:
            project_health_events(self.project.id, self.outsider)
        self.assertEqual(404, denied.exception.status_code)
        self.assertEqual(0, scan_project_health(self.outsider)["scanned"])

    def test_authoritative_write_path_observes_immediately(self) -> None:
        created = create_item(
            self.project.id, CreateBody(title="blocked-now", status="paused"), self.owner,
        )
        events = db.list_project_health_events(self.project.id)
        self.assertEqual(["attention"], [event["to_status"] for event in events])
        update_item(
            self.project.id, created["id"], UpdateBody(status="done"), self.owner,
        )
        events = db.list_project_health_events(self.project.id)
        self.assertEqual(["healthy", "attention"], [event["to_status"] for event in events])


if __name__ == "__main__":
    unittest.main()
