"""WB-475: queued Runs expose durable device blockers without guessing."""
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


class RunQueueContextTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.DB_PATH
        self._close()
        settings.DB_PATH = Path(self.temp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        self.owner = db.create_account(name="owner-475", password="password123")
        token = db.create_token(self.owner.id)[0]
        self.user_auth = {"Authorization": f"Bearer {token}"}
        app = FastAPI()
        app.include_router(business.router)
        app.include_router(run_protocol.router)
        self.client = TestClient(app)
        self.session_id = self.client.post(
            "/api/sessions", headers=self.user_auth, json={"title": "Queue context"},
        ).json()["session"]["id"]
        self.device_id, self.device_auth = self._device()

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

    def _device(self) -> tuple[str, dict[str, str]]:
        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw,
        )
        device_id = "device-wb475-00000000"
        challenge = self.client.post("/api/devices/register", headers=self.user_auth, json={
            "device_id": device_id, "name": "WB-475 Local Agent",
            "public_key": base64.b64encode(public).decode(), "protocol_version": 1,
            "capabilities": {"capabilities": ["agent.tools"]},
        }).json()["challenge"]
        signature = base64.b64encode(private.sign(challenge["challenge"].encode())).decode()
        verified = self.client.post(
            f"/api/devices/{device_id}/verify", headers=self.user_auth,
            json={"challenge_id": challenge["challenge_id"], "signature": signature},
        )
        return device_id, {"Authorization": f"Device {verified.json()['device_token']}"}

    def _run(self, *, capability: str = "agent.tools") -> str:
        response = self.client.post("/api/runs", headers=self.user_auth, json={
            "session_id": self.session_id, "required_capabilities": [capability],
            "target_device_id": self.device_id, "request_snapshot": {"prompt": "work"},
        })
        self.assertEqual(200, response.status_code, response.text)
        return response.json()["run"]["id"]

    def _event(self, run_id: str, epoch: int, sequence: int, event_type: str) -> dict:
        occurred_at = time.time()
        payload = {"questions": [{"q": "允许执行？", "options": ["允许", "拒绝"]}]} if event_type == "run.waiting_user" else {}
        return {
            "event_id": str(uuid.uuid4()), "sequence": sequence, "type": event_type,
            "occurred_at": occurred_at, "payload": payload,
            "hash": run_protocol_store.event_digest(
                run_id=run_id, device_id=self.device_id, lease_epoch=epoch,
                sequence=sequence, event_type=event_type, occurred_at=occurred_at, payload=payload,
            ),
        }

    def test_waiting_user_blocker_is_exposed_with_direct_session_target(self) -> None:
        blocker_id = self._run()
        lease = self.client.post(
            "/api/agent/runs/lease", headers=self.device_auth, json={"lease_seconds": 60},
        ).json()["lease"]
        epoch = lease["lease_epoch"]
        submitted = self.client.post(
            f"/api/agent/runs/{blocker_id}/leases/{lease['lease_id']}/events",
            headers=self.device_auth, json={
                "lease_epoch": epoch,
                "events": [
                    self._event(blocker_id, epoch, 1, "run.started"),
                    self._event(blocker_id, epoch, 2, "run.waiting_user"),
                ],
            },
        )
        self.assertEqual(200, submitted.status_code, submitted.text)

        queued_id = self._run()
        queued = self.client.get(f"/api/runs/{queued_id}", headers=self.user_auth).json()
        self.assertEqual("queued", queued["status"])
        self.assertEqual("waiting_confirmation", queued["queue_context"]["reason"])
        self.assertEqual(blocker_id, queued["queue_context"]["blocking_run"]["id"])
        self.assertEqual(self.session_id, queued["queue_context"]["blocking_run"]["session_id"])

    def test_capability_and_offline_causes_remain_distinct(self) -> None:
        missing_id = self._run(capability="tool:missing")
        missing = self.client.get(f"/api/runs/{missing_id}", headers=self.user_auth).json()
        self.assertEqual("capability_mismatch", missing["queue_context"]["reason"])

        db.get_conn().execute(
            "UPDATE agent_devices SET last_seen_at=? WHERE id=?",
            (time.time() - run_protocol_store.DEVICE_ONLINE_WINDOW_SECONDS - 1, self.device_id),
        )
        db.get_conn().commit()
        offline_id = self._run()
        offline = self.client.get(f"/api/runs/{offline_id}", headers=self.user_auth).json()
        self.assertEqual("device_offline", offline["queue_context"]["reason"])


if __name__ == "__main__":
    unittest.main()
