"""Secure, idempotent automation Webhook ingress coverage (WB-347)."""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from agent import scheduler  # noqa: E402
from auth.middleware import AuthMiddleware  # noqa: E402
from config import settings  # noqa: E402
from routers import automations  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class AutomationWebhookIngressTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db = settings.DB_PATH
        self._close_connection()
        settings.DB_PATH = Path(self.tmp.name) / "agentmate-test.db"
        db.init_db()
        self.token = db.create_token(LOCAL_USER_ID)
        db.set_server_identity(LOCAL_USER_ID, self.token)
        app = FastAPI()
        app.add_middleware(AuthMiddleware)
        app.include_router(automations.router)
        self.client = TestClient(app)
        self.auth = {"Authorization": f"Bearer {self.token}"}
        response = self.client.post(
            "/api/automations", headers=self.auth,
            json={"name": "外部告警", "prompt": "分析告警", "trigger_kind": "webhook"},
        )
        self.assertEqual(200, response.status_code, response.text)
        self.auto = response.json()

    def tearDown(self) -> None:
        self.client.close()
        scheduler._running.clear()
        self._close_connection()
        settings.DB_PATH = self.old_db
        self.tmp.cleanup()

    @staticmethod
    def _close_connection() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None

    @staticmethod
    def _signed(secret: str, body: bytes, key: str, timestamp: int | None = None) -> dict[str, str]:
        ts = str(timestamp if timestamp is not None else int(time.time()))
        signature = hmac.new(
            secret.encode("utf-8"), ts.encode("ascii") + b"." + body, hashlib.sha256
        ).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-AgentMate-Timestamp": ts,
            "X-AgentMate-Signature": f"v1={signature}",
            "X-AgentMate-Idempotency-Key": key,
        }

    def _provision(self) -> dict:
        response = self.client.post(
            f"/api/automations/{self.auto['id']}/webhook", headers=self.auth, json={}
        )
        self.assertEqual(200, response.status_code, response.text)
        return response.json()

    def test_valid_delivery_is_idempotent_audited_and_payload_is_not_exposed(self) -> None:
        config = self._provision()
        self.assertTrue(config["secret"].startswith("whsec_"))
        readback = self.client.get(
            f"/api/automations/{self.auto['id']}/webhook", headers=self.auth
        ).json()
        self.assertNotIn("secret", readback)

        body = json.dumps({"severity": "critical", "message": "disk full"}, separators=(",", ":")).encode()
        path = config["endpoint"]
        signed = self._signed(config["secret"], body, "evt-1")
        signed["Authorization"] = "Bearer definitely-invalid"
        with patch.object(scheduler, "_launch"):
            first = self.client.post(path, content=body, headers=signed)
            duplicate = self.client.post(path, content=body, headers=self._signed(config["secret"], body, "evt-1"))
        self.assertEqual(202, first.status_code, first.text)
        self.assertEqual(202, duplicate.status_code, duplicate.text)
        self.assertEqual(first.json()["fire_id"], duplicate.json()["fire_id"])
        self.assertTrue(duplicate.json()["duplicate"])

        fire = db.get_automation_fire(first.json()["fire_id"], LOCAL_USER_ID)
        self.assertEqual({"severity": "critical", "message": "disk full"}, fire.input_payload)
        self.assertIn("不可信的事实输入", scheduler._prompt_for_fire(db.get_automation(self.auto["id"]), fire))
        public_fire = self.client.get(
            f"/api/automation-fires?status=queued&automation_id={self.auto['id']}", headers=self.auth
        ).json()["fires"][0]
        self.assertNotIn("input_payload", public_fire)

        audit = self.client.get(
            f"/api/automations/{self.auto['id']}/webhook", headers=self.auth
        ).json()["deliveries"]
        self.assertEqual(1, len(audit))
        self.assertEqual("evt-1", audit[0]["idempotency_key"])
        self.assertEqual("queued", audit[0]["fire_status"])
        self.assertNotIn("message", audit[0])

        changed = json.dumps({"severity": "low"}, separators=(",", ":")).encode()
        conflict = self.client.post(
            path, content=changed, headers=self._signed(config["secret"], changed, "evt-1")
        )
        self.assertEqual(409, conflict.status_code)
        self.assertEqual(1, len(db.list_automation_fires(LOCAL_USER_ID)))

    def test_signature_window_rotation_owner_scope_and_trigger_gates_fail_closed(self) -> None:
        config = self._provision()
        body = b'{"event":"deploy"}'
        path = config["endpoint"]
        stale = self.client.post(
            path, content=body,
            headers=self._signed(config["secret"], body, "stale-1", int(time.time()) - 301),
        )
        self.assertEqual(401, stale.status_code)
        bad = self._signed(config["secret"], body, "bad-1")
        bad["X-AgentMate-Signature"] = "v1=" + "0" * 64
        self.assertEqual(401, self.client.post(path, content=body, headers=bad).status_code)
        self.assertEqual([], db.list_automation_fires(LOCAL_USER_ID))

        malformed = b"not-json"
        self.assertEqual(
            400,
            self.client.post(
                path, content=malformed,
                headers=self._signed(config["secret"], malformed, "malformed-1"),
            ).status_code,
        )
        oversized = b"{" + b'"x":"' + b"a" * (automations.WEBHOOK_MAX_BODY + 1) + b'"}'
        self.assertEqual(
            413,
            self.client.post(
                path, content=oversized,
                headers=self._signed(config["secret"], oversized, "oversized-1"),
            ).status_code,
        )

        rotated = self.client.post(
            f"/api/automations/{self.auto['id']}/webhook/rotate", headers=self.auth, json={}
        ).json()
        self.assertNotEqual(config["secret"], rotated["secret"])
        self.assertEqual(
            401,
            self.client.post(path, content=body, headers=self._signed(config["secret"], body, "old-1")).status_code,
        )

        other = db.create_user(name="webhook-other", password="1111")
        other_token = db.create_token(other.id)
        db.set_server_identity(other.id, other_token)
        other_auth = {"Authorization": f"Bearer {other_token}"}
        self.assertEqual(
            404,
            self.client.get(f"/api/automations/{self.auto['id']}/webhook", headers=other_auth).status_code,
        )

        self.client.patch(
            f"/api/automations/{self.auto['id']}", headers=self.auth,
            json={"trigger_kind": "interval", "interval_min": 60},
        )
        unavailable = self.client.post(
            path, content=body, headers=self._signed(rotated["secret"], body, "interval-1")
        )
        self.assertEqual(409, unavailable.status_code)

    def test_webhook_automations_are_never_selected_by_periodic_scan(self) -> None:
        db.get_conn().execute(
            "UPDATE automations SET next_run_at=0 WHERE id=?", (self.auto["id"],)
        )
        db.get_conn().commit()
        self.assertNotIn(self.auto["id"], [item.id for item in db.list_due_automations(time.time())])


if __name__ == "__main__":
    unittest.main()
