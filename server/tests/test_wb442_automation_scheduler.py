"""WB-442 Server automation definitions enqueue durable Local Agent Runs."""
from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import automation_scheduler  # noqa: E402
import db  # noqa: E402
from config import settings  # noqa: E402
from routers import business  # noqa: E402


class ServerAutomationSchedulerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.DB_PATH
        self._close()
        settings.DB_PATH = Path(self.temp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        owner = db.create_account(name="owner-442", password="password123")
        token = db.create_token(owner.id)[0]
        app = FastAPI()
        app.include_router(business.router)
        self.client = TestClient(app)
        self.auth = {"Authorization": f"Bearer {token}"}

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

    def test_due_and_manual_fires_create_server_runs_without_an_open_app(self) -> None:
        created = self.client.post("/api/automations", headers=self.auth, json={
            "name": "巡检", "prompt": "检查本机工作区", "trigger_kind": "interval",
            "interval_min": 5,
        })
        self.assertEqual(200, created.status_code, created.text)
        automation = created.json()["automation"]
        self.assertGreater(float(automation["next_run_at"]), time.time())

        due_at = time.time() - 1
        db.get_conn().execute(
            "UPDATE business_automations SET next_run_at=? WHERE id=?", (due_at, automation["id"]),
        )
        db.get_conn().commit()
        self.assertEqual(1, automation_scheduler.scan_once(time.time()))
        rows = db.get_conn().execute(
            "SELECT * FROM business_runs WHERE owner_id=?", (automation["owner_id"],),
        ).fetchall()
        self.assertEqual(1, len(rows))
        self.assertEqual("queued", rows[0]["status"])
        self.assertIn(automation["id"], rows[0]["request_snapshot"])
        self.assertEqual(0, automation_scheduler.scan_once(time.time()))

        manual = self.client.post(f"/api/automations/{automation['id']}/run", headers=self.auth)
        self.assertEqual(200, manual.status_code, manual.text)
        self.assertEqual("queued", manual.json()["run"]["status"])
        self.assertNotEqual(rows[0]["id"], manual.json()["run"]["id"])
        runtime_patch = self.client.patch(
            f"/api/automations/{automation['id']}", headers=self.auth,
            json={"expected_version": manual.json()["session"]["version"], "last_status": "ok"},
        )
        self.assertEqual(403, runtime_patch.status_code, runtime_patch.text)

    def test_failed_fire_retries_then_enters_server_dead_letter(self) -> None:
        created = self.client.post("/api/automations", headers=self.auth, json={
            "name": "重试巡检", "prompt": "执行", "trigger_kind": "interval",
            "interval_min": 60, "max_attempts": 2, "retry_backoff_sec": 1,
        }).json()["automation"]
        first = automation_scheduler.enqueue_automation(
            created, fire_key="manual:retry-test", planned_at=time.time(),
        )
        conn = db.get_conn()
        automation_scheduler.finish_run(
            conn, run_id=first["run"]["id"], owner_id=created["owner_id"], failed=True,
            error_code="tool_failed", error_message="first", prompt_tokens=7,
            completion_tokens=3, now=time.time() - 2,
        )
        conn.commit()
        fire = conn.execute(
            "SELECT * FROM business_automation_fires WHERE id=?", (first["fire"]["id"],),
        ).fetchone()
        self.assertEqual("retry_wait", fire["status"])

        self.assertEqual(1, automation_scheduler.scan_once(time.time()))
        fire = conn.execute(
            "SELECT * FROM business_automation_fires WHERE id=?", (first["fire"]["id"],),
        ).fetchone()
        self.assertEqual(2, fire["attempt"])
        self.assertNotEqual(first["run"]["id"], fire["run_id"])
        automation_scheduler.finish_run(
            conn, run_id=fire["run_id"], owner_id=created["owner_id"], failed=True,
            error_code="tool_failed", error_message="second", prompt_tokens=9,
            completion_tokens=4, now=time.time(),
        )
        conn.commit()
        fire = conn.execute(
            "SELECT * FROM business_automation_fires WHERE id=?", (first["fire"]["id"],),
        ).fetchone()
        self.assertEqual("dead_letter", fire["status"])
        listed = self.client.get("/api/automation-fires?status=dead_letter", headers=self.auth)
        self.assertEqual(200, listed.status_code, listed.text)
        self.assertEqual(first["fire"]["id"], listed.json()["fires"][0]["id"])


if __name__ == "__main__":
    unittest.main()
