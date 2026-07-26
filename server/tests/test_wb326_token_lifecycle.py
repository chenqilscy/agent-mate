"""WB-326 Server token expiry and revocation contract."""
from __future__ import annotations

import sys
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from config import settings  # noqa: E402


class ServerTokenLifecycleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = settings.DB_PATH
        self.old_ttl = settings.TOKEN_TTL_SECONDS
        settings.DB_PATH = Path(self.tmp.name) / "server.db"
        settings.TOKEN_TTL_SECONDS = 120
        db._local = threading.local()
        db.init_db()
        self.account = db.create_account(name="alice", password="password123")

    def tearDown(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        settings.DB_PATH = self.old_path
        settings.TOKEN_TTL_SECONDS = self.old_ttl
        db._local = threading.local()
        self.tmp.cleanup()

    def test_new_token_has_expiry_and_expired_token_is_deleted(self) -> None:
        before = time.time()
        token, expires_at = db.create_token(self.account.id)
        self.assertGreaterEqual(expires_at, before + 119)
        self.assertEqual(self.account.id, db.account_id_for_token(token))
        self.assertEqual(expires_at, db.token_expires_at(token))

        db.get_conn().execute(
            "UPDATE server_tokens SET expires_at=? WHERE token=?", (time.time() - 1, token)
        )
        db.get_conn().commit()
        self.assertIsNone(db.account_id_for_token(token))
        self.assertIsNone(db.get_conn().execute(
            "SELECT 1 FROM server_tokens WHERE token=?", (token,)
        ).fetchone())

    def test_delete_token_is_idempotent(self) -> None:
        token, _ = db.create_token(self.account.id)
        db.delete_token(token)
        db.delete_token(token)
        self.assertIsNone(db.account_id_for_token(token))

    def test_legacy_token_gets_bounded_compatibility_expiry(self) -> None:
        conn = getattr(db._local, "conn", None)
        if conn is not None:
            conn.close()
        legacy_path = Path(self.tmp.name) / "legacy.db"
        raw = sqlite3.connect(legacy_path)
        raw.execute(
            "CREATE TABLE server_tokens "
            "(token TEXT PRIMARY KEY, account_id TEXT NOT NULL, created_at REAL NOT NULL)"
        )
        raw.execute(
            "INSERT INTO server_tokens (token,account_id,created_at) VALUES (?,?,?)",
            ("legacy-token", self.account.id, time.time() - 86400),
        )
        raw.commit()
        raw.close()

        settings.DB_PATH = legacy_path
        db._local = threading.local()
        before = time.time()
        db.init_db()
        expires_at = db.get_conn().execute(
            "SELECT expires_at FROM server_tokens WHERE token='legacy-token'"
        ).fetchone()["expires_at"]
        compatibility_window = min(
            settings.TOKEN_TTL_SECONDS, settings.TOKEN_LEGACY_GRACE_SECONDS
        )
        self.assertGreaterEqual(expires_at, before + compatibility_window - 1)
        self.assertLessEqual(
            expires_at,
            before + compatibility_window + 1,
        )
        db.init_db()  # migration is idempotent


if __name__ == "__main__":
    unittest.main()
