"""Local mirror preservation for WB-112f PM fields."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from config import settings  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from backend.routers.work_items import _sanitize_local_refs, _validate_local_fields  # noqa: E402
from storage import db  # noqa: E402


class PMMirrorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "backend.db"
        db._local = threading.local(); db.init_db()

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None: conn.close()
        settings.DB_PATH = self.old_path; db._local = threading.local(); self.tmp.cleanup()

    def test_server_pm_fields_round_trip_through_local_mirror(self) -> None:
        project_id, item_id = "project", "item"
        db.get_conn().execute(
            "INSERT INTO projects (id,owner_id,name,origin,created_at,updated_at) VALUES (?,?,?,'server',1,1)",
            (project_id, "owner", "Project"),
        ); db.get_conn().commit()
        db.mirror_server_work_items(project_id, [{
            "id": item_id, "project_id": project_id, "title": "Task", "status": "todo",
            "created_at": 10, "updated_at": 10, "custom_fields": {"risk": "high"},
            "dependency_ids": ["dep"], "sprint_id": "sprint-1",
        }])
        item = db.get_work_item(item_id)
        self.assertEqual({"risk": "high"}, item.custom_fields)
        self.assertEqual(["dep"], item.dependency_ids)
        self.assertEqual("sprint-1", item.sprint_id)

    def test_local_relationship_rules_match_server_and_delete_is_non_destructive(self) -> None:
        project = db.create_project(owner_id="owner", name="Local")
        parent = db.create_work_item(project_id=project.id, owner_id="owner", title="Parent")
        child = db.create_work_item(
            project_id=project.id, owner_id="owner", title="Child", parent_id=parent.id,
        )
        dependent = db.create_work_item(
            project_id=project.id, owner_id="owner", title="Dependent", dependency_ids=[parent.id],
        )
        with self.assertRaisesRegex(HTTPException, "parent cycle"):
            _sanitize_local_refs(project.id, parent.id, {"parent_id": child.id})
        with self.assertRaisesRegex(HTTPException, "due_date"):
            _validate_local_fields({"start_date": "2026-07-24", "due_date": "2026-07-23"})

        db.delete_work_item(parent.id)
        self.assertEqual("", db.get_work_item(child.id).parent_id)
        self.assertEqual([], db.get_work_item(dependent.id).dependency_ids)


if __name__ == "__main__":
    unittest.main()
