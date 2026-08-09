"""WB-467 Server session-list context contract."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from config import settings  # noqa: E402
from routers import business  # noqa: E402


class RecentExecutionContextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.DB_PATH
        self._close()
        settings.DB_PATH = Path(self.temp.name) / "server.db"
        db.init_db()
        self.owner = db.create_account(name="owner-467", password="password123")
        self.token = db.create_token(self.owner.id)[0]
        self.project = db.create_project(name="Project 467", owner_id=self.owner.id)
        app = FastAPI()
        app.include_router(business.router)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        self._close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.temp.cleanup()

    @staticmethod
    def _close() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def test_session_list_contains_latest_run_work_item_context(self) -> None:
        session = self.client.post(
            "/api/sessions",
            headers={**self.headers, "Idempotency-Key": "wb467-session"},
            json={"title": "Linked execution", "project_id": self.project.id},
        ).json()["session"]
        first = self.client.post(
            "/api/runs",
            headers={**self.headers, "Idempotency-Key": "wb467-run-1"},
            json={"session_id": session["id"], "workspace": f"project:{self.project.id}"},
        )
        self.assertEqual(200, first.status_code, first.text)

        work_item = db.create_work_item(project_id=self.project.id, title="Authoritative task")
        latest = self.client.post(
            "/api/runs",
            headers={**self.headers, "Idempotency-Key": "wb467-run-2"},
            json={
                "session_id": session["id"],
                "work_item_id": work_item["id"],
                "workspace": f"project:{self.project.id}",
            },
        )
        self.assertEqual(200, latest.status_code, latest.text)

        listed = self.client.get("/api/sessions", headers=self.headers)
        self.assertEqual(200, listed.status_code, listed.text)
        record = next(item for item in listed.json()["sessions"] if item["id"] == session["id"])
        self.assertEqual(latest.json()["run"]["id"], record["latest_run_id"])
        self.assertEqual(work_item["id"], record["work_item_id"])
        self.assertEqual("Authoritative task", record["work_item_title"])


if __name__ == "__main__":
    unittest.main()
