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
    migrate_artifact_presentation,
    migrate_connector_companion_skill,
    migrate_message_run_link,
    migrate_model_and_run_audit,
    migrate_project_org_scope,
    migrate_run_plan_version,
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
                self.assertEqual([1, 2, 3, 4, 5, 6, 7, 8], [row["version"] for row in rows])
                db._assert_app_schema(db.get_conn())
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
            Migration(4, "legacy-schema-completion", lambda _conn: None),
            Migration(5, "durable-run-plan-version", migrate_run_plan_version),
            Migration(6, "project-org-model-policy-scope", migrate_project_org_scope),
            Migration(7, "artifact-presentation-authority", migrate_artifact_presentation),
            Migration(8, "connector-companion-skill", migrate_connector_companion_skill),
        )
        run_migrations(conn, migrations)
        run_migrations(conn, migrations)
        self.assertIn("max_output_tokens", {row[1] for row in conn.execute("PRAGMA table_info(model_meta)")})
        self.assertIn("model_snapshot", {row[1] for row in conn.execute("PRAGMA table_info(runs)")})
        self.assertIn("plan_version", {row[1] for row in conn.execute("PRAGMA table_info(runs)")})
        self.assertIn("run_id", {row[1] for row in conn.execute("PRAGMA table_info(messages)")})
        self.assertEqual(8, conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0])

    def test_legacy_artifacts_gain_one_primary_and_stable_order(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.execute(
            """CREATE TABLE artifacts (
                   id TEXT PRIMARY KEY,run_id TEXT NOT NULL,created_at REAL NOT NULL
               )"""
        )
        conn.executemany(
            "INSERT INTO artifacts(id,run_id,created_at) VALUES (?,?,?)",
            [("b", "run-1", 2), ("a", "run-1", 1), ("c", "run-2", 1)],
        )
        migrate_artifact_presentation(conn)
        migrate_artifact_presentation(conn)
        rows = conn.execute(
            "SELECT id,run_id,is_primary,display_order FROM artifacts "
            "ORDER BY run_id,display_order"
        ).fetchall()
        self.assertEqual(
            [("a", "run-1", 1, 0), ("b", "run-1", 0, 1), ("c", "run-2", 1, 0)],
            rows,
        )

    def test_legacy_text_plan_is_upgraded_to_stable_items(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE runs(id TEXT PRIMARY KEY, plan TEXT NOT NULL DEFAULT '[]')")
        conn.execute(
            "INSERT INTO runs(id,plan) VALUES (?,?)",
            ("run-1", '[{"text":"分析"},{"text":"实现"}]'),
        )
        migrate_run_plan_version(conn)
        row = conn.execute("SELECT plan,plan_version FROM runs WHERE id='run-1'").fetchone()
        import json
        plan = json.loads(row[0])
        self.assertEqual(1, row[1])
        self.assertEqual(["分析", "实现"], [item["title"] for item in plan])
        self.assertTrue(all(item["id"].startswith("plan_") for item in plan))


if __name__ == "__main__":
    unittest.main()
