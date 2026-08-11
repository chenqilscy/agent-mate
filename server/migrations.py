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


def migrate_work_item_acceptance_idempotency(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS work_item_acceptances (
            work_item_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            artifact_count INTEGER NOT NULL,
            accepted_by TEXT NOT NULL,
            accepted_at REAL NOT NULL,
            UNIQUE(project_id, run_id)
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_work_item_acceptances_project "
        "ON work_item_acceptances(project_id, accepted_at DESC)"
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
        "work_item_acceptances": {
            "work_item_id", "project_id", "run_id", "artifact_count", "accepted_by", "accepted_at",
        },
        "org_model_policies": {"policy", "revision", "updated_by", "updated_at"},
        "tool_catalog": {
            "implementation_type", "parameters", "scripts", "timeout_seconds", "output_limit",
        },
        "business_sessions": {"owner_id", "project_id", "version", "client_request_id"},
        "business_messages": {"session_id", "run_id", "sequence", "client_request_id"},
        "business_runs": {
            "session_id", "project_id", "status", "version", "client_request_id",
            "target_device_id", "required_capabilities", "request_snapshot", "lease_epoch",
            "recovery_count", "max_recoveries", "cancel_version",
        },
        "business_run_steps": {"run_id", "sequence", "client_request_id"},
        "business_assistants": {"owner_id", "project_id", "version", "client_request_id"},
        "business_channels": {"assistant_id", "public_config", "credential_ref", "version"},
        "business_automations": {
            "owner_id", "project_id", "version", "client_request_id", "timezone",
            "routing_mode", "target_device_id",
        },
        "business_assets": {"owner_id", "project_id", "object_ref", "storage_state", "version"},
        "asset_object_versions": {"asset_id", "version_number", "storage_key", "sha256", "size"},
        "asset_uploads": {"asset_id", "expected_sha256", "expected_size", "state", "expires_at"},
        "asset_upload_parts": {"upload_id", "part_number", "sha256", "size"},
        "asset_download_grants": {
            "token_hash", "asset_id", "object_version_id", "expires_at", "used_at",
        },
        "business_audit": {"actor_id", "entity_type", "entity_id", "created_at"},
        "agent_devices": {"owner_id", "public_key", "capabilities", "status", "revoked_at"},
        "device_challenges": {"device_id", "nonce", "expires_at", "used_at"},
        "device_tokens": {"token_hash", "device_id", "expires_at", "revoked_at"},
        "run_leases": {"run_id", "device_id", "lease_epoch", "expires_at", "ack_high_water"},
        "run_events": {"event_id", "run_id", "lease_epoch", "sequence", "payload_hash"},
        "run_commands": {"run_id", "command_type", "version", "status"},
        "business_automation_fires": {"automation_id", "run_id", "status", "trigger_payload"},
        "business_automation_webhooks": {"automation_id", "owner_id", "secret_ciphertext"},
        "business_automation_webhook_deliveries": {
            "webhook_id", "idempotency_key", "payload_sha256", "status", "fire_id",
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


def migrate_single_active_sprint(conn: sqlite3.Connection) -> None:
    """Keep the newest current Sprint and enforce one active row per project."""
    active_rows = conn.execute(
        "SELECT id,project_id FROM sprints WHERE status='active' "
        "ORDER BY project_id,updated_at DESC,created_at DESC,id DESC"
    ).fetchall()
    seen_projects: set[str] = set()
    stale_ids: list[str] = []
    for row in active_rows:
        project_id = str(row["project_id"])
        if project_id in seen_projects:
            stale_ids.append(str(row["id"]))
        else:
            seen_projects.add(project_id)
    if stale_ids:
        placeholders = ",".join("?" for _item in stale_ids)
        conn.execute(
            f"UPDATE sprints SET status='closed',updated_at=? WHERE id IN ({placeholders})",
            (time.time(), *stale_ids),
        )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_sprints_one_active_per_project "
        "ON sprints(project_id) WHERE status='active'"
    )


def migrate_durable_business_plane(conn: sqlite3.Connection) -> None:
    """Create the Server-owned durable business graph (WB-432).

    File bytes, device leases and event ACK state deliberately stay out of this
    migration: WB-433 and WB-436 own those protocols. ``assets`` is the stable
    metadata/object-reference authority consumed by both later slices.
    """
    schema = """
        CREATE TABLE IF NOT EXISTS business_sessions (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            project_id TEXT,
            title TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'chat',
            status TEXT NOT NULL DEFAULT 'idle',
            space TEXT,
            version INTEGER NOT NULL DEFAULT 1,
            client_request_id TEXT NOT NULL DEFAULT '',
            request_hash TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            deleted_at REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_business_sessions_owner_page
            ON business_sessions(owner_id,updated_at DESC,id DESC);
        CREATE INDEX IF NOT EXISTS idx_business_sessions_project_page
            ON business_sessions(project_id,updated_at DESC,id DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_business_sessions_request
            ON business_sessions(owner_id,client_request_id) WHERE client_request_id!='';

        CREATE TABLE IF NOT EXISTS business_runs (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            project_id TEXT,
            work_item_id TEXT,
            mode TEXT NOT NULL DEFAULT 'exec',
            status TEXT NOT NULL DEFAULT 'queued',
            workspace TEXT NOT NULL DEFAULT 'default',
            retry_of TEXT,
            model_ref TEXT,
            model_id TEXT,
            model_snapshot TEXT NOT NULL DEFAULT '{}',
            estimated_cost REAL,
            cost_currency TEXT,
            plan TEXT NOT NULL DEFAULT '[]',
            plan_version INTEGER NOT NULL DEFAULT 0,
            permission_snapshot TEXT NOT NULL DEFAULT '{}',
            checkpoint TEXT NOT NULL DEFAULT '{}',
            error_code TEXT,
            error_message TEXT,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            cached_prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            tool_calls INTEGER NOT NULL DEFAULT 0,
            started_at REAL,
            ended_at REAL,
            version INTEGER NOT NULL DEFAULT 1,
            client_request_id TEXT NOT NULL DEFAULT '',
            request_hash TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            deleted_at REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(session_id) REFERENCES business_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_business_runs_session_page
            ON business_runs(session_id,updated_at DESC,id DESC);
        CREATE INDEX IF NOT EXISTS idx_business_runs_project_page
            ON business_runs(project_id,updated_at DESC,id DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_business_runs_request
            ON business_runs(owner_id,client_request_id) WHERE client_request_id!='';

        CREATE TABLE IF NOT EXISTS business_messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            run_id TEXT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            trace TEXT NOT NULL DEFAULT '[]',
            usage TEXT,
            error TEXT,
            sequence INTEGER NOT NULL,
            client_request_id TEXT NOT NULL DEFAULT '',
            request_hash TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            FOREIGN KEY(session_id) REFERENCES business_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY(run_id) REFERENCES business_runs(id) ON DELETE SET NULL,
            UNIQUE(session_id,sequence)
        );
        CREATE INDEX IF NOT EXISTS idx_business_messages_session_page
            ON business_messages(session_id,sequence,id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_business_messages_request
            ON business_messages(owner_id,client_request_id) WHERE client_request_id!='';

        CREATE TABLE IF NOT EXISTS business_run_steps (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            sequence INTEGER NOT NULL,
            started_at REAL,
            ended_at REAL,
            client_request_id TEXT NOT NULL DEFAULT '',
            request_hash TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            FOREIGN KEY(run_id) REFERENCES business_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE,
            UNIQUE(run_id,sequence)
        );
        CREATE INDEX IF NOT EXISTS idx_business_run_steps_page
            ON business_run_steps(run_id,sequence,id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_business_run_steps_request
            ON business_run_steps(owner_id,client_request_id) WHERE client_request_id!='';

        CREATE TABLE IF NOT EXISTS business_assistants (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            project_id TEXT,
            name TEXT NOT NULL,
            avatar TEXT NOT NULL DEFAULT '',
            instruction TEXT NOT NULL DEFAULT '',
            model_ref TEXT,
            mode TEXT NOT NULL DEFAULT 'exec',
            workspace TEXT NOT NULL DEFAULT 'default',
            experts TEXT NOT NULL DEFAULT '[]',
            skills TEXT NOT NULL DEFAULT '[]',
            connectors TEXT NOT NULL DEFAULT '[]',
            enabled INTEGER NOT NULL DEFAULT 1,
            version INTEGER NOT NULL DEFAULT 1,
            client_request_id TEXT NOT NULL DEFAULT '',
            request_hash TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            deleted_at REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_business_assistants_owner_page
            ON business_assistants(owner_id,updated_at DESC,id DESC);
        CREATE INDEX IF NOT EXISTS idx_business_assistants_project_page
            ON business_assistants(project_id,updated_at DESC,id DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_business_assistants_request
            ON business_assistants(owner_id,client_request_id) WHERE client_request_id!='';

        CREATE TABLE IF NOT EXISTS business_channels (
            id TEXT PRIMARY KEY,
            assistant_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            type TEXT NOT NULL,
            public_config TEXT NOT NULL DEFAULT '{}',
            credential_ref TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 0,
            version INTEGER NOT NULL DEFAULT 1,
            client_request_id TEXT NOT NULL DEFAULT '',
            request_hash TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            deleted_at REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(assistant_id) REFERENCES business_assistants(id) ON DELETE CASCADE,
            FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_business_channels_assistant_page
            ON business_channels(assistant_id,updated_at DESC,id DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_business_channels_request
            ON business_channels(owner_id,client_request_id) WHERE client_request_id!='';

        CREATE TABLE IF NOT EXISTS business_automations (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            project_id TEXT,
            name TEXT NOT NULL,
            prompt TEXT NOT NULL,
            trigger_kind TEXT NOT NULL DEFAULT 'interval',
            interval_min INTEGER NOT NULL DEFAULT 60,
            at_time TEXT NOT NULL DEFAULT '09:00',
            model_ref TEXT,
            routing_mode TEXT NOT NULL DEFAULT 'any_compatible',
            target_device_id TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            next_run_at REAL,
            last_run_at REAL,
            last_session_id TEXT,
            last_status TEXT,
            timeout_sec INTEGER NOT NULL DEFAULT 300,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            retry_backoff_sec INTEGER NOT NULL DEFAULT 30,
            max_total_tokens INTEGER NOT NULL DEFAULT 0,
            notify_policy TEXT NOT NULL DEFAULT 'failure,recovery',
            concurrency_policy TEXT NOT NULL DEFAULT 'skip',
            preauthorized_permissions TEXT NOT NULL DEFAULT '[]',
            version INTEGER NOT NULL DEFAULT 1,
            client_request_id TEXT NOT NULL DEFAULT '',
            request_hash TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            deleted_at REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY(last_session_id) REFERENCES business_sessions(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_business_automations_owner_page
            ON business_automations(owner_id,updated_at DESC,id DESC);
        CREATE INDEX IF NOT EXISTS idx_business_automations_project_page
            ON business_automations(project_id,updated_at DESC,id DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_business_automations_request
            ON business_automations(owner_id,client_request_id) WHERE client_request_id!='';

        CREATE TABLE IF NOT EXISTS business_assets (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            project_id TEXT,
            session_id TEXT,
            run_id TEXT,
            kind TEXT NOT NULL DEFAULT 'asset',
            name TEXT NOT NULL,
            mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
            size INTEGER NOT NULL DEFAULT 0,
            sha256 TEXT NOT NULL DEFAULT '',
            storage_state TEXT NOT NULL DEFAULT 'pending',
            object_ref TEXT NOT NULL DEFAULT '',
            source_tool TEXT NOT NULL DEFAULT '',
            validation_status TEXT NOT NULL DEFAULT 'pending',
            validation TEXT NOT NULL DEFAULT '{}',
            acceptance_status TEXT NOT NULL DEFAULT 'pending',
            accepted_by TEXT,
            accepted_at REAL,
            version INTEGER NOT NULL DEFAULT 1,
            client_request_id TEXT NOT NULL DEFAULT '',
            request_hash TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            deleted_at REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY(session_id) REFERENCES business_sessions(id) ON DELETE SET NULL,
            FOREIGN KEY(run_id) REFERENCES business_runs(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_business_assets_project_page
            ON business_assets(project_id,updated_at DESC,id DESC);
        CREATE INDEX IF NOT EXISTS idx_business_assets_run_page
            ON business_assets(run_id,updated_at DESC,id DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_business_assets_request
            ON business_assets(owner_id,client_request_id) WHERE client_request_id!='';

        CREATE TABLE IF NOT EXISTS business_audit (
            id TEXT PRIMARY KEY,
            actor_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            project_id TEXT,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_business_audit_owner_page
            ON business_audit(owner_id,created_at DESC,id DESC);
        CREATE INDEX IF NOT EXISTS idx_business_audit_project_page
            ON business_audit(project_id,created_at DESC,id DESC);
        """
    # ``executescript`` commits implicitly and would escape run_migrations'
    # BEGIN IMMEDIATE transaction. These statements contain no trigger bodies,
    # so executing them individually preserves an atomic schema migration.
    for statement in schema.split(";"):
        if statement.strip():
            conn.execute(statement)


def migrate_asset_object_storage(conn: sqlite3.Connection) -> None:
    """Add resumable immutable Asset objects without turning Server into a workspace mirror."""
    schema = """
        CREATE TABLE IF NOT EXISTS asset_object_versions (
            id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            version_number INTEGER NOT NULL,
            storage_key TEXT NOT NULL,
            size INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            retained_until REAL NOT NULL,
            created_at REAL NOT NULL,
            deleted_at REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(asset_id) REFERENCES business_assets(id) ON DELETE CASCADE,
            FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE,
            UNIQUE(asset_id,version_number)
        );
        CREATE INDEX IF NOT EXISTS idx_asset_versions_asset
            ON asset_object_versions(asset_id,version_number DESC);
        CREATE INDEX IF NOT EXISTS idx_asset_versions_dedupe
            ON asset_object_versions(owner_id,sha256,size,deleted_at);

        CREATE TABLE IF NOT EXISTS asset_uploads (
            id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            project_id TEXT,
            expected_size INTEGER NOT NULL,
            expected_sha256 TEXT NOT NULL,
            part_size INTEGER NOT NULL,
            state TEXT NOT NULL DEFAULT 'uploading',
            object_version_id TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            completed_at REAL,
            FOREIGN KEY(asset_id) REFERENCES business_assets(id) ON DELETE CASCADE,
            FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY(object_version_id) REFERENCES asset_object_versions(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_asset_uploads_resume
            ON asset_uploads(owner_id,asset_id,state,updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_asset_uploads_expiry
            ON asset_uploads(state,expires_at);

        CREATE TABLE IF NOT EXISTS asset_upload_parts (
            upload_id TEXT NOT NULL,
            part_number INTEGER NOT NULL,
            size INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            created_at REAL NOT NULL,
            PRIMARY KEY(upload_id,part_number),
            FOREIGN KEY(upload_id) REFERENCES asset_uploads(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS asset_download_grants (
            token_hash TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            object_version_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            expires_at REAL NOT NULL,
            used_at REAL NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            FOREIGN KEY(asset_id) REFERENCES business_assets(id) ON DELETE CASCADE,
            FOREIGN KEY(object_version_id) REFERENCES asset_object_versions(id) ON DELETE CASCADE,
            FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_asset_download_grants_expiry
            ON asset_download_grants(expires_at,used_at);
    """
    for statement in schema.split(";"):
        if statement.strip():
            conn.execute(statement)


def migrate_device_run_protocol(conn: sqlite3.Connection) -> None:
    """Create device identity, fenced Run leases and ordered event storage (WB-433)."""
    run_columns = {row[1] for row in conn.execute("PRAGMA table_info(business_runs)")}
    for column, ddl in (
        ("target_device_id", "target_device_id TEXT NOT NULL DEFAULT ''"),
        ("required_capabilities", "required_capabilities TEXT NOT NULL DEFAULT '[]'"),
        ("request_snapshot", "request_snapshot TEXT NOT NULL DEFAULT '{}'") ,
        ("lease_epoch", "lease_epoch INTEGER NOT NULL DEFAULT 0"),
        ("recovery_count", "recovery_count INTEGER NOT NULL DEFAULT 0"),
        ("max_recoveries", "max_recoveries INTEGER NOT NULL DEFAULT 3"),
        ("cancel_version", "cancel_version INTEGER NOT NULL DEFAULT 0"),
        ("cancel_requested_at", "cancel_requested_at REAL NOT NULL DEFAULT 0"),
    ):
        if column not in run_columns:
            conn.execute(f"ALTER TABLE business_runs ADD COLUMN {ddl}")

    schema = """
        CREATE TABLE IF NOT EXISTS agent_devices (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            name TEXT NOT NULL,
            public_key TEXT NOT NULL,
            protocol_version INTEGER NOT NULL DEFAULT 1,
            app_version TEXT NOT NULL DEFAULT '',
            platform TEXT NOT NULL DEFAULT '',
            arch TEXT NOT NULL DEFAULT '',
            capabilities TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            authenticated_at REAL NOT NULL DEFAULT 0,
            last_seen_at REAL NOT NULL DEFAULT 0,
            revoked_at REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_agent_devices_owner
            ON agent_devices(owner_id,status,last_seen_at DESC);

        CREATE TABLE IF NOT EXISTS device_challenges (
            id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            nonce TEXT NOT NULL,
            expires_at REAL NOT NULL,
            used_at REAL NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            FOREIGN KEY(device_id) REFERENCES agent_devices(id) ON DELETE CASCADE,
            FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_device_challenges_device
            ON device_challenges(device_id,expires_at DESC);

        CREATE TABLE IF NOT EXISTS device_tokens (
            token_hash TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            expires_at REAL NOT NULL,
            created_at REAL NOT NULL,
            last_used_at REAL NOT NULL DEFAULT 0,
            revoked_at REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(device_id) REFERENCES agent_devices(id) ON DELETE CASCADE,
            FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_device_tokens_device
            ON device_tokens(device_id,expires_at DESC);

        CREATE TABLE IF NOT EXISTS run_leases (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            lease_epoch INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            issued_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            renewed_at REAL NOT NULL,
            ack_high_water INTEGER NOT NULL DEFAULT 0,
            terminal_event_id TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(run_id) REFERENCES business_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY(device_id) REFERENCES agent_devices(id) ON DELETE CASCADE,
            UNIQUE(run_id,lease_epoch)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_run_leases_one_active
            ON run_leases(run_id) WHERE status='active';
        CREATE INDEX IF NOT EXISTS idx_run_leases_device
            ON run_leases(device_id,status,expires_at);

        CREATE TABLE IF NOT EXISTS run_events (
            event_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            lease_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            lease_epoch INTEGER NOT NULL,
            sequence INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            occurred_at REAL NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            payload_hash TEXT NOT NULL,
            created_at REAL NOT NULL,
            FOREIGN KEY(run_id) REFERENCES business_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(lease_id) REFERENCES run_leases(id) ON DELETE CASCADE,
            FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY(device_id) REFERENCES agent_devices(id) ON DELETE CASCADE,
            UNIQUE(run_id,lease_epoch,sequence)
        );
        CREATE INDEX IF NOT EXISTS idx_run_events_order
            ON run_events(run_id,lease_epoch,sequence);

        CREATE TABLE IF NOT EXISTS run_commands (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            command_type TEXT NOT NULL,
            version INTEGER NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at REAL NOT NULL,
            acknowledged_at REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(run_id) REFERENCES business_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE,
            UNIQUE(run_id,command_type,version)
        );
        CREATE INDEX IF NOT EXISTS idx_run_commands_pending
            ON run_commands(run_id,status,version);
    """
    for statement in schema.split(";"):
        if statement.strip():
            conn.execute(statement)


def migrate_server_automation_fires(conn: sqlite3.Connection) -> None:
    """Move automation attempt, retry, and dead-letter authority to Server."""
    schema = """
        CREATE TABLE IF NOT EXISTS business_automation_fires (
            id TEXT PRIMARY KEY,
            automation_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            fire_key TEXT NOT NULL,
            trigger_kind TEXT NOT NULL,
            planned_at REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            attempt INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            session_id TEXT,
            run_id TEXT,
            retry_of_run_id TEXT,
            error_code TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            next_attempt_at REAL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            finished_at REAL NOT NULL DEFAULT 0,
            UNIQUE(automation_id,fire_key),
            FOREIGN KEY(automation_id) REFERENCES business_automations(id) ON DELETE CASCADE,
            FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY(session_id) REFERENCES business_sessions(id) ON DELETE SET NULL,
            FOREIGN KEY(run_id) REFERENCES business_runs(id) ON DELETE SET NULL,
            FOREIGN KEY(retry_of_run_id) REFERENCES business_runs(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_business_automation_fires_due
            ON business_automation_fires(status,next_attempt_at);
        CREATE INDEX IF NOT EXISTS idx_business_automation_fires_owner
            ON business_automation_fires(owner_id,created_at DESC);
    """
    for statement in schema.split(";"):
        if statement.strip():
            conn.execute(statement)


def migrate_server_automation_webhooks(conn: sqlite3.Connection) -> None:
    """Move signed webhook ingress and delivery idempotency to Server."""
    fire_columns = {row[1] for row in conn.execute("PRAGMA table_info(business_automation_fires)")}
    if "trigger_payload" not in fire_columns:
        conn.execute(
            "ALTER TABLE business_automation_fires ADD COLUMN trigger_payload TEXT NOT NULL DEFAULT '{}'"
        )
    schema = """
        CREATE TABLE IF NOT EXISTS business_automation_webhooks (
            id TEXT PRIMARY KEY,
            automation_id TEXT NOT NULL UNIQUE,
            owner_id TEXT NOT NULL,
            secret_ciphertext TEXT NOT NULL,
            created_at REAL NOT NULL,
            rotated_at REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(automation_id) REFERENCES business_automations(id) ON DELETE CASCADE,
            FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_business_automation_webhooks_owner
            ON business_automation_webhooks(owner_id,created_at DESC);

        CREATE TABLE IF NOT EXISTS business_automation_webhook_deliveries (
            id TEXT PRIMARY KEY,
            webhook_id TEXT NOT NULL,
            automation_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'received',
            fire_id TEXT,
            error_code TEXT NOT NULL DEFAULT '',
            received_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            UNIQUE(webhook_id,idempotency_key),
            FOREIGN KEY(webhook_id) REFERENCES business_automation_webhooks(id) ON DELETE CASCADE,
            FOREIGN KEY(automation_id) REFERENCES business_automations(id) ON DELETE CASCADE,
            FOREIGN KEY(owner_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY(fire_id) REFERENCES business_automation_fires(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_business_automation_webhook_deliveries_owner
            ON business_automation_webhook_deliveries(owner_id,received_at DESC);
    """
    for statement in schema.split(";"):
        if statement.strip():
            conn.execute(statement)


def migrate_server_automation_timezone(conn: sqlite3.Connection) -> None:
    """Pin daily schedules to an explicit timezone while preserving legacy semantics."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(business_automations)")}
    if "timezone" not in columns:
        conn.execute(
            "ALTER TABLE business_automations ADD COLUMN timezone TEXT NOT NULL DEFAULT 'server_local'"
        )


def migrate_automation_device_routing(conn: sqlite3.Connection) -> None:
    """Persist Console-selected Local Agent routing without changing execution ownership."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(business_automations)")}
    if "routing_mode" not in columns:
        conn.execute(
            "ALTER TABLE business_automations ADD COLUMN routing_mode TEXT NOT NULL DEFAULT 'any_compatible'"
        )
    if "target_device_id" not in columns:
        conn.execute(
            "ALTER TABLE business_automations ADD COLUMN target_device_id TEXT NOT NULL DEFAULT ''"
        )
