"""WB-477: diagnostics are owner-scoped and recovery cannot discard unacked WAL."""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

import local_agent_store  # noqa: E402
from config import settings  # noqa: E402


class DeviceDiagnosticsStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.LOCAL_AGENT_DB_PATH
        local_agent_store.close_thread_connection()
        settings.LOCAL_AGENT_DB_PATH = Path(self.temp.name) / "core.db"
        local_agent_store.init_db()

    def tearDown(self) -> None:
        local_agent_store.close_thread_connection()
        settings.LOCAL_AGENT_DB_PATH = self.old_path
        self.temp.cleanup()

    def test_snapshot_filters_owner_and_cleanup_only_removes_acked_terminal_leases(self) -> None:
        now = time.time()
        conn = local_agent_store.get_conn()
        for run_id, owner_id, status in (
            ("run-complete", "owner-a", "completed"),
            ("run-active", "owner-a", "active"),
            ("run-other", "owner-b", "active"),
        ):
            conn.execute(
                "INSERT INTO run_transport_leases "
                "(run_id,owner_id,device_id,lease_id,lease_epoch,expires_at,ack_high_water,status,last_error,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (run_id, owner_id, "device", f"lease-{run_id}", 1, now + 60, 0, status, "", now),
            )
        conn.execute(
            "INSERT INTO run_event_wal "
            "(event_id,run_id,owner_id,device_id,lease_id,lease_epoch,sequence,event_type,occurred_at,payload,payload_hash,byte_size,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("event-active", "run-active", "owner-a", "device", "lease-run-active", 1, 1, "ui.text", now, "{}", "a" * 64, 2, now),
        )
        conn.commit()
        snapshot = local_agent_store.diagnostics_snapshot("owner-a")
        self.assertEqual({"run-complete", "run-active"}, {item["run_id"] for item in snapshot["leases"]})
        self.assertEqual(1, snapshot["wal"]["count"])
        self.assertEqual(1, local_agent_store.clear_completed_transport("owner-a"))
        self.assertEqual(1, local_agent_store.diagnostics_snapshot("owner-a")["wal"]["count"])
        self.assertIsNotNone(conn.execute("SELECT 1 FROM run_transport_leases WHERE run_id='run-active'").fetchone())
        self.assertIsNotNone(conn.execute("SELECT 1 FROM run_transport_leases WHERE run_id='run-other'").fetchone())


if __name__ == "__main__":
    unittest.main()
