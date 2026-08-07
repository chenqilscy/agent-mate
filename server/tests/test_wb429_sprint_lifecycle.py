"""WB-429: a project has one explicit current Sprint lifecycle."""
from __future__ import annotations

import sys
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path


SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from config import settings  # noqa: E402
from routers.pm import (  # noqa: E402
    SprintBody,
    SprintUpdateBody,
    create_sprint,
    update_sprint,
)


class SprintLifecycleTests(unittest.TestCase):
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

    def sprint(self, name: str, status: str = "planned") -> dict:
        return create_sprint(
            self.project.id,
            SprintBody(
                name=name,
                start_date="2026-08-01",
                end_date="2026-08-14",
                status=status,
            ),
            self.account,
        )

    def test_creating_active_sprint_closes_previous_current_sprint(self) -> None:
        first = self.sprint("Sprint 1", "active")
        second = self.sprint("Sprint 2", "active")

        states = {item["id"]: item["status"] for item in db.list_sprints(self.project.id)}
        self.assertEqual("closed", states[first["id"]])
        self.assertEqual("active", states[second["id"]])
        self.assertEqual(1, list(states.values()).count("active"))

    def test_starting_planned_sprint_atomically_switches_current_sprint(self) -> None:
        current = self.sprint("Current", "active")
        next_sprint = self.sprint("Next")

        started = update_sprint(
            self.project.id,
            next_sprint["id"],
            SprintUpdateBody(status="active"),
            self.account,
        )

        self.assertEqual("active", started["status"])
        self.assertEqual("closed", db.get_sprint(current["id"])["status"])
        self.assertEqual(
            [next_sprint["id"]],
            [item["id"] for item in db.list_sprints(self.project.id) if item["status"] == "active"],
        )

    def test_switching_current_sprint_does_not_touch_other_projects(self) -> None:
        other = db.create_project(name="Other", owner_id=self.account.id)
        other_sprint = create_sprint(
            other.id,
            SprintBody(
                name="Other current",
                start_date="2026-08-01",
                end_date="2026-08-14",
                status="active",
            ),
            self.account,
        )
        planned = self.sprint("Next")

        update_sprint(
            self.project.id,
            planned["id"],
            SprintUpdateBody(status="active"),
            self.account,
        )

        self.assertEqual("active", db.get_sprint(other_sprint["id"])["status"])

    def test_database_rejects_a_second_active_sprint_for_same_project(self) -> None:
        first = self.sprint("Current", "active")
        with self.assertRaises(sqlite3.IntegrityError):
            db.get_conn().execute(
                "INSERT INTO sprints "
                "(id,project_id,milestone_id,name,goal,start_date,end_date,status,sort,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "duplicate-active",
                    self.project.id,
                    "",
                    "Duplicate",
                    "",
                    "2026-08-15",
                    "2026-08-28",
                    "active",
                    2,
                    first["created_at"] + 1,
                    first["updated_at"] + 1,
                ),
            )
        db.get_conn().rollback()


class SprintLifecycleConsoleContractTests(unittest.TestCase):
    def test_console_exposes_explicit_lifecycle_and_read_only_history(self) -> None:
        source = (
            SERVER.parent
            / "console"
            / "src"
            / "components"
            / "project"
            / "ProjectWorkspace.tsx"
        ).read_text(encoding="utf-8")
        for marker in (
            "开始 Sprint",
            "结束 Sprint",
            "历史 Sprint 仅供查看",
            "只读历史任务",
            'sprint.status !== "closed"',
            'status: "planned"',
            "项目唯一的当前 Sprint",
        ):
            self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()
