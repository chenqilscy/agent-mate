"""Terminal relay payload and row retention (WB-370)."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
import relay_store  # noqa: E402
from config import settings  # noqa: E402


class RelayRetentionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.DB_PATH
        self.old_payload = settings.RELAY_PAYLOAD_RETENTION_SECONDS
        self.old_terminal = settings.RELAY_TERMINAL_RETENTION_SECONDS
        self.old_cap = settings.RELAY_MAX_TERMINAL_ROWS_PER_OWNER
        settings.DB_PATH = Path(self.temp.name) / "server.db"
        settings.RELAY_PAYLOAD_RETENTION_SECONDS = 10
        settings.RELAY_TERMINAL_RETENTION_SECONDS = 100
        settings.RELAY_MAX_TERMINAL_ROWS_PER_OWNER = 2
        db._local = threading.local()
        db.init_db()
        self.owner = db.create_account(name="owner", password="password-for-tests")
        self.service, _token = relay_store.create_service_account(
            self.owner.id, "relay", ["relay:read", "relay:write"],
        )

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        db._local = threading.local()
        settings.DB_PATH = self.old_path
        settings.RELAY_PAYLOAD_RETENTION_SECONDS = self.old_payload
        settings.RELAY_TERMINAL_RETENTION_SECONDS = self.old_terminal
        settings.RELAY_MAX_TERMINAL_ROWS_PER_OWNER = self.old_cap
        self.temp.cleanup()

    def _event(self, event_id: str, status: str, timestamp: float) -> None:
        db.get_conn().execute(
            "INSERT INTO relay_events "
            "(id,service_account_id,owner_id,device_id,automation_id,event_key,payload,"
            "payload_sha256,status,max_attempts,available_at,created_at,updated_at,acknowledged_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id, self.service["id"], self.owner.id, "device-test-0001", "auto-1",
             event_id, json.dumps({"secret": event_id}), "hash", status, 5, timestamp,
             timestamp, timestamp, timestamp if status not in {"pending", "leased"} else None),
        )
        db.get_conn().commit()

    def test_pending_is_preserved_payload_is_tombstoned_and_old_rows_are_deleted(self) -> None:
        now = time.time()
        self._event("pending", "pending", now - 1000)
        self._event("tombstone", "succeeded", now - 20)
        self._event("delete", "failed", now - 200)

        result = relay_store.cleanup_terminal_events(now)
        self.assertEqual(1, result["payloads_tombstoned"])
        self.assertEqual(1, result["rows_deleted"])
        pending = db.get_conn().execute(
            "SELECT payload FROM relay_events WHERE id='pending'"
        ).fetchone()
        terminal = db.get_conn().execute(
            "SELECT payload,payload_tombstoned_at FROM relay_events WHERE id='tombstone'"
        ).fetchone()
        self.assertIn("secret", pending["payload"])
        self.assertEqual("{}", terminal["payload"])
        self.assertIsNotNone(terminal["payload_tombstoned_at"])
        self.assertIsNone(db.get_conn().execute(
            "SELECT 1 FROM relay_events WHERE id='delete'"
        ).fetchone())

    def test_per_owner_cap_keeps_newest_terminal_rows(self) -> None:
        now = time.time()
        self._event("oldest", "succeeded", now - 3)
        self._event("middle", "failed", now - 2)
        self._event("newest", "dead_letter", now - 1)
        result = relay_store.cleanup_terminal_events(now)
        self.assertEqual(1, result["rows_deleted"])
        remaining = {row[0] for row in db.get_conn().execute(
            "SELECT id FROM relay_events ORDER BY id"
        ).fetchall()}
        self.assertEqual({"middle", "newest"}, remaining)


if __name__ == "__main__":
    unittest.main()
