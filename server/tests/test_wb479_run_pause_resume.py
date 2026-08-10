"""WB-479: pause/resume/cancel are distinct, durable Run controls."""
from __future__ import annotations

import base64
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
import run_protocol_store  # noqa: E402
from config import settings  # noqa: E402
from routers import business, run_protocol  # noqa: E402


class RunPauseResumeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.DB_PATH
        self._close()
        settings.DB_PATH = Path(self.temp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        owner = db.create_account(name="owner-479", password="password123")
        token = db.create_token(owner.id)[0]
        self.user_auth = {"Authorization": f"Bearer {token}"}
        app = FastAPI()
        app.include_router(business.router)
        app.include_router(run_protocol.router)
        self.client = TestClient(app)
        self.session_id = self.client.post(
            "/api/sessions", headers=self.user_auth, json={"title": "Run control"},
        ).json()["session"]["id"]

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

    def _run(self) -> str:
        response = self.client.post("/api/runs", headers=self.user_auth, json={
            "session_id": self.session_id, "request_snapshot": {"prompt": "work"},
        })
        self.assertEqual(200, response.status_code, response.text)
        return response.json()["run"]["id"]

    def _device(self):
        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw,
        )
        device_id = "device-wb479-00000000"
        challenge = self.client.post("/api/devices/register", headers=self.user_auth, json={
            "device_id": device_id, "name": "wb479", "public_key": base64.b64encode(public).decode(),
            "protocol_version": 1, "capabilities": {},
        }).json()["challenge"]
        signature = base64.b64encode(private.sign(challenge["challenge"].encode())).decode()
        verified = self.client.post(
            f"/api/devices/{device_id}/verify", headers=self.user_auth,
            json={"challenge_id": challenge["challenge_id"], "signature": signature},
        )
        self.assertEqual(200, verified.status_code, verified.text)
        return device_id, {"Authorization": f"Device {verified.json()['device_token']}"}

    @staticmethod
    def _event(run_id: str, device_id: str, epoch: int, sequence: int, event_type: str, payload=None):
        occurred_at = time.time()
        payload = payload or {}
        return {
            "event_id": str(uuid.uuid4()), "sequence": sequence, "type": event_type,
            "occurred_at": occurred_at, "payload": payload,
            "hash": run_protocol_store.event_digest(
                run_id=run_id, device_id=device_id, lease_epoch=epoch, sequence=sequence,
                event_type=event_type, occurred_at=occurred_at, payload=payload,
            ),
        }

    def test_queued_pause_requires_explicit_resume_before_lease(self) -> None:
        run_id = self._run()
        paused = self.client.post(f"/api/runs/{run_id}/pause", headers=self.user_auth)
        self.assertEqual("paused", paused.json()["run"]["status"])
        device_id, auth = self._device()
        self.assertIsNone(self.client.post("/api/agent/runs/lease", headers=auth, json={}).json()["lease"])
        resumed = self.client.post(f"/api/runs/{run_id}/resume", headers=self.user_auth)
        self.assertEqual("recoverable", resumed.json()["run"]["status"])
        lease = self.client.post("/api/agent/runs/lease", headers=auth, json={}).json()["lease"]
        self.assertEqual(run_id, lease["run"]["id"])
        self.assertEqual(device_id, lease["run"].get("target_device_id") or device_id)

    def test_active_run_pauses_and_resumes_same_identity_then_cancels(self) -> None:
        device_id, auth = self._device()
        run_id = self._run()
        lease = self.client.post("/api/agent/runs/lease", headers=auth, json={}).json()["lease"]
        lease_id, epoch = lease["lease_id"], lease["lease_epoch"]

        def submit(sequence: int, event_type: str, payload=None):
            response = self.client.post(
                f"/api/agent/runs/{run_id}/leases/{lease_id}/events", headers=auth,
                json={"lease_epoch": epoch, "events": [self._event(run_id, device_id, epoch, sequence, event_type, payload)]},
            )
            self.assertEqual(200, response.status_code, response.text)

        submit(1, "run.started")
        self.client.post(f"/api/runs/{run_id}/pause", headers=self.user_auth)
        commands = self.client.post(
            f"/api/agent/runs/{run_id}/leases/{lease_id}/renew", headers=auth,
            json={"lease_epoch": epoch},
        ).json()["commands"]
        pause_command = next(item for item in commands if item["command_type"] == "pause")
        submit(2, "run.paused")
        submit(3, "command.ack", {"command_id": pause_command["id"]})
        self.assertEqual("paused", self.client.get(f"/api/runs/{run_id}", headers=self.user_auth).json()["status"])

        self.client.post(f"/api/runs/{run_id}/resume", headers=self.user_auth)
        commands = self.client.post(
            f"/api/agent/runs/{run_id}/leases/{lease_id}/renew", headers=auth,
            json={"lease_epoch": epoch},
        ).json()["commands"]
        resume_command = next(item for item in commands if item["command_type"] == "resume")
        submit(4, "run.started", {"resumed_from": "paused"})
        submit(5, "command.ack", {"command_id": resume_command["id"]})
        running = self.client.get(f"/api/runs/{run_id}", headers=self.user_auth).json()
        self.assertEqual("running", running["status"])
        self.assertEqual(epoch, running["lease_epoch"])

        self.client.post(f"/api/runs/{run_id}/cancel", headers=self.user_auth)
        submit(6, "run.cancelled")
        self.assertEqual("cancelled", self.client.get(f"/api/runs/{run_id}", headers=self.user_auth).json()["status"])

    def test_paused_run_with_lost_lease_fails_closed_for_explicit_retry(self) -> None:
        device_id, auth = self._device()
        run_id = self._run()
        lease = self.client.post("/api/agent/runs/lease", headers=auth, json={}).json()["lease"]
        lease_id, epoch = lease["lease_id"], lease["lease_epoch"]

        def submit(sequence: int, event_type: str, payload=None):
            response = self.client.post(
                f"/api/agent/runs/{run_id}/leases/{lease_id}/events", headers=auth,
                json={"lease_epoch": epoch, "events": [self._event(run_id, device_id, epoch, sequence, event_type, payload)]},
            )
            self.assertEqual(200, response.status_code, response.text)

        submit(1, "run.started")
        self.client.post(f"/api/runs/{run_id}/pause", headers=self.user_auth)
        submit(2, "run.paused")
        db.get_conn().execute(
            "UPDATE run_leases SET expires_at=? WHERE id=?", (time.time() - 1, lease_id),
        )
        db.get_conn().commit()

        resumed = self.client.post(f"/api/runs/{run_id}/resume", headers=self.user_auth)
        self.assertEqual(200, resumed.status_code, resumed.text)
        run = resumed.json()["run"]
        self.assertEqual("failed", run["status"])
        self.assertEqual("resume_checkpoint_unavailable", run["error_code"])
        self.assertIsNone(self.client.post("/api/agent/runs/lease", headers=auth, json={}).json()["lease"])


if __name__ == "__main__":
    unittest.main()
