"""WB-291: device settings are typed, hot-reloaded, masked and audited."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

import device_settings  # noqa: E402
from auth.deps import set_current_user_id  # noqa: E402
from config import settings  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from routers import device_settings as router  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class DeviceSettingsGovernanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self.old_values = {item.setting_attr: getattr(settings, item.setting_attr) for item in device_settings.DEFINITIONS}
        settings.DB_PATH = Path(self.tmp.name) / "app.db"
        db._local = threading.local(); db.init_db(); set_current_user_id(None)

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_db
        for key, value in self.old_values.items():
            setattr(settings, key, value)
        db._local = threading.local(); set_current_user_id(None); self.tmp.cleanup()

    @patch("routers.asr.reset_model")
    @patch("agent.telemetry.reconfigure")
    def test_save_hot_reloads_masks_secret_and_audits(self, telemetry_reset, asr_reset) -> None:
        result = router.put_runtime_settings(router.UpdateBody(values={
            "observability.enabled": True,
            "observability.base_url": "http://langfuse.local:3000/",
            "observability.public_key": "pk-public",
            "observability.secret_key": "sk-private-value",
            "observability.sample_rate": 0.5,
            "voice.asr_model": "small",
            "collaboration.server_url": "http://server.local:8100/",
            "collaboration.timeline_upload": True,
        }))
        self.assertTrue(settings.LANGFUSE_ENABLED)
        self.assertEqual("http://langfuse.local:3000", settings.LANGFUSE_BASE_URL)
        self.assertEqual("small", settings.ASR_MODEL)
        self.assertEqual("http://server.local:8100", settings.AGENTMATE_SERVER_URL)
        self.assertTrue(settings.AGENTMATE_SERVER_TIMELINE_UPLOAD)
        self.assertNotIn("sk-private-value", repr(result))
        self.assertNotIn("sk-private-value", repr(db.list_device_settings_audit()))
        telemetry_reset.assert_called_once(); asr_reset.assert_called_once()

    def test_validation_is_atomic_and_deployment_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(HTTPException, "启动级配置"):
            router.put_runtime_settings(router.UpdateBody(values={
                "voice.asr_model": "small",
                "runtime.database_path": "other.db",
            }))
        self.assertIsNone(db.get_device_setting("voice.asr_model"))
        with self.assertRaisesRegex(HTTPException, "采样率"):
            router.put_runtime_settings(router.UpdateBody(values={
                "observability.sample_rate": 2,
            }))
        with self.assertRaisesRegex(HTTPException, "有限数字"):
            router.put_runtime_settings(router.UpdateBody(values={
                "observability.sample_rate": float("nan"),
            }))

    @patch("routers.asr.reset_model")
    @patch("agent.telemetry.reconfigure")
    def test_clear_returns_to_bootstrap_source(self, _telemetry_reset, _asr_reset) -> None:
        router.put_runtime_settings(router.UpdateBody(values={"voice.asr_model": "small"}))
        result = router.put_runtime_settings(router.UpdateBody(clear=["voice.asr_model"]))
        item = next(row for row in result["items"] if row["key"] == "voice.asr_model")
        self.assertNotEqual("database", item["source"])
        self.assertEqual(device_settings._BOOTSTRAP["ASR_MODEL"], settings.ASR_MODEL)
        self.assertEqual(LOCAL_USER_ID, db.list_device_settings_audit()[0]["actor_id"])

    def test_device_owner_is_not_derived_from_mirrored_business_role(self) -> None:
        db.upsert_external_user("alice", "Alice")
        db.upsert_external_user("bob", "Bob")
        set_current_user_id("alice")
        self.assertEqual("alice", router._owner().id)
        self.assertEqual("alice", db.get_device_owner_id())

        set_current_user_id("bob")
        with self.assertRaises(HTTPException) as other:
            router._owner()
        self.assertEqual(403, other.exception.status_code)

        set_current_user_id(None)
        with self.assertRaises(HTTPException) as guest:
            router._owner()
        self.assertEqual(403, guest.exception.status_code)

        set_current_user_id("alice")
        self.assertEqual("alice", router._owner().id)


if __name__ == "__main__":
    unittest.main()
