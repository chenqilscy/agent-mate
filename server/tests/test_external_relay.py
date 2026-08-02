"""Scoped external service identity and durable relay contract (WB-361)."""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
import relay_store  # noqa: E402
from config import settings  # noqa: E402
from routers import relay  # noqa: E402


class ExternalRelayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db = settings.DB_PATH
        self._close()
        settings.DB_PATH = Path(self.tmp.name) / "server-test.db"
        db.init_db()
        self.owner = db.create_account(name="owner", password="1111")
        self.other = db.create_account(name="other", password="1111")
        self.owner_token = db.create_token(self.owner.id)[0]
        self.other_token = db.create_token(self.other.id)[0]
        app = FastAPI()
        app.include_router(relay.router)
        self.client = TestClient(app)
        self.owner_auth = {"Authorization": f"Bearer {self.owner_token}"}
        self.other_auth = {"Authorization": f"Bearer {self.other_token}"}
        response = self.client.post(
            "/api/integrations/service-accounts", headers=self.owner_auth,
            json={"name": "ci", "scopes": ["relay:write", "relay:read"]},
        )
        self.assertEqual(200, response.status_code, response.text)
        data = response.json()
        self.service = data["service_account"]
        self.service_token = data["token"]
        self.device = "device-owner-0001"
        self.client.post(
            "/api/relay/pull", headers=self.owner_auth,
            json={"device_id": self.device, "device_name": "Office PC"},
        )

    def tearDown(self) -> None:
        self.client.close()
        self._close()
        settings.DB_PATH = self.old_db
        self.tmp.cleanup()

    @staticmethod
    def _close() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None

    def _signed(self, body: dict, *, token: str | None = None, timestamp: int | None = None):
        raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
        secret = token or self.service_token
        ts = str(timestamp if timestamp is not None else int(time.time()))
        signature = hmac.new(
            secret.encode(), ts.encode("ascii") + b"." + raw, hashlib.sha256,
        ).hexdigest()
        headers = {
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
            "X-AgentMate-Timestamp": ts,
            "X-AgentMate-Signature": f"v1={signature}",
        }
        return raw, headers

    def test_idempotent_offline_delivery_device_isolation_and_ack(self) -> None:
        body = {
            "event_key": "build-42", "device_id": self.device,
            "automation_id": "auto-local-1", "payload": {"status": "failed"},
        }
        raw, headers = self._signed(body)
        first = self.client.post("/api/relay/events", headers=headers, content=raw)
        duplicate = self.client.post("/api/relay/events", headers=headers, content=raw)
        self.assertEqual(202, first.status_code, first.text)
        self.assertEqual(202, duplicate.status_code, duplicate.text)
        self.assertFalse(first.json()["duplicate"])
        self.assertTrue(duplicate.json()["duplicate"])
        event_id = first.json()["event"]["id"]

        wrong_owner = self.client.post(
            "/api/relay/pull", headers=self.other_auth,
            json={"device_id": self.device},
        )
        self.assertEqual([], wrong_owner.json()["events"])
        wrong_device = self.client.post(
            "/api/relay/pull", headers=self.owner_auth,
            json={"device_id": "device-owner-other"},
        )
        self.assertEqual([], wrong_device.json()["events"])
        pulled = self.client.post(
            "/api/relay/pull", headers=self.owner_auth,
            json={"device_id": self.device},
        ).json()["events"]
        self.assertEqual(1, len(pulled))
        self.assertEqual({"status": "failed"}, pulled[0]["payload"])

        # Simulate an App going offline after lease. The event remains durable and
        # is re-leased only to the same owner/device with a fresh token.
        db.get_conn().execute("UPDATE relay_events SET lease_until=0 WHERE id=?", (event_id,))
        db.get_conn().commit()
        redelivered = self.client.post(
            "/api/relay/pull", headers=self.owner_auth,
            json={"device_id": self.device},
        ).json()["events"]
        self.assertEqual(2, redelivered[0]["attempt"])
        self.assertNotEqual(pulled[0]["lease_token"], redelivered[0]["lease_token"])
        stale_ack = self.client.post(
            f"/api/relay/events/{event_id}/ack", headers=self.owner_auth,
            json={
                "device_id": self.device, "lease_token": pulled[0]["lease_token"],
                "status": "succeeded",
            },
        )
        self.assertEqual(409, stale_ack.status_code)
        pulled = redelivered

        wrong_ack = self.client.post(
            f"/api/relay/events/{event_id}/ack", headers=self.owner_auth,
            json={
                "device_id": "device-owner-wrong", "lease_token": pulled[0]["lease_token"],
                "status": "succeeded",
            },
        )
        self.assertEqual(409, wrong_ack.status_code)
        ack = self.client.post(
            f"/api/relay/events/{event_id}/ack", headers=self.owner_auth,
            json={
                "device_id": self.device, "lease_token": pulled[0]["lease_token"],
                "status": "succeeded",
            },
        )
        self.assertEqual(200, ack.status_code, ack.text)
        status = self.client.get(
            f"/api/relay/events/{event_id}",
            headers={"Authorization": f"Bearer {self.service_token}"},
        )
        self.assertEqual("succeeded", status.json()["event"]["status"])

    def test_rotation_revocation_signature_scope_and_rate_limit(self) -> None:
        read_only = self.client.post(
            "/api/integrations/service-accounts", headers=self.owner_auth,
            json={"name": "auditor", "scopes": ["relay:read"]},
        )
        self.assertEqual(200, read_only.status_code, read_only.text)
        raw, headers = self._signed({
            "event_key": "read-only-write", "device_id": self.device,
            "automation_id": "auto-local-1", "payload": {"ok": True},
        }, token=read_only.json()["token"])
        self.assertEqual(
            401,
            self.client.post("/api/relay/events", headers=headers, content=raw).status_code,
        )

        old = self.service_token
        rotated = self.client.post(
            f"/api/integrations/service-accounts/{self.service['id']}/rotate",
            headers=self.owner_auth,
        )
        self.assertEqual(200, rotated.status_code, rotated.text)
        self.service_token = rotated.json()["token"]
        self.assertIsNone(relay_store.resolve_service_token(old))
        self.assertIsNotNone(relay_store.resolve_service_token(self.service_token, "relay:write"))

        def body(key: str) -> dict:
            return {
                "event_key": key, "device_id": self.device,
                "automation_id": "auto-local-1", "payload": {"ok": True},
            }

        with patch.object(settings, "RELAY_RATE_LIMIT_PER_MINUTE", 1):
            raw, headers = self._signed(body("rate-1"))
            self.assertEqual(202, self.client.post("/api/relay/events", headers=headers, content=raw).status_code)
            raw, headers = self._signed(body("rate-2"))
            self.assertEqual(429, self.client.post("/api/relay/events", headers=headers, content=raw).status_code)

        revoked = self.client.delete(
            f"/api/integrations/service-accounts/{self.service['id']}", headers=self.owner_auth,
        )
        self.assertEqual(200, revoked.status_code)
        raw, headers = self._signed(body("after-revoke"))
        self.assertEqual(401, self.client.post("/api/relay/events", headers=headers, content=raw).status_code)


if __name__ == "__main__":
    unittest.main()
