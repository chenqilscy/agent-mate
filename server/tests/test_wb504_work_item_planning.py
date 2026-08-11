"""WB-504 narrow, versioned WorkItem Sprint update gates."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

from fastapi import HTTPException

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from config import settings  # noqa: E402
from models import Role  # noqa: E402
from routers.work_items import PlanningUpdateBody, update_item_planning  # noqa: E402


class WorkItemPlanningTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.temp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        self.owner = db.create_account(name="owner-504", password="password123")
        self.member = db.create_account(name="member-504", password="password123")
        self.viewer = db.create_account(name="viewer-504", password="password123")
        self.outsider = db.create_account(name="outsider-504", password="password123")
        self.project = db.create_project(name="planning", owner_id=self.owner.id)
        self.other = db.create_project(name="other", owner_id=self.outsider.id)
        db.add_project_member(self.project.id, self.member.id, Role.MEMBER)
        db.add_project_member(self.project.id, self.viewer.id, Role.VIEWER)
        self.milestone = db.create_milestone(project_id=self.project.id, name="M1")
        self.open_sprint = db.create_sprint(
            project_id=self.project.id, name="Sprint 1", goal="ship",
            start_date="2026-08-11", end_date="2026-08-18", status="planned",
            milestone_id=self.milestone["id"],
        )
        self.closed_sprint = db.create_sprint(
            project_id=self.project.id, name="Closed", goal="done",
            start_date="2026-08-01", end_date="2026-08-08", status="closed",
        )
        self.foreign_sprint = db.create_sprint(
            project_id=self.other.id, name="Foreign", goal="no",
            start_date="2026-08-11", end_date="2026-08-18", status="planned",
        )
        self.item = db.create_work_item(project_id=self.project.id, title="加入 Sprint")
        self.foreign_item = db.create_work_item(project_id=self.other.id, title="Foreign item")

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.temp.cleanup()

    def _update(self, sprint_id: str, version: int, account=None, item_id: str | None = None) -> dict:
        return update_item_planning(
            self.project.id,
            item_id or self.item["id"],
            PlanningUpdateBody(sprint_id=sprint_id, expected_version=version, sync_milestone=True),
            account or self.member,
        )

    def test_member_updates_open_sprint_and_audit_is_complete(self) -> None:
        self.assertEqual(1, self.item["version"])
        updated = self._update(self.open_sprint["id"], 1)
        self.assertEqual(self.open_sprint["id"], updated["sprint_id"])
        self.assertEqual(self.milestone["id"], updated["milestone_id"])
        self.assertEqual(2, updated["version"])
        activity = db.list_work_item_activity(self.project.id, self.item["id"])[0]
        self.assertEqual("planning_updated", activity["kind"])
        self.assertIn(f"actor_id={self.member.id}", activity["detail"])
        self.assertIn(f"old_sprint=; new_sprint={self.open_sprint['id']}", activity["detail"])
        self.assertIn("from_version=1; to_version=2", activity["detail"])

    def test_stale_closed_cross_project_and_missing_are_atomic(self) -> None:
        current = self._update(self.open_sprint["id"], 1)
        with self.assertRaises(HTTPException) as stale:
            self._update("", 1)
        self.assertEqual(409, stale.exception.status_code)
        with self.assertRaises(HTTPException) as closed:
            self._update(self.closed_sprint["id"], current["version"])
        self.assertEqual(400, closed.exception.status_code)
        with self.assertRaises(HTTPException) as foreign:
            self._update(self.foreign_sprint["id"], current["version"])
        self.assertEqual(400, foreign.exception.status_code)
        with self.assertRaises(HTTPException) as missing:
            self._update(self.open_sprint["id"], 1, item_id="missing-work-item")
        self.assertEqual(404, missing.exception.status_code)
        with self.assertRaises(HTTPException) as foreign_item:
            self._update(self.open_sprint["id"], 1, item_id=self.foreign_item["id"])
        self.assertEqual(404, foreign_item.exception.status_code)
        unchanged = db.get_work_item(self.item["id"])
        assert unchanged is not None
        self.assertEqual(self.open_sprint["id"], unchanged["sprint_id"])
        self.assertEqual(2, unchanged["version"])

    def test_viewer_is_rejected_and_generic_edits_advance_version(self) -> None:
        with self.assertRaises(HTTPException) as viewer:
            self._update(self.open_sprint["id"], 1, self.viewer)
        self.assertEqual(403, viewer.exception.status_code)
        edited = db.update_work_item(self.item["id"], priority="high")
        assert edited is not None
        self.assertEqual(2, edited["version"])
        with self.assertRaises(HTTPException) as stale:
            self._update(self.open_sprint["id"], 1)
        self.assertEqual(409, stale.exception.status_code)
