"""Small, ordered SQLite migration runner for the local App database."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


def run_migrations(
    conn: sqlite3.Connection, migrations: Iterable[Migration], *, scope: str = "app",
) -> None:
    """Apply each migration once and record success only after its transaction commits."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
               scope TEXT NOT NULL,
               version INTEGER NOT NULL,
               name TEXT NOT NULL,
               applied_at REAL NOT NULL,
               PRIMARY KEY (scope, version)
           )"""
    )
    conn.commit()
    ordered = sorted(migrations, key=lambda item: item.version)
    if len({item.version for item in ordered}) != len(ordered):
        raise ValueError(f"duplicate migration version for {scope}")
    applied = {
        int(row[0]): str(row[1])
        for row in conn.execute(
            "SELECT version,name FROM schema_migrations WHERE scope=?", (scope,)
        ).fetchall()
    }
    for migration in ordered:
        recorded_name = applied.get(migration.version)
        if recorded_name is not None:
            if recorded_name != migration.name:
                raise RuntimeError(
                    f"migration {scope}:{migration.version} was {recorded_name!r}, "
                    f"not {migration.name!r}"
                )
            continue
        try:
            conn.execute("BEGIN IMMEDIATE")
            migration.apply(conn)
            conn.execute(
                "INSERT INTO schema_migrations(scope,version,name,applied_at) VALUES (?,?,?,?)",
                (scope, migration.version, migration.name, time.time()),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def migrate_model_and_run_audit(conn: sqlite3.Connection) -> None:
    have_meta = {row[1] for row in conn.execute("PRAGMA table_info(model_meta)")}
    for column, ddl in (
        ("input_cost_cached", "input_cost_cached REAL"),
        ("currency", "currency TEXT"),
        ("max_output_tokens", "max_output_tokens INTEGER"),
    ):
        if column not in have_meta:
            conn.execute(f"ALTER TABLE model_meta ADD COLUMN {ddl}")
    have_runs = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    for column, ddl in (
        ("model_ref", "model_ref TEXT"),
        ("model_id", "model_id TEXT"),
        ("model_snapshot", "model_snapshot TEXT NOT NULL DEFAULT '{}'"),
        ("estimated_cost", "estimated_cost REAL"),
        ("cost_currency", "cost_currency TEXT"),
        ("cached_prompt_tokens", "cached_prompt_tokens INTEGER NOT NULL DEFAULT 0"),
    ):
        if column not in have_runs:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {ddl}")


def migrate_message_run_link(conn: sqlite3.Connection) -> None:
    have_messages = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
    if "run_id" not in have_messages:
        conn.execute("ALTER TABLE messages ADD COLUMN run_id TEXT")
    if "error" not in have_messages:
        conn.execute("ALTER TABLE messages ADD COLUMN error TEXT")
