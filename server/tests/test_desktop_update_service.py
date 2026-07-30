"""Production desktop updater rollout and rollback contract (WB-257)."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from config import settings  # noqa: E402
import update_store  # noqa: E402


class DesktopUpdateServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        self.old_dedupe = settings.UPDATE_EVENT_DEDUPE_SECONDS
        self.old_retention = settings.UPDATE_EVENT_RETENTION_SECONDS
        self.old_max_rows = settings.UPDATE_EVENT_MAX_ROWS
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        update_store.ensure_tables()

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        settings.UPDATE_EVENT_DEDUPE_SECONDS = self.old_dedupe
        settings.UPDATE_EVENT_RETENTION_SECONDS = self.old_retention
        settings.UPDATE_EVENT_MAX_ROWS = self.old_max_rows
        db._local = threading.local()
        self.tmp.cleanup()

    @staticmethod
    def artifact(target: str = "windows", arch: str = "x86_64") -> dict:
        return {
            "target": target,
            "arch": arch,
            "url": f"https://updates.example.invalid/{target}/{arch}/bundle.zip",
            "signature": "signed:" + "A" * 80,
            "sha256": "a" * 64,
            "size_bytes": 1024,
        }

    def release(self, version: str, channel: str = "stable") -> dict:
        return update_store.create_release(
            version=version, channel=channel, notes=f"release {version}",
            artifacts=[self.artifact()], created_by="admin",
        )

    def test_immutable_release_validation_and_duplicate_version(self) -> None:
        release = self.release("1.1.0")
        self.assertEqual("draft", release["state"])
        self.assertEqual("a" * 64, release["artifacts"][0]["sha256"])
        with self.assertRaises(Exception):
            self.release("1.1.0")
        bad = self.artifact()
        bad["url"] = "http://updates.example.invalid/bundle.zip"
        with self.assertRaisesRegex(ValueError, "https"):
            update_store.create_release(
                version="1.2.0", channel="stable", notes="", artifacts=[bad], created_by="admin",
            )

    def test_stable_rollout_is_deterministic_and_minimum_version_forces_offer(self) -> None:
        release = self.release("2.0.0")
        state = update_store.publish_release(
            release["id"], rollout_percent=1, min_supported_version="1.5.0",
        )
        salt = state["rollout_salt"]
        outside = next(
            f"device-{i:04d}" for i in range(10000)
            if update_store._bucket(f"device-{i:04d}", salt) >= 1
        )
        self.assertIsNone(update_store.select_update(
            channel="stable", target="windows", arch="x86_64",
            current_version="1.9.0", device_id=outside,
        ))
        forced = update_store.select_update(
            channel="stable", target="windows", arch="x86_64",
            current_version="1.0.0", device_id=outside,
        )
        self.assertEqual("2.0.0", forced["version"])
        self.assertTrue(forced["forced"])
        again = update_store.select_update(
            channel="stable", target="windows", arch="x86_64",
            current_version="1.0.0", device_id=outside,
        )
        self.assertEqual(forced["release_id"], again["release_id"])

    def test_pause_and_signed_rollback_are_deterministic(self) -> None:
        old = self.release("1.5.0")
        update_store.publish_release(old["id"], rollout_percent=100, min_supported_version="1.0.0")
        new = self.release("2.0.0")
        update_store.publish_release(new["id"], rollout_percent=100, min_supported_version="1.0.0")
        device = "device-rollback-001"
        self.assertEqual("2.0.0", update_store.select_update(
            channel="stable", target="windows", arch="x86_64",
            current_version="1.5.0", device_id=device,
        )["version"])
        update_store.pause_channel("stable", True)
        self.assertIsNone(update_store.select_update(
            channel="stable", target="windows", arch="x86_64",
            current_version="1.5.0", device_id=device,
        ))
        update_store.rollback_channel("stable", old["id"])
        rollback = update_store.select_update(
            channel="stable", target="windows", arch="x86_64",
            current_version="2.0.0", device_id=device,
        )
        self.assertEqual("1.5.0", rollback["version"])
        self.assertTrue(rollback["rollback"])

    def test_events_hash_device_and_never_store_raw_identifier(self) -> None:
        update_store.record_event(
            device_id="device-private-123", channel="beta", event="install_failed",
            current_version="1.0.0", error_code="signature_invalid",
        )
        row = db.get_conn().execute("SELECT * FROM desktop_update_events").fetchone()
        self.assertNotEqual("device-private-123", row["device_hash"])
        self.assertEqual(64, len(row["device_hash"]))
        self.assertEqual("signature_invalid", row["error_code"])
        serialized = str(dict(row))
        self.assertNotIn("device-private-123", serialized)

    def test_events_are_deduplicated_and_hard_capped(self) -> None:
        settings.UPDATE_EVENT_DEDUPE_SECONDS = 3600
        settings.UPDATE_EVENT_MAX_ROWS = 3
        self.assertTrue(update_store.record_event(
            device_id="device-dedupe-001", channel="stable", event="check",
        ))
        self.assertFalse(update_store.record_event(
            device_id="device-dedupe-001", channel="stable", event="check",
        ))
        self.assertEqual(
            1,
            db.get_conn().execute("SELECT COUNT(*) FROM desktop_update_events").fetchone()[0],
        )

        for index in range(5):
            update_store.record_event(
                device_id=f"device-cap-{index:03d}",
                channel="beta",
                event="install_failed",
                error_code=f"error-{index}",
            )
        rows = db.get_conn().execute(
            "SELECT error_code FROM desktop_update_events ORDER BY created_at,id"
        ).fetchall()
        self.assertEqual(3, len(rows))
        self.assertEqual({"error-2", "error-3", "error-4"}, {row["error_code"] for row in rows})


if __name__ == "__main__":
    unittest.main()
