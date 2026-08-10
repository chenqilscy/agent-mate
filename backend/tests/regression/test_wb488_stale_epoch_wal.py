"""WB-488 superseded lease epochs must not remain in the retryable WAL."""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

import local_agent_store as db
import run_transport
from config import settings


class SupersededEpochWalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_path = settings.LOCAL_AGENT_DB_PATH
        self._close()
        settings.LOCAL_AGENT_DB_PATH = Path(self.temp.name) / "local-agent.db"
        db._local = threading.local()
        db.init_db()
        self.owner_id = "owner-wb488"
        self.run_id = "run-wb488"
        self._record(epoch=1, lease_id="lease-one")

    def tearDown(self) -> None:
        self._close()
        settings.LOCAL_AGENT_DB_PATH = self.old_path
        db._local = threading.local()
        self.temp.cleanup()

    @staticmethod
    def _close() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        db._local = threading.local()

    def _record(self, *, epoch: int, lease_id: str) -> None:
        run_transport.record_lease(self.owner_id, {
            "lease_id": lease_id,
            "lease_epoch": epoch,
            "expires_at": 9999999999,
            "ack_high_water": 0,
            "run": {"id": self.run_id},
        })

    def test_new_epoch_retires_old_wal_but_same_epoch_preserves_it(self) -> None:
        old_event = run_transport.append_event(self.run_id, "ui.text", {"md": "old"})
        self.assertEqual(1, db.status_snapshot()["wal"]["count"])

        self._record(epoch=2, lease_id="lease-two")

        self.assertEqual(0, db.status_snapshot()["wal"]["count"])
        retired = db.get_conn().execute(
            "SELECT event_id,lease_epoch,retired_reason,superseded_by_epoch "
            "FROM retired_run_event_wal WHERE run_id=?",
            (self.run_id,),
        ).fetchone()
        self.assertEqual(old_event["event_id"], retired["event_id"])
        self.assertEqual(1, retired["lease_epoch"])
        self.assertEqual("lease_epoch_superseded", retired["retired_reason"])
        self.assertEqual(2, retired["superseded_by_epoch"])

        current_event = run_transport.append_event(self.run_id, "ui.text", {"md": "current"})
        self._record(epoch=2, lease_id="lease-two")
        active = db.get_conn().execute(
            "SELECT event_id,lease_epoch FROM run_event_wal WHERE run_id=?", (self.run_id,),
        ).fetchall()
        self.assertEqual([(current_event["event_id"], 2)], [(row["event_id"], row["lease_epoch"]) for row in active])

        with self.assertRaisesRegex(run_transport.LeaseFenced, "moved backwards"):
            self._record(epoch=1, lease_id="stale-lease")
        lease = db.get_conn().execute(
            "SELECT lease_id,lease_epoch FROM run_transport_leases WHERE run_id=?", (self.run_id,),
        ).fetchone()
        self.assertEqual(("lease-two", 2), (lease["lease_id"], lease["lease_epoch"]))

    def test_startup_reconciles_rows_left_by_previous_version(self) -> None:
        old_event = run_transport.append_event(self.run_id, "ui.text", {"md": "legacy"})
        db.get_conn().execute(
            "UPDATE run_transport_leases SET lease_id='lease-two',lease_epoch=2 WHERE run_id=?",
            (self.run_id,),
        )
        db.get_conn().commit()

        self._close()
        db.init_db()

        self.assertEqual(0, db.status_snapshot()["wal"]["count"])
        retired = db.get_conn().execute(
            "SELECT event_id,superseded_by_epoch FROM retired_run_event_wal WHERE run_id=?",
            (self.run_id,),
        ).fetchone()
        self.assertEqual((old_event["event_id"], 2), (retired["event_id"], retired["superseded_by_epoch"]))


if __name__ == "__main__":
    unittest.main()
