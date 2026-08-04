"""Small, ordered SQLite migration runner for the local App database."""
from __future__ import annotations

import hashlib
import json
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


def migrate_run_plan_version(conn: sqlite3.Connection) -> None:
    """Add the monotonic revision used by durable RunPlan snapshots (WB-385)."""
    have_runs = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    if "plan" not in have_runs:
        conn.execute("ALTER TABLE runs ADD COLUMN plan TEXT NOT NULL DEFAULT '[]'")
    if "plan_version" not in have_runs:
        conn.execute("ALTER TABLE runs ADD COLUMN plan_version INTEGER NOT NULL DEFAULT 0")
    rows = conn.execute("SELECT id,plan,plan_version FROM runs").fetchall()
    for run_id, raw_plan, version in rows:
        try:
            plan = json.loads(raw_plan) if raw_plan else []
        except (json.JSONDecodeError, TypeError):
            plan = []
        if not isinstance(plan, list) or not any(
            isinstance(item, dict) and "text" in item and "id" not in item for item in plan
        ):
            continue
        occurrences: dict[str, int] = {}
        upgraded = []
        for order, item in enumerate(plan[:50]):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("text") or "").strip()[:300]
            if not title:
                continue
            key = title.casefold()
            occurrence = occurrences.get(key, 0)
            occurrences[key] = occurrence + 1
            digest = hashlib.sha256(
                f"{run_id}\0{key}\0{occurrence}".encode("utf-8")
            ).hexdigest()[:20]
            upgraded.append({
                "id": f"plan_{digest}", "title": title, "status": "pending",
                "order": order, "depends_on": [],
            })
        conn.execute(
            "UPDATE runs SET plan=?,plan_version=? WHERE id=?",
            (json.dumps(upgraded, ensure_ascii=False), max(1, int(version or 0)), run_id),
        )


def migrate_project_org_scope(conn: sqlite3.Connection) -> None:
    """Mirror Server organization scope for inherited model policy (WB-386)."""
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='projects'"
    ).fetchone():
        return
    columns = {row[1] for row in conn.execute("PRAGMA table_info(projects)")}
    if "org_id" not in columns:
        conn.execute("ALTER TABLE projects ADD COLUMN org_id TEXT")


def migrate_artifact_presentation(conn: sqlite3.Connection) -> None:
    """Backfill one authoritative primary artifact and stable order per Run (WB-407)."""
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='artifacts'"
    ).fetchone():
        return
    columns = {row[1] for row in conn.execute("PRAGMA table_info(artifacts)")}
    if "is_primary" not in columns:
        conn.execute("ALTER TABLE artifacts ADD COLUMN is_primary INTEGER NOT NULL DEFAULT 0")
    if "display_order" not in columns:
        conn.execute("ALTER TABLE artifacts ADD COLUMN display_order INTEGER NOT NULL DEFAULT 0")

    current_run = ""
    order = 0
    rows = conn.execute(
        "SELECT id,run_id FROM artifacts ORDER BY run_id,created_at,id"
    ).fetchall()
    for artifact_id, run_id in rows:
        if run_id != current_run:
            current_run = run_id
            order = 0
        conn.execute(
            "UPDATE artifacts SET is_primary=?,display_order=? WHERE id=?",
            (1 if order == 0 else 0, order, artifact_id),
        )
        order += 1
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_artifacts_one_primary "
        "ON artifacts(run_id) WHERE is_primary=1"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_artifacts_presentation "
        "ON artifacts(run_id,is_primary DESC,display_order,created_at,id)"
    )


def migrate_connector_companion_skill(conn: sqlite3.Connection) -> None:
    """Bind trusted connector definitions to an optional companion Skill (WB-409)."""
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='catalog_connectors'"
    ).fetchone():
        return
    columns = {row[1] for row in conn.execute("PRAGMA table_info(catalog_connectors)")}
    if "companion_skill_slug" not in columns:
        conn.execute(
            "ALTER TABLE catalog_connectors "
            "ADD COLUMN companion_skill_slug TEXT NOT NULL DEFAULT ''"
        )
    # This is shipped execution policy, not Server display metadata. Keep existing
    # databases aligned with the bundled connector definition.
    conn.execute(
        "UPDATE catalog_connectors SET companion_skill_slug='github-connector-guide' "
        "WHERE scope='builtin' AND slug='github'"
    )
