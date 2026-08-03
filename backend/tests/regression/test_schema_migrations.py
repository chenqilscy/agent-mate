"""WB-363: App schema migrations are ordered, idempotent, and transactional."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from config import settings  # noqa: E402
from storage import db  # noqa: E402
from storage.migrations import (  # noqa: E402
    Migration,
    migrate_message_run_link,
    migrate_model_and_run_audit,
    run_migrations,
)


class AppSchemaMigrationTest(unittest.TestCase):
    def test_empty_then_current_database_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            old_path = settings.DB_PATH
            settings.DB_PATH = Path(temp) / "app.db"
            db._local = threading.local()
            try:
                db.init_db()
                db.init_db()
                rows = db.get_conn().execute(
                    "SELECT version,name FROM schema_migrations WHERE scope='app' ORDER BY version"
                ).fetchall()
                self.assertEqual([1, 2, 3], [row["version"] for row in rows])
            finally:
                db.close_thread_connection()
                settings.DB_PATH = old_path
                db._local = threading.local()

    def test_old_fixture_adds_recent_audit_columns(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.executescript(
            "CREATE TABLE model_meta(id TEXT); CREATE TABLE runs(id TEXT); "
            "CREATE TABLE messages(id TEXT);"
        )
        migrations = (
            Migration(1, "existing-schema-baseline", lambda _conn: None),
            Migration(2, "model-and-run-audit", migrate_model_and_run_audit),
            Migration(3, "message-run-link", migrate_message_run_link),
        )
        run_migrations(conn, migrations)
        run_migrations(conn, migrations)
        self.assertIn("max_output_tokens", {row[1] for row in conn.execute("PRAGMA table_info(model_meta)")})
        self.assertIn("model_snapshot", {row[1] for row in conn.execute("PRAGMA table_info(runs)")})
        self.assertIn("run_id", {row[1] for row in conn.execute("PRAGMA table_info(messages)")})
        self.assertEqual(3, conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
