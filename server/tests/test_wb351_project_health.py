"""WB-351 authoritative health rules and high-risk notification dedupe."""
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
from routers.governance import CreateBody, UpdateBody, create_record, update_record  # noqa: E402
from routers.project_health import project_health  # noqa: E402


class ProjectHealthTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local(); db.init_db()
        self.owner = db.create_account(name="owner", password="password123")
        self.member = db.create_account(name="member", password="password123")
        self.viewer = db.create_account(name="viewer", password="password123")
        self.outsider = db.create_account(name="outsider", password="password123")
        self.project = db.create_project(name="health", owner_id=self.owner.id)
        db.add_project_member(self.project.id, self.member.id, Role.MEMBER)
        db.add_project_member(self.project.id, self.viewer.id, Role.VIEWER)

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path; db._local = threading.local(); self.tmp.cleanup()

    def test_health_is_explainable_and_root_task_scoped(self) -> None:
        milestone = db.create_milestone(
            project_id=self.project.id, name="M1", due_date="2000-01-01",
        )
        root = db.create_work_item(
            project_id=self.project.id, title="blocked", status="paused",
            due_date="2000-01-01", milestone_id=milestone["id"],
        )
        db.create_work_item(
            project_id=self.project.id, title="child", status="todo",
            due_date="2000-01-01", parent_id=root["id"], milestone_id=milestone["id"],
        )
        create_record(self.project.id, CreateBody(
            record_type="decision", title="choose", milestone_id=milestone["id"],
        ), self.owner)
        result = project_health(self.project.id, self.viewer)
        self.assertEqual("critical", result["status"])
        self.assertEqual("server", result["source"])
        self.assertFalse(result["stale"])
        self.assertEqual(1, result["summary"]["total_tasks"])
        self.assertEqual(1, result["summary"]["overdue_tasks"])
        self.assertEqual(1, result["summary"]["blocked_tasks"])
        self.assertEqual(1, result["summary"]["pending_decisions"])
        self.assertEqual("critical", result["milestones"][0]["health"])
        self.assertIn("overdue", result["milestones"][0]["reasons"])
        with self.assertRaises(HTTPException) as denied:
            project_health(self.project.id, self.outsider)
        self.assertEqual(404, denied.exception.status_code)

    def test_high_risk_notifications_only_on_entry_or_upgrade(self) -> None:
        risk = create_record(self.project.id, CreateBody(
            record_type="risk", title="capacity", severity="high",
        ), self.member)
        self.assertEqual(1, len(db.list_notifications(self.owner.id)))
        self.assertEqual(1, len(db.list_notifications(self.viewer.id)))
        self.assertEqual(0, len(db.list_notifications(self.member.id)))
        update_record(self.project.id, risk["id"], UpdateBody(response="mitigate"), self.member)
        self.assertEqual(1, len(db.list_notifications(self.owner.id)))
        update_record(self.project.id, risk["id"], UpdateBody(severity="critical"), self.member)
        update_record(self.project.id, risk["id"], UpdateBody(severity="critical"), self.member)
        self.assertEqual(2, len(db.list_notifications(self.owner.id)))
        health = project_health(self.project.id, self.owner)
        self.assertEqual("critical", health["status"])
        self.assertEqual(1, health["summary"]["critical_risks"])


if __name__ == "__main__":
    unittest.main()
