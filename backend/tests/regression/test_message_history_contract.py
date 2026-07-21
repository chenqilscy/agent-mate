"""Message history persistence contract (WB-277)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from config import settings  # noqa: E402
from storage import db  # noqa: E402
from storage.models import LOCAL_USER_ID  # noqa: E402


class MessageHistoryContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self._close_connection()
        settings.DB_PATH = Path(self.tmp.name) / "agentmate-test.db"
        db.init_db()
        self.session = db.create_session(owner_id=LOCAL_USER_ID, title="history")

    def tearDown(self) -> None:
        self._close_connection()
        settings.DB_PATH = self.old_db
        self.tmp.cleanup()

    @staticmethod
    def _close_connection() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None

    def test_empty_session_returns_empty_list(self) -> None:
        self.assertEqual([], db.list_messages(self.session.id))

    def test_messages_are_ordered_and_decode_trace_and_usage(self) -> None:
        first = db.add_message(
            session_id=self.session.id, role="user", content="hello", actor=LOCAL_USER_ID,
        )
        second = db.add_message(
            session_id=self.session.id, role="assistant", content="world", actor="assistant",
            trace=[{"kind": "step", "tool": "read_file"}], usage={"prompt": 3, "completion": 1},
        )

        messages = db.list_messages(self.session.id)
        self.assertEqual([first.id, second.id], [message.id for message in messages])
        self.assertEqual([], messages[0].trace)
        self.assertIsNone(messages[0].usage)
        self.assertEqual([{"kind": "step", "tool": "read_file"}], messages[1].trace)
        self.assertEqual({"prompt": 3, "completion": 1}, messages[1].usage)


if __name__ == "__main__":
    unittest.main()
