"""WB-433 device identity, fenced leases and ordered ACK protocol."""
from __future__ import annotations

import base64
import sys
import tempfile
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
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


class DeviceRunProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.DB_PATH
        self._close()
        settings.DB_PATH = Path(self.temp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        self.owner = db.create_account(name="owner-433", password="password123")
        self.owner_token = db.create_token(self.owner.id)[0]
        app = FastAPI()
        app.include_router(business.router)
        app.include_router(run_protocol.router)
        self.client = TestClient(app)
        self.user_auth = {"Authorization": f"Bearer {self.owner_token}"}
        self.session_id = self.client.post(
            "/api/sessions", headers=self.user_auth, json={"title": "Reliable runs"},
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

    def _register_device(self, suffix: str, capabilities: list[str] | None = None):
        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw,
        )
        device_id = f"device-{suffix}-43300000"
        response = self.client.post(
            "/api/devices/register", headers=self.user_auth, json={
                "device_id": device_id, "name": suffix,
                "public_key": base64.b64encode(public).decode("ascii"),
                "protocol_version": 1, "app_version": "1.0.0", "platform": "test", "arch": "x64",
                "capabilities": {"capabilities": capabilities or [], "supported_tools": {"read_file": "1"}},
            },
        )
        self.assertEqual(200, response.status_code, response.text)
        challenge = response.json()["challenge"]
        signature = base64.b64encode(
            private.sign(challenge["challenge"].encode("utf-8")),
        ).decode("ascii")
        verified = self.client.post(
            f"/api/devices/{device_id}/verify", headers=self.user_auth,
            json={"challenge_id": challenge["challenge_id"], "signature": signature},
        )
        self.assertEqual(200, verified.status_code, verified.text)
        token = verified.json()["device_token"]
        return device_id, private, {"Authorization": f"Device {token}"}, challenge, signature

    def _create_run(self, *, capability: str = "tool:read_file", max_recoveries: int = 3) -> str:
        response = self.client.post("/api/runs", headers=self.user_auth, json={
            "session_id": self.session_id, "required_capabilities": [capability],
            "request_snapshot": {"prompt": "read the report"}, "max_recoveries": max_recoveries,
        })
        self.assertEqual(200, response.status_code, response.text)
        return response.json()["run"]["id"]

    def _event(
        self, *, run_id: str, device_id: str, epoch: int, sequence: int,
        event_type: str, payload: dict | None = None,
    ) -> dict:
        payload = payload or {}
        occurred_at = time.time()
        return {
            "event_id": str(uuid.uuid4()), "sequence": sequence, "type": event_type,
            "occurred_at": occurred_at, "payload": payload,
            "hash": run_protocol_store.event_digest(
                run_id=run_id, device_id=device_id, lease_epoch=epoch, sequence=sequence,
                event_type=event_type, occurred_at=occurred_at, payload=payload,
            ),
        }

    def test_challenge_is_one_time_and_revocation_fails_closed(self) -> None:
        device_id, private, auth, challenge, signature = self._register_device("identity")
        replay = self.client.post(
            f"/api/devices/{device_id}/verify", headers=self.user_auth,
            json={"challenge_id": challenge["challenge_id"], "signature": signature},
        )
        self.assertEqual(401, replay.status_code, replay.text)

        public = private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw,
        )
        fresh = self.client.post("/api/devices/register", headers=self.user_auth, json={
            "device_id": device_id, "name": "identity", "public_key": base64.b64encode(public).decode(),
            "protocol_version": 1, "capabilities": {},
        }).json()["challenge"]
        wrong = Ed25519PrivateKey.generate().sign(fresh["challenge"].encode())
        bad = self.client.post(
            f"/api/devices/{device_id}/verify", headers=self.user_auth,
            json={"challenge_id": fresh["challenge_id"], "signature": base64.b64encode(wrong).decode()},
        )
        self.assertEqual(401, bad.status_code, bad.text)

        revoked = self.client.delete(f"/api/devices/{device_id}", headers=self.user_auth)
        self.assertEqual(200, revoked.status_code, revoked.text)
        heartbeat = self.client.post("/api/agent/heartbeat", headers=auth, json={"capabilities": {}})
        self.assertEqual(401, heartbeat.status_code, heartbeat.text)
        reregister = self.client.post("/api/devices/register", headers=self.user_auth, json={
            "device_id": device_id, "name": "identity", "public_key": base64.b64encode(public).decode(),
            "protocol_version": 1, "capabilities": {},
        })
        self.assertEqual(409, reregister.status_code, reregister.text)

    def test_gap_duplicate_ack_restart_cancel_and_terminal_commit(self) -> None:
        device_id, _private, auth, _challenge, _signature = self._register_device("primary")
        run_id = self._create_run()
        leased = self.client.post("/api/agent/runs/lease", headers=auth, json={"lease_seconds": 30})
        self.assertEqual(200, leased.status_code, leased.text)
        lease = leased.json()["lease"]
        self.assertEqual(run_id, lease["run"]["id"])
        lease_id, epoch = lease["lease_id"], lease["lease_epoch"]

        secret = self._event(
            run_id=run_id, device_id=device_id, epoch=epoch, sequence=1,
            event_type="run.checkpoint", payload={"api_key": "must-not-upload"},
        )
        rejected_secret = self.client.post(
            f"/api/agent/runs/{run_id}/leases/{lease_id}/events", headers=auth,
            json={"lease_epoch": epoch, "events": [secret]},
        )
        self.assertEqual(409, rejected_secret.status_code, rejected_secret.text)

        second = self._event(
            run_id=run_id, device_id=device_id, epoch=epoch, sequence=2,
            event_type="run.checkpoint", payload={"cursor": 2},
        )
        gap = self.client.post(
            f"/api/agent/runs/{run_id}/leases/{lease_id}/events", headers=auth,
            json={"lease_epoch": epoch, "events": [second]},
        )
        self.assertEqual(409, gap.status_code, gap.text)
        self.assertEqual(1, gap.json()["detail"]["expected_sequence"])

        first = self._event(
            run_id=run_id, device_id=device_id, epoch=epoch, sequence=1,
            event_type="run.started",
        )
        accepted = self.client.post(
            f"/api/agent/runs/{run_id}/leases/{lease_id}/events", headers=auth,
            json={"lease_epoch": epoch, "events": [first]},
        )
        duplicate = self.client.post(
            f"/api/agent/runs/{run_id}/leases/{lease_id}/events", headers=auth,
            json={"lease_epoch": epoch, "events": [first]},
        )
        self.assertEqual(1, accepted.json()["ack_high_water"])
        self.assertEqual(1, duplicate.json()["ack_high_water"])
        self.assertEqual(1, db.get_conn().execute(
            "SELECT COUNT(*) FROM run_events WHERE run_id=?", (run_id,),
        ).fetchone()[0])

        # SQLite close/reopen proves ACK/event authority survives Server restart.
        self._close()
        db.init_db()
        accepted2 = self.client.post(
            f"/api/agent/runs/{run_id}/leases/{lease_id}/events", headers=auth,
            json={"lease_epoch": epoch, "events": [second]},
        )
        self.assertEqual(2, accepted2.json()["ack_high_water"], accepted2.text)

        cancelled = self.client.post(f"/api/runs/{run_id}/cancel", headers=self.user_auth)
        self.assertEqual(200, cancelled.status_code, cancelled.text)
        renewed = self.client.post(
            f"/api/agent/runs/{run_id}/leases/{lease_id}/renew", headers=auth,
            json={"lease_epoch": epoch, "lease_seconds": 30},
        )
        self.assertEqual("cancel", renewed.json()["commands"][0]["command_type"])
        terminal = self._event(
            run_id=run_id, device_id=device_id, epoch=epoch, sequence=3,
            event_type="run.cancel_ack", payload={"version": 1},
        )
        done = self.client.post(
            f"/api/agent/runs/{run_id}/leases/{lease_id}/events", headers=auth,
            json={"lease_epoch": epoch, "events": [terminal]},
        )
        self.assertEqual(3, done.json()["ack_high_water"], done.text)
        self.assertEqual("cancelled", self.client.get(f"/api/runs/{run_id}", headers=self.user_auth).json()["status"])
        self.assertEqual(0, db.get_conn().execute(
            "SELECT COUNT(*) FROM run_commands WHERE run_id=? AND status='pending'", (run_id,),
        ).fetchone()[0])

    def test_double_worker_and_expired_epoch_are_fenced(self) -> None:
        device1, _private1, auth1, _challenge1, _signature1 = self._register_device("worker1")
        device2, _private2, auth2, _challenge2, _signature2 = self._register_device("worker2")
        run_id = self._create_run()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(
                lambda headers: self.client.post(
                    "/api/agent/runs/lease", headers=headers, json={"lease_seconds": 30},
                ),
                (auth1, auth2),
            ))
        leases = [response.json()["lease"] for response in responses]
        winner_indexes = [index for index, lease in enumerate(leases) if lease is not None]
        self.assertEqual(1, len(winner_indexes))
        winner_index = winner_indexes[0]
        first = leases[winner_index]
        self.assertIsNotNone(first)
        old_auth = (auth1, auth2)[winner_index]
        old_device = (device1, device2)[winner_index]
        new_auth = (auth2, auth1)[winner_index]
        new_device = (device2, device1)[winner_index]
        db.get_conn().execute("UPDATE run_leases SET expires_at=0 WHERE id=?", (first["lease_id"],))
        db.get_conn().commit()
        recovered = self.client.post("/api/agent/runs/lease", headers=new_auth, json={"lease_seconds": 30}).json()["lease"]
        self.assertEqual(first["lease_epoch"] + 1, recovered["lease_epoch"])

        stale_event = self._event(
            run_id=run_id, device_id=old_device, epoch=first["lease_epoch"], sequence=1,
            event_type="run.started",
        )
        stale = self.client.post(
            f"/api/agent/runs/{run_id}/leases/{first['lease_id']}/events", headers=old_auth,
            json={"lease_epoch": first["lease_epoch"], "events": [stale_event]},
        )
        self.assertEqual(409, stale.status_code, stale.text)

        complete = self._event(
            run_id=run_id, device_id=new_device, epoch=recovered["lease_epoch"], sequence=1,
            event_type="run.completed", payload={"summary": "done"},
        )
        submitted = self.client.post(
            f"/api/agent/runs/{run_id}/leases/{recovered['lease_id']}/events", headers=new_auth,
            json={"lease_epoch": recovered["lease_epoch"], "events": [complete]},
        )
        self.assertEqual(200, submitted.status_code, submitted.text)
        self.assertEqual("completed", self.client.get(f"/api/runs/{run_id}", headers=self.user_auth).json()["status"])


if __name__ == "__main__":
    unittest.main()
