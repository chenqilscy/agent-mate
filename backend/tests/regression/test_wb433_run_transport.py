"""WB-433 local WAL persistence, capacity and continuous ACK deletion gates."""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import run_transport
import local_agent_store as db
from config import settings


class LocalRunTransportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.LOCAL_AGENT_DB_PATH
        self.old_cap = settings.RUN_EVENT_WAL_MAX_BYTES
        self._close()
        settings.LOCAL_AGENT_DB_PATH = Path(self.temp.name) / "local-agent.db"
        settings.RUN_EVENT_WAL_MAX_BYTES = 1024 * 1024
        db._local = threading.local()
        db.init_db()
        self.owner_id = "owner-wb433"
        self.run_id = "run-wb433"
        run_transport.record_lease(self.owner_id, {
            "lease_id": "lease-wb433", "lease_epoch": 1, "expires_at": 9999999999,
            "ack_high_water": 0, "run": {"id": self.run_id},
        })

    def tearDown(self) -> None:
        self._close()
        settings.LOCAL_AGENT_DB_PATH = self.old_path
        settings.RUN_EVENT_WAL_MAX_BYTES = self.old_cap
        db._local = threading.local()
        self.temp.cleanup()

    @staticmethod
    def _close() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None

    def _rows(self):
        return db.get_conn().execute(
            "SELECT * FROM run_event_wal WHERE run_id=? ORDER BY sequence", (self.run_id,),
        ).fetchall()

    def test_disconnect_restart_gap_resend_and_ack_only_delete(self) -> None:
        first = run_transport.append_event(self.run_id, "run.started")
        second = run_transport.append_event(self.run_id, "run.checkpoint", {"cursor": 2})
        self.assertEqual([1, 2], [first["sequence"], second["sequence"]])

        with patch("server_client.device_post", return_value=(0, None)):
            result = run_transport.flush_wal(self.owner_id, "device-token")
        self.assertEqual(0, result["acknowledged"])
        self.assertEqual(2, len(self._rows()))

        # A process/connection restart must not lose unacknowledged events.
        self._close()
        db._local = threading.local()
        db.init_db()
        self.assertEqual([1, 2], [row["sequence"] for row in self._rows()])

        gap = {"detail": {"code": "event_sequence_gap", "expected_sequence": 1}}
        with patch("server_client.device_post", return_value=(409, gap)):
            run_transport.flush_wal(self.owner_id, "device-token")
        self.assertEqual("active", db.get_conn().execute(
            "SELECT status FROM run_transport_leases WHERE run_id=?", (self.run_id,),
        ).fetchone()[0])
        self.assertEqual(2, len(self._rows()))

        with patch("server_client.device_post", return_value=(200, {"ack_high_water": 1, "commands": []})):
            first_ack = run_transport.flush_wal(self.owner_id, "device-token")
        self.assertEqual(1, first_ack["acknowledged"])
        self.assertEqual([2], [row["sequence"] for row in self._rows()])

        # Duplicate/retry semantics are driven by the Server high-water; only
        # rows at or below that continuous ACK may be removed.
        with patch("server_client.device_post", return_value=(200, {"ack_high_water": 2, "commands": []})):
            second_ack = run_transport.flush_wal(self.owner_id, "device-token")
        self.assertEqual(1, second_ack["acknowledged"])
        self.assertEqual([], self._rows())

    def test_wal_capacity_blocks_without_dropping_and_missing_gap_fences(self) -> None:
        settings.RUN_EVENT_WAL_MAX_BYTES = 600
        with self.assertRaisesRegex(ValueError, "credentials or secrets"):
            run_transport.append_event(self.run_id, "run.checkpoint", {"access_token": "nope"})
        self.assertEqual([], self._rows())
        first = run_transport.append_event(self.run_id, "run.checkpoint", {"text": "x" * 150})
        with self.assertRaises(run_transport.WalCapacityExceeded):
            run_transport.append_event(self.run_id, "run.checkpoint", {"text": "y" * 150})
        self.assertEqual([first["event_id"]], [row["event_id"] for row in self._rows()])

        # If corruption/manual deletion makes the Server-requested sequence
        # unavailable, fail closed instead of pretending later events were ACKed.
        db.get_conn().execute("DELETE FROM run_event_wal")
        db.get_conn().execute(
            "UPDATE run_transport_leases SET ack_high_water=1 WHERE run_id=?", (self.run_id,),
        )
        db.get_conn().commit()
        run_transport.append_event(self.run_id, "run.checkpoint", {"cursor": 2})
        gap = {"detail": {"code": "event_sequence_gap", "expected_sequence": 1}}
        with patch("server_client.device_post", return_value=(409, gap)):
            run_transport.flush_wal(self.owner_id, "device-token")
        lease = db.get_conn().execute(
            "SELECT status,last_error FROM run_transport_leases WHERE run_id=?", (self.run_id,),
        ).fetchone()
        self.assertEqual("fenced", lease["status"])
        self.assertIn("missing sequence 1", lease["last_error"])
        self.assertEqual(1, len(self._rows()))


if __name__ == "__main__":
    unittest.main()
