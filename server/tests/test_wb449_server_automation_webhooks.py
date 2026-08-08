"""WB-449 Server owns webhook secrets, idempotency and Run creation."""
from __future__ import annotations

import hashlib
import hmac
import json
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

import db  # noqa: E402
import secret_crypto  # noqa: E402
from config import settings  # noqa: E402
from routers import automation_webhooks, business  # noqa: E402


class ServerAutomationWebhookTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db = settings.DB_PATH
        self.old_key_path = settings.SSO_LOCAL_KEY_PATH
        self._close()
        settings.DB_PATH = Path(self.temp.name) / "server.db"
        settings.SSO_LOCAL_KEY_PATH = str(Path(self.temp.name) / "secret.key")
        db._local = threading.local()
        db.init_db()
        owner = db.create_account(name="owner-449", password="password123")
        token = db.create_token(owner.id)[0]
        app = FastAPI()
        app.include_router(business.router)
        app.include_router(automation_webhooks.router)
        self.client = TestClient(app)
        self.auth = {"Authorization": f"Bearer {token}"}

    def tearDown(self) -> None:
        self.client.close()
        self._close()
        settings.DB_PATH = self.old_db
        settings.SSO_LOCAL_KEY_PATH = self.old_key_path
        db._local = threading.local()
        self.temp.cleanup()

    @staticmethod
    def _close() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None

    @staticmethod
    def _signed(secret: str, raw: bytes, key: str) -> dict[str, str]:
        timestamp = str(int(time.time()))
        signature = hmac.new(
            secret.encode("utf-8"), timestamp.encode("ascii") + b"." + raw, hashlib.sha256,
        ).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-AgentMate-Timestamp": timestamp,
            "X-AgentMate-Signature": f"v1={signature}",
            "X-AgentMate-Idempotency-Key": key,
        }

    def test_signed_delivery_is_server_owned_encrypted_and_idempotent(self) -> None:
        automation = self.client.post("/api/automations", headers=self.auth, json={
            "name": "Webhook 检查", "prompt": "处理事件", "trigger_kind": "webhook",
        }).json()["automation"]
        created = self.client.post(
            f"/api/automations/{automation['id']}/webhook", headers=self.auth,
        )
        self.assertEqual(200, created.status_code, created.text)
        config = created.json()
        secret = config["secret"]
        stored = db.get_conn().execute(
            "SELECT secret_ciphertext FROM business_automation_webhooks WHERE id=?",
            (config["webhook_id"],),
        ).fetchone()[0]
        self.assertTrue(secret_crypto.is_encrypted(stored))
        self.assertNotIn(secret, stored)

        raw = json.dumps({"event": "build.done", "number": 7}, separators=(",", ":")).encode()
        endpoint = f"/api/webhooks/automations/{config['webhook_id']}"
        accepted = self.client.post(endpoint, content=raw, headers=self._signed(secret, raw, "delivery-449"))
        self.assertEqual(202, accepted.status_code, accepted.text)
        first = accepted.json()
        self.assertFalse(first["duplicate"])
        duplicate = self.client.post(endpoint, content=raw, headers=self._signed(secret, raw, "delivery-449"))
        self.assertEqual(202, duplicate.status_code, duplicate.text)
        self.assertTrue(duplicate.json()["duplicate"])
        self.assertEqual(first["fire_id"], duplicate.json()["fire_id"])
        self.assertEqual(1, db.get_conn().execute(
            "SELECT COUNT(*) FROM business_runs WHERE owner_id=?", (automation["owner_id"],),
        ).fetchone()[0])
        run_id = db.get_conn().execute(
            "SELECT run_id FROM business_automation_fires WHERE id=?", (first["fire_id"],),
        ).fetchone()[0]
        message = db.get_conn().execute(
            "SELECT content FROM business_messages WHERE run_id=? AND role='user'",
            (run_id,),
        ).fetchone()[0]
        self.assertIn('"event": "build.done"', message)

        changed = b'{"event":"different"}'
        conflict = self.client.post(
            endpoint, content=changed, headers=self._signed(secret, changed, "delivery-449"),
        )
        self.assertEqual(409, conflict.status_code, conflict.text)
        bad = self.client.post(endpoint, content=raw, headers={
            **self._signed(secret, raw, "delivery-bad"), "X-AgentMate-Signature": "v1=" + "0" * 64,
        })
        self.assertEqual(401, bad.status_code, bad.text)

        rotated = self.client.post(
            f"/api/automations/{automation['id']}/webhook/rotate", headers=self.auth,
        )
        self.assertEqual(200, rotated.status_code, rotated.text)
        self.assertNotEqual(secret, rotated.json()["secret"])
