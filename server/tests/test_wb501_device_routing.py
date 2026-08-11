"""WB-501 Console device readiness and deterministic automation routing."""
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
import run_protocol_store  # noqa: E402
from config import settings  # noqa: E402
from routers import business, run_protocol  # noqa: E402


CORE_CAPABILITIES = {
    "capabilities": ["run_events_v1", "llm.chat", "agent.tools"],
    "supported_tools": {"read_file": "1"},
    "max_parallel_runs": 1,
    "max_resident_runs": 4,
}


class DeviceRoutingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.DB_PATH
        self._close()
        settings.DB_PATH = Path(self.temp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        self.owner = db.create_account(name="owner-501", password="password123")
        token = db.create_token(self.owner.id)[0]
        app = FastAPI()
        app.include_router(business.router)
        app.include_router(run_protocol.router)
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

    def _device(self, suffix: str, *, verify: bool = True) -> run_protocol_store.DevicePrincipal | str:
        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        device_id = f"device-{suffix}-50100000"
        response = self.client.post("/api/devices/register", headers=self.auth, json={
            "device_id": device_id,
            "name": f"Agent {suffix}",
            "public_key": base64.b64encode(public).decode(),
            "protocol_version": 1,
            "app_version": "1.2.3",
            "platform": "windows",
            "arch": "x64",
            "capabilities": CORE_CAPABILITIES,
        })
        self.assertEqual(200, response.status_code, response.text)
        if not verify:
            return device_id
        challenge = response.json()["challenge"]
        signature = base64.b64encode(
            private.sign(challenge["challenge"].encode()),
        ).decode()
        verified = self.client.post(
            f"/api/devices/{device_id}/verify",
            headers=self.auth,
            json={"challenge_id": challenge["challenge_id"], "signature": signature},
        )
        self.assertEqual(200, verified.status_code, verified.text)
        return run_protocol_store.DevicePrincipal(
            device_id=device_id,
            owner_id=self.owner.id,
            capabilities=CORE_CAPABILITIES,
            protocol_version=1,
        )

    def _automation(self, routing_mode: str, target_device_id: str = "") -> dict:
        response = self.client.post("/api/automations", headers=self.auth, json={
            "name": f"route-{routing_mode}",
            "prompt": "执行设备路由验收",
            "trigger_kind": "interval",
            "interval_min": 60,
            "routing_mode": routing_mode,
            "target_device_id": target_device_id,
        })
        self.assertEqual(200, response.status_code, response.text)
        return response.json()["automation"]

    def test_specific_automation_is_leased_only_by_selected_device(self) -> None:
        selected = self._device("selected")
        other = self._device("other")
        assert isinstance(selected, run_protocol_store.DevicePrincipal)
        assert isinstance(other, run_protocol_store.DevicePrincipal)
        automation = self._automation("specific", selected.device_id)
        started = self.client.post(
            f"/api/automations/{automation['id']}/run", headers=self.auth,
        )
        self.assertEqual(200, started.status_code, started.text)
        self.assertEqual(selected.device_id, started.json()["run"]["target_device_id"])
        self.assertIsNone(run_protocol_store.lease_run(other, lease_seconds=30))
        lease = run_protocol_store.lease_run(selected, lease_seconds=30)
        self.assertIsNotNone(lease)
        self.assertEqual(started.json()["run"]["id"], lease["run"]["id"])

    def test_any_compatible_automation_can_be_leased_by_either_device(self) -> None:
        first = self._device("first")
        second = self._device("second")
        assert isinstance(first, run_protocol_store.DevicePrincipal)
        assert isinstance(second, run_protocol_store.DevicePrincipal)
        automation = self._automation("any_compatible")
        started = self.client.post(
            f"/api/automations/{automation['id']}/run", headers=self.auth,
        )
        self.assertEqual("", started.json()["run"]["target_device_id"])
        lease = run_protocol_store.lease_run(second, lease_seconds=30)
        self.assertIsNotNone(lease)
        self.assertEqual(started.json()["run"]["id"], lease["run"]["id"])

    def test_device_projection_and_target_validation_use_verified_owner_devices(self) -> None:
        verified = self._device("ready")
        unverified_id = self._device("unverified", verify=False)
        assert isinstance(verified, run_protocol_store.DevicePrincipal)
        response = self.client.get("/api/devices", headers=self.auth)
        self.assertEqual(200, response.status_code, response.text)
        by_id = {item["id"]: item for item in response.json()["devices"]}
        self.assertEqual("ready", by_id[verified.device_id]["readiness"])
        self.assertTrue(by_id[verified.device_id]["verified"])
        self.assertEqual({"active": 0, "parallel": 1, "resident": 0, "resident_limit": 4}, by_id[verified.device_id]["capacity"])
        self.assertEqual("unverified", by_id[str(unverified_id)]["readiness"])
        invalid = self.client.post("/api/automations", headers=self.auth, json={
            "name": "invalid target",
            "prompt": "不应创建",
            "routing_mode": "specific",
            "target_device_id": unverified_id,
        })
        self.assertEqual(400, invalid.status_code, invalid.text)
        self.assertIn("active verified device", invalid.text)


if __name__ == "__main__":
    unittest.main()
