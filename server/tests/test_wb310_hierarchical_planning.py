"""WB-310: milestone -> Sprint -> task guided planning workflow."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
ROOT = SERVER.parent
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from config import settings  # noqa: E402
from routers.pm import (  # noqa: E402
    SprintBody,
    SprintUpdateBody,
    create_sprint,
    update_sprint,
)


class HierarchicalPlanningTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        self.account = db.create_account(name="owner", password="password123")
        self.project = db.create_project(name="Delivery", owner_id=self.account.id)

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.tmp.cleanup()

    def test_sprint_milestone_reference_is_scoped_and_delete_only_unbinds(self) -> None:
        milestone = db.create_milestone(
            project_id=self.project.id,
            name="Release",
            description="",
            due_date="2026-08-01",
            status="open",
        )
        sprint = create_sprint(
            self.project.id,
            SprintBody(
                name="Sprint 1",
                milestone_id=milestone["id"],
                start_date="2026-07-24",
                end_date="2026-07-31",
            ),
            self.account,
        )
        task = db.create_work_item(
            project_id=self.project.id,
            title="Build",
            milestone_id=milestone["id"],
            sprint_id=sprint["id"],
        )
        self.assertEqual(milestone["id"], sprint["milestone_id"])

        other = db.create_project(name="Other", owner_id=self.account.id)
        foreign = db.create_milestone(
            project_id=other.id,
            name="Foreign",
            description="",
            due_date="",
            status="open",
        )
        updated = update_sprint(
            self.project.id,
            sprint["id"],
            SprintUpdateBody(milestone_id=foreign["id"]),
            self.account,
        )
        self.assertEqual("", updated["milestone_id"])

        update_sprint(
            self.project.id,
            sprint["id"],
            SprintUpdateBody(milestone_id=milestone["id"]),
            self.account,
        )
        db.delete_milestone(milestone["id"])
        self.assertEqual("", db.get_sprint(sprint["id"])["milestone_id"])
        self.assertEqual("", db.get_work_item(task["id"])["milestone_id"])
        self.assertIsNotNone(db.get_sprint(sprint["id"]))
        self.assertIsNotNone(db.get_work_item(task["id"]))

    def test_existing_sprint_rows_gain_empty_milestone_without_data_loss(self) -> None:
        conn = db.get_conn()
        conn.execute("DROP TABLE sprints")
        conn.execute(
            """
            CREATE TABLE sprints (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                goal TEXT NOT NULL DEFAULT '',
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'planned',
                sort INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO sprints VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                "legacy-sprint",
                self.project.id,
                "Legacy",
                "",
                "2026-07-01",
                "2026-07-07",
                "closed",
                1,
                1.0,
                1.0,
            ),
        )
        # This fixture intentionally rewinds to the pre-v6 schema. A recorded
        # migration must never be rerun merely because runtime code notices a
        # missing column; remove only the v6 ledger row to model the historical DB.
        conn.execute(
            "DELETE FROM schema_migrations WHERE scope='server' AND version>=6"
        )
        conn.commit()

        db.init_db()

        sprint = db.get_sprint("legacy-sprint")
        self.assertIsNotNone(sprint)
        self.assertEqual("", sprint["milestone_id"])
        self.assertEqual("Legacy", sprint["name"])

    def test_console_exposes_contextual_creation_and_unplanned_tasks(self) -> None:
        source = (
            ROOT / "console" / "src" / "components" / "project" /
            "ProjectWorkspace.tsx"
        ).read_text(encoding="utf-8")
        for marker in (
            "onCreateSprint",
            "新建 Sprint",
            "openTask(null, {",
            "milestone_id: sprint.milestone_id",
            'value: "__unplanned__", label: "待规划"',
            "同步更新当前 Sprint 中任务的里程碑",
        ):
            self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()
