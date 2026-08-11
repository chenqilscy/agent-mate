"""WB-363: Server schema migration upgrade and failure contracts."""
from __future__ import annotations

import hashlib
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER))

import db  # noqa: E402
from config import settings  # noqa: E402
from migrations import Migration, migrate_federated_identity_security, run_migrations  # noqa: E402


class ServerSchemaMigrationTest(unittest.TestCase):
    def test_empty_then_current_database_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            old_path = settings.DB_PATH
            settings.DB_PATH = Path(temp) / "server.db"
            db._local = threading.local()
            try:
                db.init_db()
                db.init_db()
                rows = db.get_conn().execute(
                    "SELECT version,name FROM schema_migrations WHERE scope='server' ORDER BY version"
                ).fetchall()
                self.assertEqual(
                    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18],
                    [row["version"] for row in rows],
                )
            finally:
                conn = getattr(db._local, "conn", None)
                if conn is not None:
                    conn.close()
                settings.DB_PATH = old_path
                db._local = threading.local()

    def test_old_fixture_hashes_tokens_and_adds_sso_login_flag(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.executescript(
            "CREATE TABLE accounts(id TEXT PRIMARY KEY); "
            "CREATE TABLE server_tokens(token TEXT PRIMARY KEY); "
            "INSERT INTO accounts(id) VALUES ('a1'); "
            "INSERT INTO server_tokens(token) VALUES ('legacy-token');"
        )
        migrations = (
            Migration(1, "existing-schema-baseline", lambda _conn: None),
            Migration(2, "federated-identity-security", migrate_federated_identity_security),
        )
        run_migrations(conn, migrations)
        run_migrations(conn, migrations)
        expected = "sha256:" + hashlib.sha256(b"legacy-token").hexdigest()
        self.assertEqual(expected, conn.execute("SELECT token FROM server_tokens").fetchone()[0])
        self.assertIn("password_login_enabled", {row[1] for row in conn.execute("PRAGMA table_info(accounts)")})

    def test_failed_migration_rolls_back_and_is_not_recorded(self) -> None:
        conn = sqlite3.connect(":memory:")

        def fail(db_conn: sqlite3.Connection) -> None:
            db_conn.execute("CREATE TABLE should_rollback(id INTEGER)")
            raise RuntimeError("boom")

        with self.assertRaisesRegex(RuntimeError, "boom"):
            run_migrations(conn, (Migration(1, "fails", fail),))
        self.assertIsNone(conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='should_rollback'"
        ).fetchone())
        self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
