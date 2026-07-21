"""WB-112f completion: custom fields, dependency graph, sprint burndown and CSV export."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from config import settings  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from routers.pm import (  # noqa: E402
    CustomFieldBody, SprintBody, create_custom_field, create_sprint, export_pm_csv, sprint_burndown,
)
from routers.work_items import CreateBody, UpdateBody, create_item, list_items, update_item  # noqa: E402


class PMCompletionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local(); db.init_db()
        self.account = db.create_account(name="owner", password="password123")
        self.project = db.create_project(name="Delivery", owner_id=self.account.id)

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None: conn.close()
        settings.DB_PATH = self.old_path; db._local = threading.local(); self.tmp.cleanup()

    def test_fields_dependency_critical_path_sprint_burndown_and_export(self) -> None:
        field = create_custom_field(self.project.id, CustomFieldBody(
            name="Risk", field_type="select", options=["Low", "High"], required=True,
        ), self.account)
        sprint = create_sprint(self.project.id, SprintBody(
            name="Sprint 1", goal="ship", start_date="2026-07-22", end_date="2026-07-24", status="active",
        ), self.account)
        first = create_item(self.project.id, CreateBody(
            title="Design", estimate_h=2, sprint_id=sprint["id"], custom_fields={field["id"]: "High"},
        ), self.account)
        second = create_item(self.project.id, CreateBody(
            title="Build", estimate_h=5, sprint_id=sprint["id"], dependency_ids=[first["id"]],
        ), self.account)
        listed = list_items(self.project.id, self.account)["items"]
        self.assertEqual({first["id"], second["id"]}, {item["id"] for item in listed if item["critical_path"]})
        with self.assertRaisesRegex(HTTPException, "dependency cycle"):
            update_item(self.project.id, first["id"], UpdateBody(dependency_ids=[second["id"]]), self.account)
        update_item(self.project.id, first["id"], UpdateBody(status="done"), self.account)
        burn = sprint_burndown(self.project.id, sprint["id"], self.account)
        self.assertEqual(7.0, burn["total"])
        self.assertEqual(3, len(burn["points"]))
        response = export_pm_csv(self.project.id, self.account)
        body = response.body.decode("utf-8-sig")
        self.assertIn("Risk", body)
        self.assertIn("Design", body)
        self.assertIn("Sprint 1", body)

    def test_cross_project_references_and_unknown_custom_values_are_dropped(self) -> None:
        other = db.create_project(name="Other", owner_id=self.account.id)
        foreign = db.create_work_item(project_id=other.id, title="Foreign")
        item = create_item(self.project.id, CreateBody(
            title="Safe", dependency_ids=[foreign["id"]], sprint_id="missing",
            custom_fields={"unknown": "value"},
        ), self.account)
        self.assertEqual([], item["dependency_ids"])
        self.assertEqual("", item["sprint_id"])
        self.assertEqual({}, item["custom_fields"])


if __name__ == "__main__":
    unittest.main()
