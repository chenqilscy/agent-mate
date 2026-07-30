"""WB-327: a single-use invite has exactly one concurrent winner."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import sys
import tempfile
import threading
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from config import settings  # noqa: E402
from models import Role  # noqa: E402


class InviteAcceptRaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        db._local = threading.local()
        db.init_db()
        self.owner = db.create_account(name="owner", password="password123")
        self.alice = db.create_account(name="alice", password="password123")
        self.bob = db.create_account(name="bob", password="password123")
        self.project = db.create_project(name="shared", owner_id=self.owner.id)
        self.invite = db.create_invite(
            project_id=self.project.id,
            role=Role.MEMBER,
            created_by=self.owner.id,
            ttl=3600,
        )

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        db._local = threading.local()
        self.tmp.cleanup()

    def test_concurrent_accept_has_one_member_and_one_conflict(self) -> None:
        barrier = threading.Barrier(2)

        def accept(account_id: str) -> bool:
            try:
                barrier.wait(timeout=5)
                return db.accept_invite_once(
                    self.invite.id,
                    self.project.id,
                    account_id,
                    Role.MEMBER,
                )
            finally:
                conn = getattr(db._local, "conn", None)
                if conn is not None:
                    conn.close()
                    db._local.conn = None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(accept, [self.alice.id, self.bob.id]))

        self.assertEqual([False, True], sorted(results))
        invite = db.get_invite_by_code(self.invite.code)
        self.assertIsNotNone(invite)
        members = {
            row["account_id"] for row in db.list_project_members(self.project.id)
            if not row["is_owner"]
        }
        self.assertEqual({invite.accepted_by}, members)


if __name__ == "__main__":
    unittest.main()
