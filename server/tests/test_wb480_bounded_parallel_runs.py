"""WB-480 Server-side device capacity and workspace write admission."""
from __future__ import annotations

import base64
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from config import settings  # noqa: E402
from routers import business, run_protocol  # noqa: E402


class BoundedParallelLeaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.DB_PATH
        self._close()
        settings.DB_PATH = Path(self.temp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        self.owner = db.create_account(name="owner-480", password="password123")
        token = db.create_token(self.owner.id)[0]
        self.user_auth = {"Authorization": f"Bearer {token}"}
        app = FastAPI()
        app.include_router(business.router)
        app.include_router(run_protocol.router)
        self.client = TestClient(app)
        self.device_id, self.device_auth = self._device(capacity=2)

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

    def _device(self, *, capacity: int) -> tuple[str, dict[str, str]]:
        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw,
        )
        device_id = "device-wb480-00000000"
        challenge = self.client.post("/api/devices/register", headers=self.user_auth, json={
            "device_id": device_id, "name": "WB-480 Local Agent",
            "public_key": base64.b64encode(public).decode(), "protocol_version": 1,
            "capabilities": {
                "capabilities": ["agent.tools"], "max_parallel_runs": capacity,
            },
        }).json()["challenge"]
        signature = base64.b64encode(private.sign(challenge["challenge"].encode())).decode()
        verified = self.client.post(
            f"/api/devices/{device_id}/verify", headers=self.user_auth,
            json={"challenge_id": challenge["challenge_id"], "signature": signature},
        )
        return device_id, {"Authorization": f"Device {verified.json()['device_token']}"}

    def _project_session(self, name: str) -> tuple[str, str]:
        project = db.create_project(name=name, owner_id=self.owner.id)
        response = self.client.post("/api/sessions", headers=self.user_auth, json={
            "title": name, "kind": "projexec", "project_id": project.id,
        })
        self.assertEqual(200, response.status_code, response.text)
        return project.id, response.json()["session"]["id"]

    def _run(self, project_id: str, session_id: str, *, mode: str = "exec") -> str:
        response = self.client.post("/api/runs", headers=self.user_auth, json={
            "session_id": session_id, "project_id": project_id, "mode": mode,
            "workspace": f"project:{project_id}", "target_device_id": self.device_id,
            "required_capabilities": ["agent.tools"], "request_snapshot": {"prompt": "work"},
        })
        self.assertEqual(200, response.status_code, response.text)
        return response.json()["run"]["id"]

    def _lease(self):
        response = self.client.post(
            "/api/agent/runs/lease", headers=self.device_auth, json={"lease_seconds": 60},
        )
        self.assertEqual(200, response.status_code, response.text)
        return response.json()["lease"]

    def test_two_projects_fill_capacity_while_same_project_write_waits(self) -> None:
        project_a, session_a = self._project_session("Project A")
        project_b, session_b = self._project_session("Project B")
        run_a = self._run(project_a, session_a)
        queued_same_scope = self._run(project_a, session_a)
        run_b = self._run(project_b, session_b)

        self.assertEqual(run_a, self._lease()["run"]["id"])
        queued = self.client.get(f"/api/runs/{queued_same_scope}", headers=self.user_auth).json()
        self.assertEqual("resource_lock_wait", queued["queue_context"]["reason"])
        self.assertEqual(run_a, queued["queue_context"]["blocking_run"]["id"])
        self.assertEqual(run_b, self._lease()["run"]["id"])
        self.assertIsNone(self._lease())

    def test_read_only_runs_in_one_project_can_overlap(self) -> None:
        project_id, session_id = self._project_session("Read only")
        first = self._run(project_id, session_id, mode="plan")
        second = self._run(project_id, session_id, mode="ask")
        self.assertEqual(first, self._lease()["run"]["id"])
        self.assertEqual(second, self._lease()["run"]["id"])
        self.assertIsNone(self._lease())

    def test_waiting_user_is_resident_but_does_not_consume_compute_capacity(self) -> None:
        project_a, session_a = self._project_session("Waiting")
        project_b, session_b = self._project_session("Running")
        project_c, session_c = self._project_session("Next")
        waiting = self._run(project_a, session_a)
        running = self._run(project_b, session_b)
        self.assertEqual(waiting, self._lease()["run"]["id"])
        self.assertEqual(running, self._lease()["run"]["id"])
        db.get_conn().execute(
            "UPDATE business_runs SET status='waiting_user' WHERE id=?", (waiting,),
        )
        db.get_conn().commit()
        next_run = self._run(project_c, session_c)
        self.assertEqual(next_run, self._lease()["run"]["id"])


if __name__ == "__main__":
    unittest.main()
