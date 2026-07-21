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


if __name__ == "__main__":
    unittest.main()
