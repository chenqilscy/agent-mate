"""Ordered SQLite migrations for the Server control-plane database."""
from __future__ import annotations

import hashlib
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
    conn: sqlite3.Connection, migrations: Iterable[Migration], *, scope: str = "server",
) -> None:
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


def migrate_federated_identity_security(conn: sqlite3.Connection) -> None:
    account_columns = {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}
    if "password_login_enabled" not in account_columns:
        conn.execute(
            "ALTER TABLE accounts ADD COLUMN password_login_enabled INTEGER NOT NULL DEFAULT 1"
        )
    for row in conn.execute(
        "SELECT token FROM server_tokens WHERE token NOT LIKE 'sha256:%'"
    ).fetchall():
        raw = str(row[0])
        conn.execute(
            "UPDATE server_tokens SET token=? WHERE token=?",
            ("sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest(), raw),
        )


def migrate_governance_activity_sequence(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(project_governance_activity)")}
    if "sequence" not in columns:
        conn.execute(
            "ALTER TABLE project_governance_activity ADD COLUMN sequence INTEGER NOT NULL DEFAULT 0"
        )
    # This is an ordinary SQLite table, so rowid preserves historical insertion order.
    conn.execute("UPDATE project_governance_activity SET sequence=rowid WHERE sequence=0")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_governance_activity_sequence "
        "ON project_governance_activity(project_id, record_id, sequence DESC)"
    )
