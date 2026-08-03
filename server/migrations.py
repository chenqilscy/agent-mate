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


def migrate_account_login_lifecycle(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}
    if "suspended_at" not in columns:
        conn.execute("ALTER TABLE accounts ADD COLUMN suspended_at REAL NOT NULL DEFAULT 0")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS auth_audit (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL DEFAULT '',
            actor_id TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL,
            provider TEXT NOT NULL DEFAULT '',
            details TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_audit_created "
        "ON auth_audit(created_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_auth_audit_account "
        "ON auth_audit(account_id, created_at DESC)"
    )


def migrate_relay_retention(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(relay_events)")}
    if "payload_tombstoned_at" not in columns:
        conn.execute(
            "ALTER TABLE relay_events ADD COLUMN payload_tombstoned_at REAL"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_relay_events_terminal_retention "
        "ON relay_events(owner_id,status,acknowledged_at,created_at)"
    )


def migrate_server_legacy_schema(
    conn: sqlite3.Connection, token_legacy_expires_at: float,
) -> None:
    """Complete every schema column that existed before the ordered ledger."""
    account_columns = {row[1] for row in conn.execute("PRAGMA table_info(accounts)")}
    for column, ddl in (
        ("is_platform_admin", "is_platform_admin INTEGER NOT NULL DEFAULT 0"),
        ("last_seen", "last_seen REAL NOT NULL DEFAULT 0"),
    ):
        if column not in account_columns:
            conn.execute(f"ALTER TABLE accounts ADD COLUMN {ddl}")

    token_columns = {row[1] for row in conn.execute("PRAGMA table_info(server_tokens)")}
    if "expires_at" not in token_columns:
        conn.execute("ALTER TABLE server_tokens ADD COLUMN expires_at REAL")
    conn.execute(
        "UPDATE server_tokens SET expires_at=? WHERE expires_at IS NULL OR expires_at<=0",
        (token_legacy_expires_at,),
    )

    project_columns = {row[1] for row in conn.execute("PRAGMA table_info(projects)")}
    if "archived_at" not in project_columns:
        conn.execute("ALTER TABLE projects ADD COLUMN archived_at REAL NOT NULL DEFAULT 0")

    work_columns = {row[1] for row in conn.execute("PRAGMA table_info(work_items)")}
    for column, ddl in (
        ("priority", "priority TEXT NOT NULL DEFAULT ''"),
        ("due_date", "due_date TEXT NOT NULL DEFAULT ''"),
        ("start_date", "start_date TEXT NOT NULL DEFAULT ''"),
        ("labels", "labels TEXT NOT NULL DEFAULT '[]'"),
        ("parent_id", "parent_id TEXT NOT NULL DEFAULT ''"),
        ("milestone_id", "milestone_id TEXT NOT NULL DEFAULT ''"),
        ("estimate_h", "estimate_h REAL NOT NULL DEFAULT 0"),
        ("spent_h", "spent_h REAL NOT NULL DEFAULT 0"),
        ("custom_fields", "custom_fields TEXT NOT NULL DEFAULT '{}'"),
        ("dependency_ids", "dependency_ids TEXT NOT NULL DEFAULT '[]'"),
        ("sprint_id", "sprint_id TEXT NOT NULL DEFAULT ''"),
    ):
        if column not in work_columns:
            conn.execute(f"ALTER TABLE work_items ADD COLUMN {ddl}")

    sprint_columns = {row[1] for row in conn.execute("PRAGMA table_info(sprints)")}
    if "milestone_id" not in sprint_columns:
        conn.execute("ALTER TABLE sprints ADD COLUMN milestone_id TEXT NOT NULL DEFAULT ''")
    comment_columns = {row[1] for row in conn.execute("PRAGMA table_info(comments)")}
    if "work_item_id" not in comment_columns:
        conn.execute("ALTER TABLE comments ADD COLUMN work_item_id TEXT NOT NULL DEFAULT ''")
    notification_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(server_notifications)")
    }
    if "dedupe_key" not in notification_columns:
        conn.execute(
            "ALTER TABLE server_notifications ADD COLUMN dedupe_key TEXT NOT NULL DEFAULT ''"
        )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_server_notifs_dedupe "
        "ON server_notifications(account_id,dedupe_key) WHERE dedupe_key!=''"
    )

    kb_columns = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_bases)")}
    for column, ddl in (
        ("provider", "provider TEXT NOT NULL DEFAULT 'legacy'"),
        ("provider_id", "provider_id TEXT NOT NULL DEFAULT ''"),
        ("provider_status", "provider_status TEXT NOT NULL DEFAULT 'legacy_pending'"),
        ("provider_error", "provider_error TEXT NOT NULL DEFAULT ''"),
    ):
        if column not in kb_columns:
            conn.execute(f"ALTER TABLE knowledge_bases ADD COLUMN {ddl}")
    document_columns = {row[1] for row in conn.execute("PRAGMA table_info(kb_documents)")}
    if "provider_id" not in document_columns:
        conn.execute("ALTER TABLE kb_documents ADD COLUMN provider_id TEXT NOT NULL DEFAULT ''")

    tool_columns = {row[1] for row in conn.execute("PRAGMA table_info(tool_catalog)")}
    for column, ddl in (
        ("implementation_type", "implementation_type TEXT NOT NULL DEFAULT 'native'"),
        ("parameters", "parameters TEXT NOT NULL DEFAULT '{}'"),
        ("scripts", "scripts TEXT NOT NULL DEFAULT '{}'"),
        ("timeout_seconds", "timeout_seconds INTEGER NOT NULL DEFAULT 30"),
        ("output_limit", "output_limit INTEGER NOT NULL DEFAULT 65536"),
    ):
        if column not in tool_columns:
            conn.execute(f"ALTER TABLE tool_catalog ADD COLUMN {ddl}")

    member_columns = {row[1] for row in conn.execute("PRAGMA table_info(project_members)")}
    if "updated_at" not in member_columns:
        conn.execute("ALTER TABLE project_members ADD COLUMN updated_at REAL NOT NULL DEFAULT 0")
    conn.execute("UPDATE project_members SET updated_at=created_at WHERE updated_at=0")
    if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='catalog_skills'"
    ).fetchone():
        conn.execute("UPDATE catalog_skills SET source='Server' WHERE source='Hub'")


def assert_server_schema(conn: sqlite3.Connection) -> None:
    required = {
        "accounts": {
            "is_platform_admin", "last_seen", "password_login_enabled", "suspended_at",
        },
        "server_tokens": {"expires_at"},
        "projects": {"archived_at"},
        "project_members": {"updated_at"},
        "relay_events": {"payload_tombstoned_at"},
        "org_model_policies": {"policy", "revision", "updated_by", "updated_at"},
        "tool_catalog": {
            "implementation_type", "parameters", "scripts", "timeout_seconds", "output_limit",
        },
    }
    missing: list[str] = []
    for table, columns in required.items():
        have = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        missing.extend(f"{table}.{column}" for column in sorted(columns - have))
    if missing:
        raise RuntimeError("server schema invariant failed: " + ", ".join(missing))


def migrate_sso_provider_audit(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS sso_provider_audit (
            id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sso_provider_audit_created "
        "ON sso_provider_audit(created_at DESC)"
    )
