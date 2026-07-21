"""Owner isolation for multi-assistant and channel routes (WB-285)."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from auth.deps import set_current_user_id  # noqa: E402
from config import settings  # noqa: E402
from routers import channels as channels_router  # noqa: E402
from storage import db  # noqa: E402


class AssistantOwnerIsolationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = settings.DB_PATH
        self._close_connection()
        settings.DB_PATH = Path(self.tmp.name) / "assistant-owner.db"
        db.init_db()
        self.alice = db.create_user(name="assistant-alice", password="pw")
        self.bob = db.create_user(name="assistant-bob", password="pw")

    def tearDown(self) -> None:
        set_current_user_id(None)
        self._close_connection()
        settings.DB_PATH = self.old_db
        self.tmp.cleanup()

    @staticmethod
    def _close_connection() -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
            db._local.conn = None

    async def test_accounts_only_list_and_mutate_their_own_assistants(self) -> None:
        with patch.object(channels_router.manager, "refresh", new=AsyncMock()):
            set_current_user_id(self.alice.id)
            alice_assistant = await channels_router.create_assistant(
                channels_router.AssistantBody(name="Alice helper")
            )
            set_current_user_id(self.bob.id)
            bob_assistant = await channels_router.create_assistant(
                channels_router.AssistantBody(name="Bob helper")
            )

            self.assertEqual(["Bob helper"], [item["name"] for item in channels_router.list_assistants()["assistants"]])
            self.assertEqual(self.bob.id, db.get_assistant(bob_assistant["id"])["owner_id"])
            with self.assertRaises(HTTPException) as read_error:
                channels_router.get_assistant(alice_assistant["id"])
            self.assertEqual(404, read_error.exception.status_code)
            with self.assertRaises(HTTPException) as update_error:
                await channels_router.update_assistant(
                    alice_assistant["id"], channels_router.AssistantBody(name="stolen")
                )
            self.assertEqual(404, update_error.exception.status_code)
            with self.assertRaises(HTTPException) as channel_error:
                await channels_router.add_channel(
                    alice_assistant["id"], channels_router.ChannelBody(type="telegram")
                )
            self.assertEqual(404, channel_error.exception.status_code)

            set_current_user_id(self.alice.id)
            self.assertEqual(["Alice helper"], [item["name"] for item in channels_router.list_assistants()["assistants"]])


if __name__ == "__main__":
    unittest.main()
