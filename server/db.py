"""Server SQLite 持久化（WB-061）—— 中心权威源的 DAO。

沿用 backend/storage/db.py 的成熟做法：thread-local 连接（WB-009）、WAL + busy_timeout、
无 ORM。承载账号/组织/项目/成员/邀请，以及目录（catalog_*）的 Server 侧同构表（预埋，供 P3 下发）。
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import threading
import time
import uuid
from typing import Any, Optional

from config import settings
from catalog_seed import (
    DEFAULT_APP_SKILLS, DEFAULT_CONNECTORS, DEFAULT_EXPERTS, DEFAULT_EXPERT_TEAMS,
    DEFAULT_SKILL_CATEGORIES, DEFAULT_TOOL_CATALOG,
)
from models import Account, Invite, Org, Project, Role
from migrations import (
    Migration,
    migrate_account_login_lifecycle,
    migrate_federated_identity_security,
    migrate_governance_activity_sequence,
    migrate_durable_business_plane,
    migrate_device_run_protocol,
    migrate_relay_retention,
    migrate_single_active_sprint,
    migrate_work_item_acceptance_idempotency,
    migrate_server_legacy_schema,
    assert_server_schema,
    migrate_sso_provider_audit,
    run_migrations,
)

_local = threading.local()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = _connect()
        _local.conn = conn
    return conn


def new_uuid() -> str:
    return str(uuid.uuid4())


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _migrate_server_naming(conn: sqlite3.Connection) -> None:
    """WB-210：一次性把旧中心服务表改为 server_*；不保留双表兼容。"""
    for old, new in (
        ("hub_tokens", "server_tokens"),
        ("hub_notifications", "server_notifications"),
    ):
        if _table_exists(conn, old) and not _table_exists(conn, new):
            conn.execute(f"ALTER TABLE {old} RENAME TO {new}")
    conn.execute("DROP INDEX IF EXISTS idx_hub_tokens_account")
    conn.execute("DROP INDEX IF EXISTS idx_hub_notifs_account")
    conn.commit()


def init_db() -> None:
    conn = get_conn()
    _migrate_server_naming(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL DEFAULT '',
            plan TEXT NOT NULL DEFAULT '体验版',
            password_hash TEXT NOT NULL,
            created_at REAL NOT NULL,
            is_platform_admin INTEGER NOT NULL DEFAULT 0,
            last_seen REAL NOT NULL DEFAULT 0,
            password_login_enabled INTEGER NOT NULL DEFAULT 1,
            suspended_at REAL NOT NULL DEFAULT 0
        );

        -- Server 签发的 Bearer token（本地 backend 作为客户端持有并回传）。
        CREATE TABLE IF NOT EXISTS server_tokens (
            token TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_server_tokens_account ON server_tokens(account_id);

        -- Federated identity broker (WB-362). Provider secrets and transient PKCE
        -- verifier values stay on Server; public APIs never return them.
        CREATE TABLE IF NOT EXISTS sso_provider_configs (
            provider TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0,
            client_id TEXT NOT NULL DEFAULT '',
            client_secret TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT '',
            updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sso_provider_audit (
            id TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sso_provider_audit_created
            ON sso_provider_audit(created_at DESC);
        CREATE TABLE IF NOT EXISTS external_identities (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            subject TEXT NOT NULL,
            email TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            last_login_at REAL NOT NULL,
            UNIQUE(provider, subject),
            UNIQUE(account_id, provider)
        );
        CREATE INDEX IF NOT EXISTS idx_external_identities_account
            ON external_identities(account_id, created_at);
        CREATE TABLE IF NOT EXISTS sso_attempts (
            id TEXT PRIMARY KEY,
            state_hash TEXT NOT NULL UNIQUE,
            attempt_token_hash TEXT NOT NULL,
            provider TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'login',
            account_id TEXT,
            invite_code_hash TEXT,
            code_verifier TEXT NOT NULL DEFAULT '',
            nonce TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            result_account_id TEXT,
            error_code TEXT,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            completed_at REAL,
            consumed_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_sso_attempt_expiry ON sso_attempts(expires_at);
        CREATE TABLE IF NOT EXISTS sso_signup_invites (
            id TEXT PRIMARY KEY,
            code_hash TEXT NOT NULL UNIQUE,
            created_by TEXT NOT NULL,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            consumed_by TEXT,
            consumed_at REAL
        );
        CREATE TABLE IF NOT EXISTS auth_rate_windows (
            rate_key TEXT NOT NULL,
            window_start INTEGER NOT NULL,
            count INTEGER NOT NULL,
            PRIMARY KEY(rate_key, window_start)
        );

        -- Scoped machine identities and durable external-event relay (WB-361).
        -- Only token hashes and delivery metadata are stored; no App credentials,
        -- conversation text or workspace files enter the control plane.
        CREATE TABLE IF NOT EXISTS service_accounts (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            name TEXT NOT NULL,
            scopes TEXT NOT NULL DEFAULT '[]',
            token_hash TEXT NOT NULL,
            token_hint TEXT NOT NULL,
            created_at REAL NOT NULL,
            rotated_at REAL,
            revoked_at REAL,
            UNIQUE(owner_id, name)
        );
        CREATE INDEX IF NOT EXISTS idx_service_accounts_owner
            ON service_accounts(owner_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS relay_devices (
            owner_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            last_seen REAL NOT NULL,
            PRIMARY KEY(owner_id, device_id)
        );

        CREATE TABLE IF NOT EXISTS relay_events (
            id TEXT PRIMARY KEY,
            service_account_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            automation_id TEXT NOT NULL,
            event_key TEXT NOT NULL,
            payload TEXT NOT NULL,
            payload_sha256 TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            attempt INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 5,
            available_at REAL NOT NULL,
            lease_token_hash TEXT,
            lease_until REAL,
            error_code TEXT,
            error_message TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            acknowledged_at REAL,
            payload_tombstoned_at REAL,
            UNIQUE(service_account_id, event_key)
        );
        CREATE INDEX IF NOT EXISTS idx_relay_events_pull
            ON relay_events(owner_id, device_id, status, available_at, created_at);

        CREATE TABLE IF NOT EXISTS service_rate_windows (
            service_account_id TEXT NOT NULL,
            window_start INTEGER NOT NULL,
            count INTEGER NOT NULL,
            PRIMARY KEY(service_account_id, window_start)
        );

        CREATE TABLE IF NOT EXISTS orgs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_orgs_owner ON orgs(owner_id);

        -- 组织成员（owner 不在此表，由 orgs.owner_id 记）。role ∈ Admin/Member/Viewer。
        CREATE TABLE IF NOT EXISTS org_members (
            org_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at REAL NOT NULL,
            PRIMARY KEY (org_id, account_id)
        );
        CREATE TABLE IF NOT EXISTS org_model_policies (
            org_id TEXT PRIMARY KEY,
            policy TEXT NOT NULL DEFAULT '{}',
            revision INTEGER NOT NULL DEFAULT 1,
            updated_by TEXT NOT NULL DEFAULT '',
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_org_members_account ON org_members(account_id);

        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            org_id TEXT,
            owner_id TEXT NOT NULL,
            instruction TEXT NOT NULL DEFAULT '',
            connectors TEXT NOT NULL DEFAULT '[]',
            experts TEXT NOT NULL DEFAULT '[]',
            skills TEXT NOT NULL DEFAULT '[]',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            archived_at REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects(owner_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_projects_org ON projects(org_id);

        -- 项目成员（owner 不在此表）。access = owner OR 此表一行。
        CREATE TABLE IF NOT EXISTS project_members (
            project_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (project_id, account_id)
        );
        CREATE INDEX IF NOT EXISTS idx_project_members_account ON project_members(account_id);

        -- 邀请码：接受后把接受者加为项目成员（role 由邀请指定）。
        CREATE TABLE IF NOT EXISTS invites (
            id TEXT PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            project_id TEXT NOT NULL,
            role TEXT NOT NULL,
            created_by TEXT NOT NULL,
            accepted_by TEXT,
            created_at REAL NOT NULL,
            expires_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_invites_project ON invites(project_id);

        -- 目录 Server 侧同构表（预埋，供 P3 下发）。scope ∈ builtin/org；org 级由 org_id 归属。
        CREATE TABLE IF NOT EXISTS catalog_items (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,      -- experts | connectors | showcase | ...
            scope TEXT NOT NULL DEFAULT 'builtin',
            org_id TEXT,
            kind TEXT NOT NULL DEFAULT '',
            data TEXT NOT NULL DEFAULT '{}',
            enabled INTEGER NOT NULL DEFAULT 1,
            sort INTEGER NOT NULL DEFAULT 0,
            version INTEGER NOT NULL DEFAULT 1,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_catalog_items_cat ON catalog_items(category, scope, sort);

        -- 内置工具目录（WB-266）：数据库是运营策略权威源；name 对应 App 签名代码中的真实实现。
        -- Console 只能管理现有实现的展示/风险/启停/绑定/兼容字段，不能伪造或删除工具实现。
        CREATE TABLE IF NOT EXISTS tool_catalog (
            name TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '',
            risk_level TEXT NOT NULL DEFAULT 'low',
            exposure TEXT NOT NULL DEFAULT 'skill',
            permissions TEXT NOT NULL DEFAULT '[]',
            enabled INTEGER NOT NULL DEFAULT 1,
            bindable INTEGER NOT NULL DEFAULT 0,
            contract_version TEXT NOT NULL DEFAULT '1',
            min_app_version TEXT NOT NULL DEFAULT '1.0.0',
            implementation_type TEXT NOT NULL DEFAULT 'native',
            parameters TEXT NOT NULL DEFAULT '{}',
            scripts TEXT NOT NULL DEFAULT '{}',
            timeout_seconds INTEGER NOT NULL DEFAULT 30,
            output_limit INTEGER NOT NULL DEFAULT 65536,
            sort INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tool_catalog_policy
            ON tool_catalog(enabled, bindable, exposure, sort);

        CREATE TABLE IF NOT EXISTS tool_catalog_audit (
            id TEXT PRIMARY KEY,
            tool_name TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            action TEXT NOT NULL,
            before_data TEXT NOT NULL DEFAULT '{}',
            after_data TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tool_catalog_audit_name
            ON tool_catalog_audit(tool_name, created_at DESC);

        -- Skill 发布控制面（WB-250）：定义正文是不可变 release 快照；状态、测试、审核与
        -- 灰度参数独立演进。catalog_items 仅保存当前公开投影，draft/testing 不会进入下行。
        CREATE TABLE IF NOT EXISTS skill_releases (
            id TEXT PRIMARY KEY,
            catalog_item_id TEXT,
            slug TEXT NOT NULL,
            version INTEGER NOT NULL,
            state TEXT NOT NULL DEFAULT 'draft',
            data TEXT NOT NULL,
            sort INTEGER NOT NULL DEFAULT 0,
            content_hash TEXT NOT NULL,
            base_release_id TEXT NOT NULL DEFAULT '',
            min_app_version TEXT NOT NULL DEFAULT '0.0.0',
            rollout_channel TEXT NOT NULL DEFAULT 'stable',
            rollout_percent INTEGER NOT NULL DEFAULT 100,
            effective_at REAL NOT NULL DEFAULT 0,
            author_id TEXT NOT NULL,
            reviewer_id TEXT NOT NULL DEFAULT '',
            test_status TEXT NOT NULL DEFAULT 'pending',
            test_report TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            published_at REAL,
            UNIQUE(slug, version)
        );
        CREATE INDEX IF NOT EXISTS idx_skill_releases_slug
            ON skill_releases(slug, version DESC);
        CREATE INDEX IF NOT EXISTS idx_skill_releases_state
            ON skill_releases(state, effective_at);

        CREATE TABLE IF NOT EXISTS skill_release_audit (
            id TEXT PRIMARY KEY,
            release_id TEXT NOT NULL,
            action TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_skill_release_audit_release
            ON skill_release_audit(release_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS skill_release_metrics (
            release_id TEXT PRIMARY KEY,
            installs INTEGER NOT NULL DEFAULT 0,
            install_failures INTEGER NOT NULL DEFAULT 0,
            runs INTEGER NOT NULL DEFAULT 0,
            run_failures INTEGER NOT NULL DEFAULT 0,
            rollbacks INTEGER NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL
        );

        -- 团队时间线（WB-062 Phase 3）：本地执行产出上行的只读镜像（append-only）。
        -- 只存元数据 + 可选摘要，绝不含凭据 / 工作区文件。(project_id, ext_id) 唯一 → 重复上报去重。
        CREATE TABLE IF NOT EXISTS timeline_events (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            actor_name TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT 'session',
            title TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            ext_id TEXT,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_timeline_project ON timeline_events(project_id, created_at DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_timeline_ext ON timeline_events(project_id, ext_id);

        -- 项目评论（WB-065）：团队协作讨论，access-gated。append-only。
        CREATE TABLE IF NOT EXISTS comments (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            work_item_id TEXT NOT NULL DEFAULT '',
            author_id TEXT NOT NULL,
            author_name TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_comments_project ON comments(project_id, created_at);

        -- Server 通知（WB-065）：@提及等事件，一行一收件人。
        CREATE TABLE IF NOT EXISTS server_notifications (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '',
            project_id TEXT,
            actor_name TEXT,
            dedupe_key TEXT NOT NULL DEFAULT '',
            read INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_server_notifs_account ON server_notifications(account_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS project_health_state (
            project_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            snapshot TEXT NOT NULL,
            source TEXT NOT NULL,
            checked_at REAL NOT NULL,
            changed_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS project_health_events (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            from_status TEXT NOT NULL,
            to_status TEXT NOT NULL,
            direction TEXT NOT NULL,
            rank_delta INTEGER NOT NULL,
            source TEXT NOT NULL,
            snapshot TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_project_health_events_project
            ON project_health_events(project_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS work_items (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'todo',
            source TEXT NOT NULL DEFAULT '手动',
            assignee TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            priority TEXT NOT NULL DEFAULT '',
            due_date TEXT NOT NULL DEFAULT '',
            start_date TEXT NOT NULL DEFAULT '',
            labels TEXT NOT NULL DEFAULT '[]',
            parent_id TEXT NOT NULL DEFAULT '',
            milestone_id TEXT NOT NULL DEFAULT '',
            estimate_h REAL NOT NULL DEFAULT 0,
            spent_h REAL NOT NULL DEFAULT 0,
            custom_fields TEXT NOT NULL DEFAULT '{}',
            dependency_ids TEXT NOT NULL DEFAULT '[]',
            sprint_id TEXT NOT NULL DEFAULT '',
            sort INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_work_items_project ON work_items(project_id, status, sort);

        CREATE TABLE IF NOT EXISTS project_custom_fields (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL,
            field_type TEXT NOT NULL DEFAULT 'text',
            options TEXT NOT NULL DEFAULT '[]',
            required INTEGER NOT NULL DEFAULT 0,
            sort INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_project_custom_fields_project
            ON project_custom_fields(project_id, sort);

        CREATE TABLE IF NOT EXISTS sprints (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            milestone_id TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL,
            goal TEXT NOT NULL DEFAULT '',
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'planned',
            sort INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sprints_project ON sprints(project_id, sort);

        -- WB-295：项目共享 PM 配置（模板/WIP）与用户私有保存视图分层持久化。
        CREATE TABLE IF NOT EXISTS project_pm_settings (
            project_id TEXT PRIMARY KEY,
            templates TEXT NOT NULL DEFAULT '[]',
            wip TEXT NOT NULL DEFAULT '{}',
            updated_by TEXT NOT NULL DEFAULT '',
            updated_at REAL NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS project_pm_views (
            project_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            views TEXT NOT NULL DEFAULT '[]',
            updated_at REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (project_id, account_id)
        );
        CREATE INDEX IF NOT EXISTS idx_project_pm_views_account
            ON project_pm_views(account_id, updated_at DESC);

        CREATE TABLE IF NOT EXISTS milestones (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            due_date TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'open',
            sort INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_milestones_project ON milestones(project_id, sort);

        CREATE TABLE IF NOT EXISTS project_governance (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            record_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT '',
            owner_id TEXT NOT NULL DEFAULT '',
            response TEXT NOT NULL DEFAULT '',
            rationale TEXT NOT NULL DEFAULT '',
            work_item_id TEXT NOT NULL DEFAULT '',
            milestone_id TEXT NOT NULL DEFAULT '',
            run_id TEXT NOT NULL DEFAULT '',
            artifact_id TEXT NOT NULL DEFAULT '',
            evidence_label TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            resolved_at REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_project_governance_project
            ON project_governance(project_id, record_type, status, updated_at DESC);

        CREATE TABLE IF NOT EXISTS project_governance_activity (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            record_id TEXT NOT NULL,
            actor_id TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            sequence INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_project_governance_activity
            ON project_governance_activity(project_id, record_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS work_item_activity (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            work_item_id TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT '',
            detail TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_wi_activity_item ON work_item_activity(work_item_id, created_at);

        CREATE TABLE IF NOT EXISTS work_item_acceptances (
            work_item_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            artifact_count INTEGER NOT NULL,
            accepted_by TEXT NOT NULL,
            accepted_at REAL NOT NULL,
            UNIQUE(project_id, run_id)
        );
        CREATE INDEX IF NOT EXISTS idx_work_item_acceptances_project
            ON work_item_acceptances(project_id, accepted_at DESC);

        -- 项目级团队知识库。WB-290 起本表保存稳定项目 ID 到 WeKnora provider ID 的绑定；
        -- 旧 WB-171 行 provider_id 为空并保持 legacy_pending，等待显式迁移。
        CREATE TABLE IF NOT EXISTS knowledge_bases (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            icon TEXT NOT NULL DEFAULT '📚',
            embedding_id INTEGER NOT NULL DEFAULT 11,
            embedding_dim INTEGER NOT NULL DEFAULT 2048,
            knowledge_type INTEGER NOT NULL DEFAULT 5,
            sentence_size INTEGER NOT NULL DEFAULT 300,
            contextual INTEGER NOT NULL DEFAULT 0,
            tags TEXT NOT NULL DEFAULT '[]',
            provider TEXT NOT NULL DEFAULT 'legacy',
            provider_id TEXT NOT NULL DEFAULT '',
            provider_status TEXT NOT NULL DEFAULT 'legacy_pending',
            provider_error TEXT NOT NULL DEFAULT '',
            sort INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_kb_project ON knowledge_bases(project_id, sort);

        -- 文档：字节存磁盘（storage_path），此表存元数据。vector_status 0 未向量化·1 已·2 失败；
        -- Server 永不设 1（诚实，执行面将来回写）。
        CREATE TABLE IF NOT EXISTS kb_documents (
            id TEXT PRIMARY KEY,
            kb_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            size INTEGER NOT NULL DEFAULT 0,
            content_type TEXT NOT NULL DEFAULT '',
            doc_type TEXT NOT NULL DEFAULT '',
            storage_path TEXT NOT NULL DEFAULT '',
            provider_id TEXT NOT NULL DEFAULT '',
            vector_status INTEGER NOT NULL DEFAULT 0,
            fail_msg TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_kbdoc_kb ON kb_documents(kb_id, created_at);

        CREATE TABLE IF NOT EXISTS settings (
            k TEXT PRIMARY KEY,
            v TEXT NOT NULL DEFAULT '',
            updated_at REAL NOT NULL DEFAULT 0
        );

        -- WB-291：平台敏感配置与普通 settings 分表。API 只写不回读；审计永不保存密钥值。
        CREATE TABLE IF NOT EXISTS platform_secrets (
            k TEXT PRIMARY KEY,
            v TEXT NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS platform_settings_audit (
            id TEXT PRIMARY KEY,
            setting_key TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            action TEXT NOT NULL,
            before_value TEXT NOT NULL DEFAULT '',
            after_value TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_platform_settings_audit_created
            ON platform_settings_audit(created_at DESC);

        CREATE TABLE IF NOT EXISTS auth_audit (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL DEFAULT '',
            actor_id TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL,
            provider TEXT NOT NULL DEFAULT '',
            details TEXT NOT NULL DEFAULT '{}',
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_auth_audit_created
            ON auth_audit(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_auth_audit_account
            ON auth_audit(account_id, created_at DESC);
        """
    )
    conn.commit()
    run_migrations(conn, (
        Migration(1, "existing-schema-baseline", lambda _conn: None),
        Migration(2, "federated-identity-security", migrate_federated_identity_security),
        Migration(3, "governance-activity-sequence", migrate_governance_activity_sequence),
        Migration(4, "account-login-lifecycle", migrate_account_login_lifecycle),
        Migration(5, "relay-terminal-retention", migrate_relay_retention),
        Migration(
            6, "legacy-schema-completion",
            lambda target: migrate_server_legacy_schema(
                target,
                time.time() + min(
                    settings.TOKEN_TTL_SECONDS, settings.TOKEN_LEGACY_GRACE_SECONDS,
                ),
            ),
        ),
        Migration(7, "sso-provider-audit", migrate_sso_provider_audit),
        Migration(8, "work-item-acceptance-idempotency", migrate_work_item_acceptance_idempotency),
        Migration(9, "single-active-sprint", migrate_single_active_sprint),
        Migration(10, "durable-business-plane", migrate_durable_business_plane),
        Migration(11, "device-run-protocol", migrate_device_run_protocol),
    ))
    assert_server_schema(conn)
    # 新 App 版本可补充真实实现，但绝不覆盖 Console 已管理的运营字段。
    # 因而本清单只是 bootstrap/migration 输入，不是运行时管理源。
    now = time.time()
    for tool in DEFAULT_TOOL_CATALOG:
        conn.execute(
            "INSERT OR IGNORE INTO tool_catalog "
            "(name,label,description,category,risk_level,exposure,permissions,enabled,bindable,"
            "contract_version,min_app_version,implementation_type,parameters,scripts,timeout_seconds,"
            "output_limit,sort,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                tool["name"], tool["label"], tool["description"], tool["category"],
                tool["risk_level"], tool["exposure"],
                json.dumps(tool.get("permissions", []), ensure_ascii=False),
                1 if tool.get("enabled", True) else 0,
                1 if tool.get("bindable", False) else 0,
                tool.get("contract_version", "1"), tool.get("min_app_version", "1.0.0"),
                tool.get("implementation_type", "native"),
                json.dumps(tool.get("parameters", {}), ensure_ascii=False),
                json.dumps(tool.get("scripts", {}), ensure_ascii=False),
                int(tool.get("timeout_seconds", 30)), int(tool.get("output_limit", 65536)),
                int(tool.get("sort", 0)), now, now,
            ),
        )
    # WB-336：只升级仍保持产品旧种子原文的技能创建指南；Console 已运营过的定义不覆盖。
    governed_creator = next(
        (item for item in DEFAULT_APP_SKILLS if item.get("slug") == "skill-creator-guide"),
        None,
    )
    if governed_creator:
        legacy_creator_instructions = {
            "帮助用户创建自定义技能：先澄清用途、触发场景、输入输出与约束，整理出稳定英文 slug、名称、描述和完整 Markdown 指令；信息足够后必须调用 create_local_skill 真正创建并安装，不要只给模板或假装已创建。",
        }
        for row in conn.execute(
            "SELECT id,data FROM catalog_items WHERE category='APP_SKILLS' AND scope='builtin'"
        ).fetchall():
            try:
                item = json.loads(row["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            if (
                isinstance(item, dict)
                and item.get("slug") == "skill-creator-guide"
                and item.get("instructions") in legacy_creator_instructions
            ):
                conn.execute(
                    "UPDATE catalog_items SET data=?,version=version+1,updated_at=? WHERE id=?",
                    (json.dumps(governed_creator, ensure_ascii=False), now, row["id"]),
                )
    # WB-215：第三方 SkillHub 改为每台 App 直接访问。清掉旧 Server 镜像、精选与凭据，
    # 防止升级后的 Server 继续向客户端下发历史数据。
    conn.execute(
        "DELETE FROM catalog_items WHERE scope='builtin' AND "
        "(kind IN ('skillhub','skillhub-taxonomy','featured') "
        "OR category IN ('skill','skill-category','SKILLHUB_FEATURED'))"
    )
    conn.execute("DELETE FROM settings WHERE k='skillhub_api_key'")
    # WB-217：Server 首次拥有自有技能目录，并把升级前“全部 APP_SKILLS 即推荐”
    # 的展示结果迁成独立推荐位。写库后运行时只读 catalog_items。
    # 标记后即使运营主动删空推荐位也不会在下次启动被重新填充。
    migrated = conn.execute(
        "SELECT v FROM settings WHERE k='skill_recommendations_v2'"
    ).fetchone()
    if not migrated:
        now = time.time()
        skill_count = conn.execute(
            "SELECT COUNT(*) FROM catalog_items WHERE category='APP_SKILLS' AND scope='builtin'"
        ).fetchone()[0]
        if not skill_count:
            for sort, skill in enumerate(DEFAULT_APP_SKILLS):
                conn.execute(
                    "INSERT INTO catalog_items (id,category,scope,org_id,kind,data,enabled,sort,version,created_at,updated_at) "
                    "VALUES (?,'APP_SKILLS','builtin',NULL,'',?,1,?,1,?,?)",
                    (new_uuid(), json.dumps(skill, ensure_ascii=False), sort, now, now),
                )
        recommendation_count = conn.execute(
            "SELECT COUNT(*) FROM catalog_items WHERE category='SKILL_RECOMMENDATIONS' AND scope='builtin'"
        ).fetchone()[0]
        rows = [] if recommendation_count else conn.execute(
            "SELECT data,sort FROM catalog_items "
            "WHERE category='APP_SKILLS' AND scope='builtin' AND enabled=1 ORDER BY sort"
        ).fetchall()
        for row in rows:
            try:
                skill = json.loads(row["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            slug = str(skill.get("slug", "")).strip() if isinstance(skill, dict) else ""
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", slug):
                continue
            data = {"provider": "agentmate", "skill_slug": slug, "placement": "skills.recommended"}
            conn.execute(
                "INSERT INTO catalog_items (id,category,scope,org_id,kind,data,enabled,sort,version,created_at,updated_at) "
                "VALUES (?,?,'builtin',NULL,'',?,1,?,1,?,?)",
                (new_uuid(), "SKILL_RECOMMENDATIONS", json.dumps(data, ensure_ascii=False), row["sort"], now, now),
            )
        conn.execute(
            "INSERT INTO settings (k,v,updated_at) VALUES ('skill_recommendations_v2','1',?)",
            (now,),
        )
    # WB-267：Skill 分类从自由文本升级为独立权威目录。只迁移一次，避免运营主动删除
    # 未使用分类后重启又被 bootstrap 恢复；存量未知名称使用稳定哈希 slug 保留。
    category_migrated = conn.execute(
        "SELECT v FROM settings WHERE k='skill_categories_v1'"
    ).fetchone()
    if not category_migrated:
        now = time.time()
        categories = [dict(item) for item in DEFAULT_SKILL_CATEGORIES]
        known_names = {str(item["name"]): str(item["slug"]) for item in categories}
        legacy_rows = conn.execute(
            "SELECT rowid,category,data FROM catalog_items WHERE scope='builtin' "
            "AND category IN ('APP_SKILLS','SKILL_RECOMMENDATIONS')"
        ).fetchall()
        for row in legacy_rows:
            try:
                data = json.loads(row["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            name = str(data.get("category") or "").strip() if isinstance(data, dict) else ""
            if name and name not in known_names:
                slug = f"legacy-{hashlib.sha256(name.encode('utf-8')).hexdigest()[:12]}"
                known_names[name] = slug
                categories.append({
                    "slug": slug, "name": name, "icon": "🧩",
                    "description": "从存量 Skill 分类自动迁移。", "sort": len(categories) * 10,
                })
        for position, category in enumerate(categories):
            data = {key: value for key, value in category.items() if key != "sort"}
            conn.execute(
                "INSERT INTO catalog_items "
                "(id,category,scope,org_id,kind,data,enabled,sort,version,created_at,updated_at) "
                "VALUES (?,'SKILL_CATEGORIES','builtin',NULL,'',?,1,?,1,?,?)",
                (new_uuid(), json.dumps(data, ensure_ascii=False),
                 int(category.get("sort", position * 10)), now, now),
            )
        for row in legacy_rows:
            if row["category"] != "APP_SKILLS":
                continue
            try:
                data = json.loads(row["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(data, dict):
                continue
            before = json.dumps(data, ensure_ascii=False, sort_keys=True)
            name = str(data.get("category") or "").strip()
            data["category_slug"] = str(data.get("category_slug") or known_names.get(name) or "other")
            resolved = next((item for item in categories if item["slug"] == data["category_slug"]), None)
            if resolved:
                data["category"] = resolved["name"]
            if json.dumps(data, ensure_ascii=False, sort_keys=True) != before:
                conn.execute(
                    "UPDATE catalog_items SET data=?,version=version+1,updated_at=? WHERE rowid=?",
                    (json.dumps(data, ensure_ascii=False), now, row["rowid"]),
                )
        conn.execute(
            "INSERT INTO settings (k,v,updated_at) VALUES ('skill_categories_v1','1',?)",
            (now,),
        )
    # WB-220：连接器定义与推荐位独立。一次性迁移标记保证运营主动清空推荐后不会被重建。
    connector_migrated = conn.execute(
        "SELECT v FROM settings WHERE k='connector_recommendations_v1'"
    ).fetchone()
    if not connector_migrated:
        now = time.time()
        connector_count = conn.execute(
            "SELECT COUNT(*) FROM catalog_items WHERE category='CONN_DEFS' AND scope='builtin'"
        ).fetchone()[0]
        if not connector_count:
            for sort, connector in enumerate(DEFAULT_CONNECTORS):
                conn.execute(
                    "INSERT INTO catalog_items (id,category,scope,org_id,kind,data,enabled,sort,version,created_at,updated_at) "
                    "VALUES (?,'CONN_DEFS','builtin',NULL,'',?,1,?,1,?,?)",
                    (new_uuid(), json.dumps(connector, ensure_ascii=False), sort, now, now),
                )
        recommendation_count = conn.execute(
            "SELECT COUNT(*) FROM catalog_items WHERE category='CONNECTOR_RECOMMENDATIONS' AND scope='builtin'"
        ).fetchone()[0]
        rows = [] if recommendation_count else conn.execute(
            "SELECT data,sort FROM catalog_items WHERE category='CONN_DEFS' "
            "AND scope='builtin' AND enabled=1 ORDER BY sort"
        ).fetchall()
        for row in rows:
            try:
                connector = json.loads(row["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            slug = str(connector.get("slug", "")).strip() if isinstance(connector, dict) else ""
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", slug):
                continue
            data = {"connector_slug": slug, "placement": "connectors.recommended"}
            conn.execute(
                "INSERT INTO catalog_items (id,category,scope,org_id,kind,data,enabled,sort,version,created_at,updated_at) "
                "VALUES (?,'CONNECTOR_RECOMMENDATIONS','builtin',NULL,'',?,1,?,1,?,?)",
                (new_uuid(), json.dumps(data, ensure_ascii=False), row["sort"], now, now),
            )
        conn.execute(
            "INSERT INTO settings (k,v,updated_at) VALUES ('connector_recommendations_v1','1',?)",
            (now,),
        )
    # WB-221：专家真定义与推荐位分离；自定义专家不进入此 Server builtin 目录。
    expert_migrated = conn.execute(
        "SELECT v FROM settings WHERE k='expert_recommendations_v1'"
    ).fetchone()
    if not expert_migrated:
        now = time.time()
        expert_count = conn.execute(
            "SELECT COUNT(*) FROM catalog_items WHERE category='EXPERT_DEFS' AND scope='builtin'"
        ).fetchone()[0]
        if not expert_count:
            for sort, expert in enumerate(DEFAULT_EXPERTS):
                data = {k: v for k, v in expert.items() if k != "recommended"}
                conn.execute(
                    "INSERT INTO catalog_items (id,category,scope,org_id,kind,data,enabled,sort,version,created_at,updated_at) "
                    "VALUES (?,'EXPERT_DEFS','builtin',NULL,'',?,1,?,1,?,?)",
                    (new_uuid(), json.dumps(data, ensure_ascii=False), sort, now, now),
                )
        recommendation_count = conn.execute(
            "SELECT COUNT(*) FROM catalog_items WHERE category='EXPERT_RECOMMENDATIONS' AND scope='builtin'"
        ).fetchone()[0]
        if not recommendation_count:
            recommended_slugs = {str(e["slug"]) for e in DEFAULT_EXPERTS if e.get("recommended")}
            rows = conn.execute(
                "SELECT data,sort FROM catalog_items WHERE category='EXPERT_DEFS' "
                "AND scope='builtin' AND enabled=1 ORDER BY sort"
            ).fetchall()
            for row in rows:
                try:
                    expert = json.loads(row["data"])
                except (json.JSONDecodeError, TypeError):
                    continue
                slug = str(expert.get("slug", "")).strip() if isinstance(expert, dict) else ""
                if slug not in recommended_slugs:
                    continue
                data = {"expert_slug": slug, "placement": "experts.recommended"}
                conn.execute(
                    "INSERT INTO catalog_items (id,category,scope,org_id,kind,data,enabled,sort,version,created_at,updated_at) "
                    "VALUES (?,'EXPERT_RECOMMENDATIONS','builtin',NULL,'',?,1,?,1,?,?)",
                    (new_uuid(), json.dumps(data, ensure_ascii=False), row["sort"], now, now),
                )
        conn.execute(
            "INSERT INTO settings (k,v,updated_at) VALUES ('expert_recommendations_v1','1',?)",
            (now,),
        )
    # WB-231：团队是独立目录，但成员必须引用 EXPERT_DEFS 的稳定 slug。
    teams_migrated = conn.execute(
        "SELECT v FROM settings WHERE k='expert_teams_v1'"
    ).fetchone()
    if not teams_migrated:
        now = time.time()
        team_count = conn.execute(
            "SELECT COUNT(*) FROM catalog_items WHERE category='EXP_TEAMS' AND scope='builtin'"
        ).fetchone()[0]
        if not team_count:
            for sort, team in enumerate(DEFAULT_EXPERT_TEAMS):
                conn.execute(
                    "INSERT INTO catalog_items (id,category,scope,org_id,kind,data,enabled,sort,version,created_at,updated_at) "
                    "VALUES (?,'EXP_TEAMS','builtin',NULL,'',?,1,?,1,?,?)",
                    (new_uuid(), json.dumps(team, ensure_ascii=False), sort, now, now),
                )
        conn.execute(
            "INSERT INTO settings (k,v,updated_at) VALUES ('expert_teams_v1','1',?)",
            (now,),
        )
    conn.commit()
    # 一次性：存量 work_items.assignee 自由文本 → account_id 强映射（WB-112c-B）。
    if get_setting("assignee_norm_v1") != "1":
        migrate_assignees_to_account_id()
        set_setting("assignee_norm_v1", "1")


# ---- password / tokens --------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: Optional[str]) -> bool:
    if not stored:
        return False
    try:
        parts = stored.split("$")
        if parts[0] == "scrypt":
            _algo, n, r, p, salt, hexdk = parts
            dk = hashlib.scrypt(
                password.encode("utf-8"), salt=bytes.fromhex(salt),
                n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(hexdk)),
            )
        else:
            _algo, iters, salt, hexdk = parts
            dk = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iters)
            )
        return secrets.compare_digest(dk.hex(), hexdk)
    except Exception:  # noqa: BLE001
        return False


def password_needs_rehash(stored: str) -> bool:
    return not stored.startswith("scrypt$16384$8$1$")


def upgrade_password_hash(account_id: str, password: str) -> None:
    get_conn().execute(
        "UPDATE accounts SET password_hash=?,password_login_enabled=1 WHERE id=?",
        (hash_password(password), account_id),
    )
    get_conn().commit()


def _token_key(token: str) -> str:
    return "sha256:" + hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_token(
    account_id: str, *, conn: Optional[sqlite3.Connection] = None,
) -> tuple[str, float]:
    target = conn or get_conn()
    account = target.execute(
        "SELECT suspended_at FROM accounts WHERE id=?", (account_id,)
    ).fetchone()
    if not account or float(account["suspended_at"] or 0) > 0:
        raise ValueError("account_suspended_or_missing")
    token = secrets.token_hex(32)
    now = time.time()
    expires_at = now + settings.TOKEN_TTL_SECONDS
    target.execute(
        "INSERT INTO server_tokens (token, account_id, created_at, expires_at) VALUES (?,?,?,?)",
        (_token_key(token), account_id, now, expires_at),
    )
    if conn is None:
        target.commit()
    return token, expires_at


def account_id_for_token(token: str) -> Optional[str]:
    conn = get_conn()
    row = conn.execute(
        "SELECT account_id, expires_at FROM server_tokens WHERE token=?", (_token_key(token),)
    ).fetchone()
    if not row:
        return None
    if float(row["expires_at"] or 0) <= time.time():
        conn.execute("DELETE FROM server_tokens WHERE token=?", (_token_key(token),))
        conn.commit()
        return None
    return row["account_id"]


def token_expires_at(token: str) -> Optional[float]:
    row = get_conn().execute(
        "SELECT expires_at FROM server_tokens WHERE token=?", (_token_key(token),)
    ).fetchone()
    return float(row["expires_at"]) if row and float(row["expires_at"] or 0) > time.time() else None


def delete_token(token: str) -> None:
    get_conn().execute("DELETE FROM server_tokens WHERE token=?", (_token_key(token),))
    get_conn().commit()


# ---- accounts -----------------------------------------------------------

def _row_to_account(r: sqlite3.Row) -> Account:
    keys = r.keys()
    return Account(
        id=r["id"], name=r["name"], email=r["email"], plan=r["plan"], created_at=r["created_at"],
        is_platform_admin=bool(r["is_platform_admin"]) if "is_platform_admin" in keys else False,
        password_login_enabled=(
            bool(r["password_login_enabled"]) if "password_login_enabled" in keys else True
        ),
        suspended_at=float(r["suspended_at"] or 0) if "suspended_at" in keys else 0,
    )


def create_account(
    *, name: str, password: str, email: str = "", plan: str = "体验版",
    password_login_enabled: bool = True, is_platform_admin: bool = False,
) -> Account:
    a = Account(id=new_uuid(), name=name[:60], email=email[:120], plan=plan, created_at=time.time(),
                is_platform_admin=is_platform_admin,
                password_login_enabled=password_login_enabled)
    get_conn().execute(
        "INSERT INTO accounts (id,name,email,plan,password_hash,created_at,is_platform_admin,password_login_enabled) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (a.id, a.name, a.email, a.plan, hash_password(password), a.created_at,
         int(a.is_platform_admin), int(password_login_enabled)),
    )
    get_conn().commit()
    return a


def bootstrap_admin(*, name: str, password: str, email: str = "") -> Account:
    """Create the only first administrator under a database write lock."""
    conn = get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        if int(conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]) != 0:
            raise ValueError("bootstrap_already_completed")
        account = Account(
            id=new_uuid(), name=name[:60], email=email[:120], plan="体验版",
            created_at=time.time(), is_platform_admin=True,
            password_login_enabled=True,
        )
        conn.execute(
            "INSERT INTO accounts "
            "(id,name,email,plan,password_hash,created_at,is_platform_admin,password_login_enabled) "
            "VALUES (?,?,?,?,?,?,1,1)",
            (account.id, account.name, account.email, account.plan,
             hash_password(password), account.created_at),
        )
        record_auth_audit(
            action="bootstrap_admin_created", account_id=account.id,
            actor_id=account.id, conn=conn,
        )
        conn.commit()
        return account
    except Exception:
        conn.rollback()
        raise


def get_account(account_id: str) -> Optional[Account]:
    r = get_conn().execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    return _row_to_account(r) if r else None


def get_account_by_name(name: str) -> Optional[tuple[Account, str]]:
    """(account, password_hash) for login, or None."""
    r = get_conn().execute("SELECT * FROM accounts WHERE name=?", (name,)).fetchone()
    return (
        (_row_to_account(r), r["password_hash"])
        if r and bool(r["password_login_enabled"]) and float(r["suspended_at"] or 0) <= 0
        else None
    )


def find_account_by_name(name: str) -> Optional[Account]:
    r = get_conn().execute("SELECT * FROM accounts WHERE name=?", (name,)).fetchone()
    return _row_to_account(r) if r else None


# ---- accounts admin（WB-163 平台用户管理）--------------------------------
# 仅平台管理员经 routers/accounts.py 调用；返回富字典（含 last_seen/online/项目数），供管理台账。

def owned_projects_count(account_id: str) -> int:
    return get_conn().execute("SELECT COUNT(*) FROM projects WHERE owner_id=?", (account_id,)).fetchone()[0]


def member_projects_count(account_id: str) -> int:
    return get_conn().execute("SELECT COUNT(*) FROM project_members WHERE account_id=?", (account_id,)).fetchone()[0]


def count_platform_admins() -> int:
    return get_conn().execute(
        "SELECT COUNT(*) FROM accounts WHERE is_platform_admin=1 AND suspended_at<=0"
    ).fetchone()[0]


def count_accounts() -> int:
    return int(get_conn().execute("SELECT COUNT(*) FROM accounts").fetchone()[0])


def owned_orgs_count(account_id: str) -> int:
    return int(get_conn().execute(
        "SELECT COUNT(*) FROM orgs WHERE owner_id=?", (account_id,)
    ).fetchone()[0])


def _account_admin_view(a: Account, last_seen: float) -> dict:
    """账号 + 在线状态 + 项目数（owner + 成员），供管理台账。绝不含 password_hash。"""
    d = a.to_dict()
    d["last_seen"] = last_seen
    d["online"] = bool(last_seen) and (time.time() - last_seen) < _ONLINE_WINDOW
    d["owned_projects"] = owned_projects_count(a.id)
    d["member_projects"] = member_projects_count(a.id)
    d["identities"] = list_account_identities(a.id)
    d["active_sessions"] = active_session_count(a.id)
    return d


def list_accounts() -> list[dict]:
    """全部平台账号（按创建时间），含在线/项目数的富视图。"""
    rows = get_conn().execute("SELECT * FROM accounts ORDER BY created_at").fetchall()
    return [_account_admin_view(_row_to_account(r), (r["last_seen"] if "last_seen" in r.keys() else 0) or 0) for r in rows]


def get_account_admin_view(account_id: str) -> Optional[dict]:
    r = get_conn().execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    return _account_admin_view(_row_to_account(r), (r["last_seen"] if "last_seen" in r.keys() else 0) or 0) if r else None


def _guard_active_platform_admin_removal(
    conn: sqlite3.Connection, account_id: str,
) -> Optional[sqlite3.Row]:
    """Lock-protected guard for changes that remove an active platform admin."""
    row = conn.execute(
        "SELECT * FROM accounts WHERE id=?", (account_id,),
    ).fetchone()
    if (
        row is not None
        and bool(row["is_platform_admin"])
        and float(row["suspended_at"] or 0) <= 0
        and int(conn.execute(
            "SELECT COUNT(*) FROM accounts "
            "WHERE is_platform_admin=1 AND suspended_at<=0",
        ).fetchone()[0]) <= 1
    ):
        raise ValueError("last_platform_admin")
    return row


def update_account(account_id: str, *, name: Optional[str] = None, email: Optional[str] = None,
                   plan: Optional[str] = None, is_platform_admin: Optional[bool] = None,
                   actor_id: str = "") -> Optional[Account]:
    """局部更新账号可改字段。name 唯一约束由调用方先查重（撞了这里 sqlite 会抛）。"""
    sets: list[str] = []
    vals: list[Any] = []
    if name is not None:
        sets.append("name=?"); vals.append(name[:60])
    if email is not None:
        sets.append("email=?"); vals.append(email[:120])
    if plan is not None:
        sets.append("plan=?"); vals.append(plan[:40])
    if is_platform_admin is not None:
        sets.append("is_platform_admin=?"); vals.append(int(is_platform_admin))
    if sets:
        conn = get_conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            before_row = conn.execute(
                "SELECT * FROM accounts WHERE id=?", (account_id,),
            ).fetchone()
            if is_platform_admin is False:
                _guard_active_platform_admin_removal(conn, account_id)
            vals.append(account_id)
            conn.execute(f"UPDATE accounts SET {','.join(sets)} WHERE id=?", vals)
            before_admin = bool(before_row["is_platform_admin"]) if before_row else None
            if is_platform_admin is not None and before_admin is not None and before_admin != is_platform_admin:
                record_auth_audit(
                    action="platform_admin_granted" if is_platform_admin else "platform_admin_revoked",
                    account_id=account_id, actor_id=actor_id,
                    details={"before": before_admin, "after": is_platform_admin}, conn=conn,
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return get_account(account_id)


def record_auth_audit(
    *, action: str, account_id: str = "", actor_id: str = "",
    provider: str = "", details: Optional[dict[str, Any]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    target = conn or get_conn()
    target.execute(
        "INSERT INTO auth_audit(id,account_id,actor_id,action,provider,details,created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (new_uuid(), account_id, actor_id, action[:80], provider[:40],
         json.dumps(details or {}, ensure_ascii=False), time.time()),
    )
    if conn is None:
        target.commit()


def list_auth_audit(limit: int = 100, account_id: str = "") -> list[dict[str, Any]]:
    sql = "SELECT * FROM auth_audit"
    values: list[Any] = []
    if account_id:
        sql += " WHERE account_id=?"
        values.append(account_id)
    sql += " ORDER BY created_at DESC,rowid DESC LIMIT ?"
    values.append(max(1, min(limit, 500)))
    rows = get_conn().execute(sql, values).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["details"] = json.loads(item["details"] or "{}")
        except (json.JSONDecodeError, TypeError):
            item["details"] = {}
        result.append(item)
    return result


def active_session_count(account_id: str) -> int:
    return int(get_conn().execute(
        "SELECT COUNT(*) FROM server_tokens WHERE account_id=? AND expires_at>?",
        (account_id, time.time()),
    ).fetchone()[0])


def revoke_account_sessions(
    account_id: str, *, actor_id: str, action: str = "sessions_revoked",
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    target = conn or get_conn()
    changed = target.execute(
        "DELETE FROM server_tokens WHERE account_id=?", (account_id,)
    ).rowcount
    record_auth_audit(
        action=action, account_id=account_id, actor_id=actor_id,
        details={"revoked_sessions": int(changed)}, conn=target,
    )
    if conn is None:
        target.commit()
    return int(changed)


def list_account_identities(account_id: str) -> list[dict[str, Any]]:
    return [dict(row) for row in get_conn().execute(
        "SELECT provider,email,display_name,created_at,last_login_at "
        "FROM external_identities WHERE account_id=? ORDER BY created_at",
        (account_id,),
    ).fetchall()]


def set_account_password(account_id: str, password: str, *, actor_id: str = "") -> None:
    conn = get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            "UPDATE accounts SET password_hash=?,password_login_enabled=1 WHERE id=?",
            (hash_password(password), account_id),
        )
        revoke_account_sessions(
            account_id, actor_id=actor_id, action="password_reset", conn=conn,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def set_password_login_enabled(account_id: str, enabled: bool, *, actor_id: str) -> None:
    conn = get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        account = conn.execute(
            "SELECT id FROM accounts WHERE id=?", (account_id,),
        ).fetchone()
        if account is None:
            raise ValueError("account_not_found")
        if not enabled:
            identities = int(conn.execute(
                "SELECT COUNT(*) FROM external_identities WHERE account_id=?", (account_id,)
            ).fetchone()[0])
            if identities < 1:
                raise ValueError("last_login_method")
        conn.execute(
            "UPDATE accounts SET password_login_enabled=? WHERE id=?",
            (int(enabled), account_id),
        )
        revoke_account_sessions(
            account_id, actor_id=actor_id,
            action="password_login_enabled" if enabled else "password_login_disabled",
            conn=conn,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def set_account_suspended(account_id: str, suspended: bool, *, actor_id: str) -> None:
    conn = get_conn()
    now = time.time() if suspended else 0
    conn.execute("BEGIN IMMEDIATE")
    try:
        if actor_id and account_id == actor_id and suspended:
            raise ValueError("cannot_suspend_self")
        if suspended:
            _guard_active_platform_admin_removal(conn, account_id)
        conn.execute("UPDATE accounts SET suspended_at=? WHERE id=?", (now, account_id))
        if suspended:
            revoke_account_sessions(
                account_id, actor_id=actor_id, action="account_suspended", conn=conn,
            )
            conn.execute(
                "UPDATE service_accounts SET revoked_at=? "
                "WHERE owner_id=? AND revoked_at IS NULL", (now, account_id),
            )
        else:
            record_auth_audit(
                action="account_reactivated", account_id=account_id,
                actor_id=actor_id, conn=conn,
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def delete_account(account_id: str, *, actor_id: str = "") -> None:
    """Atomically revoke credentials and remove an account's authentication state."""
    c = get_conn()
    c.execute("BEGIN IMMEDIATE")
    try:
        if actor_id and account_id == actor_id:
            raise ValueError("cannot_delete_self")
        target = _guard_active_platform_admin_removal(c, account_id)
        if target is None:
            raise ValueError("account_not_found")
        owned_projects = int(c.execute(
            "SELECT COUNT(*) FROM projects WHERE owner_id=?", (account_id,),
        ).fetchone()[0])
        if owned_projects:
            raise ValueError(f"account_owns_projects:{owned_projects}")
        owned_orgs = int(c.execute(
            "SELECT COUNT(*) FROM orgs WHERE owner_id=?", (account_id,),
        ).fetchone()[0])
        if owned_orgs:
            raise ValueError(f"account_owns_orgs:{owned_orgs}")
        record_auth_audit(
            action="account_deleted", account_id=account_id, actor_id=actor_id,
            conn=c,
        )
        service_ids = [row[0] for row in c.execute(
            "SELECT id FROM service_accounts WHERE owner_id=?", (account_id,)
        ).fetchall()]
        for service_id in service_ids:
            c.execute("DELETE FROM service_rate_windows WHERE service_account_id=?", (service_id,))
        c.execute("DELETE FROM relay_events WHERE owner_id=?", (account_id,))
        c.execute("DELETE FROM relay_devices WHERE owner_id=?", (account_id,))
        c.execute("DELETE FROM service_accounts WHERE owner_id=?", (account_id,))
        c.execute("DELETE FROM external_identities WHERE account_id=?", (account_id,))
        c.execute(
            "DELETE FROM sso_attempts WHERE account_id=? OR result_account_id=?",
            (account_id, account_id),
        )
        c.execute("DELETE FROM sso_signup_invites WHERE created_by=?", (account_id,))
        c.execute(
            "UPDATE sso_signup_invites SET consumed_by=NULL WHERE consumed_by=?", (account_id,)
        )
        c.execute("DELETE FROM server_tokens WHERE account_id=?", (account_id,))
        c.execute("DELETE FROM project_members WHERE account_id=?", (account_id,))
        c.execute("DELETE FROM org_members WHERE account_id=?", (account_id,))
        c.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        c.commit()
    except Exception:
        c.rollback()
        raise


# ---- orgs ---------------------------------------------------------------

def _row_to_org(r: sqlite3.Row) -> Org:
    return Org(id=r["id"], name=r["name"], owner_id=r["owner_id"], created_at=r["created_at"])


def create_org(*, name: str, owner_id: str) -> Org:
    o = Org(id=new_uuid(), name=name[:120], owner_id=owner_id, created_at=time.time())
    get_conn().execute(
        "INSERT INTO orgs (id,name,owner_id,created_at) VALUES (?,?,?,?)",
        (o.id, o.name, o.owner_id, o.created_at),
    )
    get_conn().commit()
    return o


def get_org(org_id: str) -> Optional[Org]:
    r = get_conn().execute("SELECT * FROM orgs WHERE id=?", (org_id,)).fetchone()
    return _row_to_org(r) if r else None


def org_role(org_id: str, account_id: str) -> Optional[Role]:
    """Owner if owns the org, else explicit membership role, else None."""
    o = get_conn().execute("SELECT owner_id FROM orgs WHERE id=?", (org_id,)).fetchone()
    if not o:
        return None
    if o["owner_id"] == account_id:
        return Role.OWNER
    r = get_conn().execute(
        "SELECT role FROM org_members WHERE org_id=? AND account_id=?", (org_id, account_id)
    ).fetchone()
    return Role(r["role"]) if r else None


def add_org_member(org_id: str, account_id: str, role: Role) -> None:
    get_conn().execute(
        "INSERT INTO org_members (org_id, account_id, role, created_at) VALUES (?,?,?,?) "
        "ON CONFLICT(org_id, account_id) DO UPDATE SET role=excluded.role",
        (org_id, account_id, role.value, time.time()),
    )
    get_conn().commit()


def list_orgs_for(account_id: str) -> list[tuple[Org, Role]]:
    rows = get_conn().execute(
        """
        SELECT o.*, 'Owner' AS _role FROM orgs o WHERE o.owner_id=?
        UNION
        SELECT o.*, m.role AS _role FROM orgs o
          JOIN org_members m ON m.org_id=o.id
          WHERE m.account_id=? AND o.owner_id<>?
        ORDER BY created_at DESC
        """,
        (account_id, account_id, account_id),
    ).fetchall()
    return [(_row_to_org(r), Role(r["_role"])) for r in rows]


def list_org_members(org_id: str) -> list[dict]:
    o = get_conn().execute("SELECT owner_id FROM orgs WHERE id=?", (org_id,)).fetchone()
    if not o:
        return []
    out: list[dict] = []
    owner = get_account(o["owner_id"])
    if owner:
        out.append({"account_id": owner.id, "name": owner.name, "role": Role.OWNER.value, "is_owner": True})
    rows = get_conn().execute(
        "SELECT m.account_id, m.role, a.name FROM org_members m JOIN accounts a ON a.id=m.account_id "
        "WHERE m.org_id=? ORDER BY m.created_at",
        (org_id,),
    ).fetchall()
    for r in rows:
        out.append({"account_id": r["account_id"], "name": r["name"], "role": r["role"], "is_owner": False})
    return out


# ---- projects -----------------------------------------------------------

def _row_to_project(r: sqlite3.Row) -> Project:
    return Project(
        id=r["id"], name=r["name"], org_id=r["org_id"], owner_id=r["owner_id"],
        instruction=r["instruction"], connectors=json.loads(r["connectors"]),
        experts=json.loads(r["experts"]), skills=json.loads(r["skills"]),
        created_at=r["created_at"], updated_at=r["updated_at"],
        archived_at=float(r["archived_at"] or 0) if "archived_at" in r.keys() else 0,
    )


def create_project(
    *, name: str, owner_id: str, org_id: Optional[str] = None, instruction: str = "",
    connectors: Optional[list[str]] = None, experts: Optional[list[str]] = None,
    skills: Optional[list[str]] = None,
) -> Project:
    now = time.time()
    p = Project(
        id=new_uuid(), name=name[:120], org_id=org_id, owner_id=owner_id, instruction=instruction,
        connectors=connectors or [], experts=experts or [], skills=skills or [],
        created_at=now, updated_at=now, archived_at=0,
    )
    get_conn().execute(
        """INSERT INTO projects (id,name,org_id,owner_id,instruction,connectors,experts,skills,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (p.id, p.name, p.org_id, p.owner_id, p.instruction,
         json.dumps(p.connectors, ensure_ascii=False), json.dumps(p.experts, ensure_ascii=False),
         json.dumps(p.skills, ensure_ascii=False), p.created_at, p.updated_at),
    )
    get_conn().commit()
    return p


def get_project(project_id: str) -> Optional[Project]:
    r = get_conn().execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    return _row_to_project(r) if r else None


def project_member_role(project_id: str, account_id: str) -> Optional[Role]:
    r = get_conn().execute(
        "SELECT role FROM project_members WHERE project_id=? AND account_id=?", (project_id, account_id)
    ).fetchone()
    return Role(r["role"]) if r else None


def project_access_role(project_id: str, account_id: str) -> Optional[Role]:
    """单一访问闸：Owner if owns, else membership role, else None. 与 backend 同名同义。"""
    r = get_conn().execute("SELECT owner_id FROM projects WHERE id=?", (project_id,)).fetchone()
    if not r:
        return None
    if r["owner_id"] == account_id:
        return Role.OWNER
    return project_member_role(project_id, account_id)


def project_is_archived(project_id: str) -> bool:
    row = get_conn().execute("SELECT archived_at FROM projects WHERE id=?", (project_id,)).fetchone()
    return bool(row and float(row["archived_at"] or 0) > 0)


def update_project(project_id: str, **fields: Any) -> Optional[Project]:
    cols = {"name", "org_id", "instruction", "connectors", "experts", "skills", "archived_at"}
    sets, vals = [], []
    for k, v in fields.items():
        if k not in cols:
            continue
        if k in ("connectors", "experts", "skills"):
            sets.append(f"{k}=?"); vals.append(json.dumps(v, ensure_ascii=False))
        elif k == "org_id":
            sets.append("org_id=?"); vals.append(v or None)
        else:
            sets.append(f"{k}=?"); vals.append(v[:120] if k == "name" else v)
    if not sets:
        return get_project(project_id)
    sets.append("updated_at=?"); vals.append(time.time())
    vals.append(project_id)
    get_conn().execute(f"UPDATE projects SET {', '.join(sets)} WHERE id=?", vals)
    get_conn().commit()
    return get_project(project_id)


def touch_project(project_id: str) -> None:
    """Knowledge bindings are part of the project downlink contract."""
    get_conn().execute("UPDATE projects SET updated_at=? WHERE id=?", (time.time(), project_id))
    get_conn().commit()


def list_projects_for(account_id: str, *, include_archived: bool = False) -> list[tuple[Project, Role]]:
    active = "" if include_archived else " AND p.archived_at=0"
    rows = get_conn().execute(
        f"""
        SELECT p.*, 'Owner' AS _role FROM projects p WHERE p.owner_id=?{active}
        UNION
        SELECT p.*, m.role AS _role FROM projects p
          JOIN project_members m ON m.project_id=p.id
          WHERE m.account_id=? AND p.owner_id<>?{active}
        ORDER BY updated_at DESC
        """,
        (account_id, account_id, account_id),
    ).fetchall()
    return [(_row_to_project(r), Role(r["_role"])) for r in rows]


def transfer_project_owner(project_id: str, current_owner_id: str, next_owner_id: str) -> Optional[Project]:
    conn = get_conn()
    row = conn.execute("SELECT owner_id FROM projects WHERE id=?", (project_id,)).fetchone()
    if not row or row["owner_id"] != current_owner_id:
        return None
    member = conn.execute(
        "SELECT role FROM project_members WHERE project_id=? AND account_id=?",
        (project_id, next_owner_id),
    ).fetchone()
    if not member or member["role"] not in {Role.ADMIN.value, Role.MEMBER.value}:
        return None
    now = time.time()
    conn.execute("UPDATE projects SET owner_id=?,updated_at=? WHERE id=?", (next_owner_id, now, project_id))
    conn.execute("DELETE FROM project_members WHERE project_id=? AND account_id=?", (project_id, next_owner_id))
    conn.execute(
        "INSERT INTO project_members (project_id,account_id,role,created_at,updated_at) VALUES (?,?,?,?,?) "
        "ON CONFLICT(project_id,account_id) DO UPDATE SET role=excluded.role,updated_at=excluded.updated_at",
        (project_id, current_owner_id, Role.ADMIN.value, now, now),
    )
    conn.commit()
    return get_project(project_id)


def project_delete_counts(project_id: str) -> dict[str, int]:
    conn = get_conn()
    tables = {
        "members": "project_members", "tasks": "work_items", "knowledge_bases": "knowledge_bases",
        "milestones": "milestones", "sprints": "sprints", "comments": "comments",
        "governance": "project_governance",
        "sessions": "business_sessions", "runs": "business_runs",
        "assistants": "business_assistants", "automations": "business_automations",
        "assets": "business_assets",
    }
    return {
        key: int(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE project_id=?", (project_id,)).fetchone()[0])
        for key, table in tables.items()
    }


def delete_project(project_id: str) -> bool:
    """Delete an archived project after external knowledge resources have been removed."""
    conn = get_conn()
    project = conn.execute("SELECT archived_at FROM projects WHERE id=?", (project_id,)).fetchone()
    if not project or float(project["archived_at"] or 0) <= 0:
        return False
    if conn.execute("SELECT 1 FROM knowledge_bases WHERE project_id=? LIMIT 1", (project_id,)).fetchone():
        raise ValueError("project still has knowledge bases")
    for table in (
        "project_members", "invites", "timeline_events", "comments", "server_notifications",
        "project_health_state", "project_health_events",
        "work_item_activity", "work_items", "project_custom_fields", "sprints", "milestones",
        "project_governance_activity", "project_governance",
        "kb_documents", "project_pm_settings", "project_pm_views",
    ):
        conn.execute(f"DELETE FROM {table} WHERE project_id=?", (project_id,))
    cur = conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
    conn.commit()
    return cur.rowcount > 0


def get_project_pm_preferences(project_id: str, account_id: str) -> dict[str, Any]:
    conn = get_conn()
    shared = conn.execute(
        "SELECT templates,wip,updated_at FROM project_pm_settings WHERE project_id=?", (project_id,)
    ).fetchone()
    personal = conn.execute(
        "SELECT views,updated_at FROM project_pm_views WHERE project_id=? AND account_id=?",
        (project_id, account_id),
    ).fetchone()
    def decoded(row: Optional[sqlite3.Row], key: str, fallback: Any) -> Any:
        if not row:
            return fallback
        try:
            return json.loads(row[key] or "")
        except (json.JSONDecodeError, TypeError):
            return fallback
    return {
        "templates": decoded(shared, "templates", []),
        "wip": decoded(shared, "wip", {}),
        "views": decoded(personal, "views", []),
        "shared_updated_at": float(shared["updated_at"] or 0) if shared else 0,
        "views_updated_at": float(personal["updated_at"] or 0) if personal else 0,
    }


def save_project_pm_preferences(
    project_id: str, account_id: str, *, templates: Optional[list[dict]] = None,
    wip: Optional[dict[str, int]] = None, views: Optional[list[dict]] = None,
    expected_shared_updated_at: Optional[float] = None,
    expected_views_updated_at: Optional[float] = None,
) -> bool:
    """Atomically update PM preferences when the caller's revisions are current."""
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        shared = conn.execute(
            "SELECT templates,wip,updated_at FROM project_pm_settings WHERE project_id=?",
            (project_id,),
        ).fetchone()
        personal = conn.execute(
            "SELECT views,updated_at FROM project_pm_views WHERE project_id=? AND account_id=?",
            (project_id, account_id),
        ).fetchone()
        shared_revision = float(shared["updated_at"] or 0) if shared else 0
        views_revision = float(personal["updated_at"] or 0) if personal else 0
        if expected_shared_updated_at is not None and shared_revision != expected_shared_updated_at:
            conn.rollback()
            return False
        if expected_views_updated_at is not None and views_revision != expected_views_updated_at:
            conn.rollback()
            return False

        def decoded(row: Optional[sqlite3.Row], key: str, fallback: Any) -> Any:
            if not row:
                return fallback
            try:
                return json.loads(row[key] or "")
            except (json.JSONDecodeError, TypeError):
                return fallback

        if templates is not None or wip is not None:
            next_templates = decoded(shared, "templates", []) if templates is None else templates
            next_wip = decoded(shared, "wip", {}) if wip is None else wip
            now = max(time.time(), shared_revision + 0.000001)
            conn.execute(
                "INSERT INTO project_pm_settings (project_id,templates,wip,updated_by,updated_at) VALUES (?,?,?,?,?) "
                "ON CONFLICT(project_id) DO UPDATE SET templates=excluded.templates,wip=excluded.wip,"
                "updated_by=excluded.updated_by,updated_at=excluded.updated_at",
                (project_id, json.dumps(next_templates, ensure_ascii=False),
                 json.dumps(next_wip, ensure_ascii=False), account_id, now),
            )
        if views is not None:
            now = max(time.time(), views_revision + 0.000001)
            conn.execute(
                "INSERT INTO project_pm_views (project_id,account_id,views,updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT(project_id,account_id) DO UPDATE SET views=excluded.views,updated_at=excluded.updated_at",
                (project_id, account_id, json.dumps(views, ensure_ascii=False), now),
            )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise


def save_project_pm_shared(
    project_id: str, account_id: str, *, templates: Optional[list[dict]] = None,
    wip: Optional[dict[str, int]] = None, expected_updated_at: Optional[float] = None,
) -> bool:
    return save_project_pm_preferences(
        project_id, account_id, templates=templates, wip=wip,
        expected_shared_updated_at=expected_updated_at,
    )


def save_project_pm_views(
    project_id: str, account_id: str, views: list[dict],
    expected_updated_at: Optional[float] = None,
) -> bool:
    return save_project_pm_preferences(
        project_id, account_id, views=views, expected_views_updated_at=expected_updated_at,
    )


def add_project_member(project_id: str, account_id: str, role: Role) -> None:
    now = time.time()
    get_conn().execute(
        "INSERT INTO project_members (project_id, account_id, role, created_at, updated_at) VALUES (?,?,?,?,?) "
        "ON CONFLICT(project_id, account_id) DO UPDATE SET role=excluded.role,updated_at=excluded.updated_at",
        (project_id, account_id, role.value, now, now),
    )
    get_conn().commit()


def remove_project_member(project_id: str, account_id: str) -> None:
    get_conn().execute(
        "DELETE FROM project_members WHERE project_id=? AND account_id=?", (project_id, account_id)
    )
    get_conn().commit()


def list_project_members(project_id: str) -> list[dict]:
    p = get_conn().execute("SELECT owner_id,created_at,updated_at FROM projects WHERE id=?", (project_id,)).fetchone()
    if not p:
        return []
    out: list[dict] = []
    owner = get_account(p["owner_id"])
    if owner:
        out.append({
            "account_id": owner.id, "name": owner.name, "role": Role.OWNER.value, "is_owner": True,
            "created_at": p["created_at"], "updated_at": p["updated_at"],
        })
    rows = get_conn().execute(
        "SELECT m.account_id,m.role,m.created_at,m.updated_at,a.name FROM project_members m JOIN accounts a ON a.id=m.account_id "
        "WHERE m.project_id=? ORDER BY m.created_at",
        (project_id,),
    ).fetchall()
    for r in rows:
        out.append({
            "account_id": r["account_id"], "name": r["name"], "role": r["role"], "is_owner": False,
            "created_at": r["created_at"], "updated_at": r["updated_at"],
        })
    return out


# ---- invites ------------------------------------------------------------

def _row_to_invite(r: sqlite3.Row) -> Invite:
    return Invite(
        id=r["id"], code=r["code"], project_id=r["project_id"], role=Role(r["role"]),
        created_by=r["created_by"], accepted_by=r["accepted_by"],
        created_at=r["created_at"], expires_at=r["expires_at"],
    )


def create_invite(*, project_id: str, role: Role, created_by: str, ttl: int = 0) -> Invite:
    now = time.time()
    inv = Invite(
        id=new_uuid(), code=secrets.token_urlsafe(12), project_id=project_id, role=role,
        created_by=created_by, accepted_by=None, created_at=now,
        expires_at=(now + ttl) if ttl else None,
    )
    get_conn().execute(
        "INSERT INTO invites (id,code,project_id,role,created_by,accepted_by,created_at,expires_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (inv.id, inv.code, inv.project_id, inv.role.value, inv.created_by, None, inv.created_at, inv.expires_at),
    )
    get_conn().commit()
    return inv


def get_invite_by_code(code: str) -> Optional[Invite]:
    r = get_conn().execute("SELECT * FROM invites WHERE code=?", (code,)).fetchone()
    return _row_to_invite(r) if r else None


def accept_invite_once(invite_id: str, project_id: str, account_id: str, role: Role) -> bool:
    """Atomically consume a single-use invite and add its member.

    The conditional update is the serialization point: concurrent acceptors may
    both have read ``accepted_by IS NULL``, but only one can change it.  Member
    creation is kept in the same transaction so neither half can commit alone.
    """
    conn = get_conn()
    now = time.time()
    try:
        conn.execute("BEGIN IMMEDIATE")
        claimed = conn.execute(
            "UPDATE invites SET accepted_by=? WHERE id=? AND accepted_by IS NULL",
            (account_id, invite_id),
        )
        if claimed.rowcount != 1:
            conn.rollback()
            return False
        conn.execute(
            "INSERT INTO project_members (project_id,account_id,role,created_at,updated_at) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(project_id,account_id) DO UPDATE SET "
            "role=excluded.role,updated_at=excluded.updated_at",
            (project_id, account_id, role.value, now, now),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise


# ---- catalog（预埋，供 P3 下发）-----------------------------------------
# Server 侧目录同构表：builtin 由运营下发、org 由团队管理员维护。WB-061 只建表 + 最小读写，
# 完整下发/同步是 P3（WB-063）。

def list_catalog_items(category: str, scope: Optional[str] = None,
                       include_disabled: bool = False) -> list[dict]:
    """某 category 目录项。默认只返回 enabled（客户端下行）；`include_disabled` 时返回全部
    并带 `enabled` 标志——供 AgentMate Console 管理端列出/切换停用项（WB-082）。"""
    where = ["category=?"]
    params: list[Any] = [category]
    if scope:
        where.append("scope=?"); params.append(scope)
    if not include_disabled:
        where.append("enabled=1")
    rows = get_conn().execute(
        f"SELECT * FROM catalog_items WHERE {' AND '.join(where)} ORDER BY sort", params
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        try:
            data = json.loads(r["data"])
        except (json.JSONDecodeError, TypeError):
            data = {}
        out.append({
            "id": r["id"], "category": r["category"], "scope": r["scope"], "org_id": r["org_id"],
            "kind": r["kind"], "data": data, "sort": r["sort"], "version": r["version"],
            "enabled": bool(r["enabled"]),
        })
    return out


def canonical_skill_keys(values: list[str]) -> list[str]:
    """把 Console/旧客户端传来的技能展示名归一成 APP_SKILLS.slug；未知但合法 slug 原样保留。"""
    rows = list_catalog_items("APP_SKILLS", scope="builtin")
    by_slug: dict[str, str] = {}
    by_name: dict[str, list[str]] = {}
    for row in rows:
        data = row.get("data")
        if not isinstance(data, dict):
            continue
        slug = str(data.get("slug", "")).strip()
        name = str(data.get("name", "")).strip()
        if slug:
            by_slug[slug] = slug
            if name:
                by_name.setdefault(name, []).append(slug)
    out: list[str] = []
    for raw in values:
        key = str(raw).strip()
        resolved = by_slug.get(key)
        if not resolved and len(by_name.get(key, [])) == 1:
            resolved = by_name[key][0]
        if not resolved and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", key):
            resolved = key
        if resolved and resolved not in out:
            out.append(resolved)
    return out


def create_catalog_item(
    *, category: str, data: Any, scope: str = "builtin", org_id: Optional[str] = None,
    kind: str = "", sort: int = 0,
) -> str:
    iid = new_uuid()
    now = time.time()
    get_conn().execute(
        "INSERT INTO catalog_items (id,category,scope,org_id,kind,data,enabled,sort,version,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,1,?,1,?,?)",
        (iid, category, scope, org_id, kind, json.dumps(data, ensure_ascii=False), sort, now, now),
    )
    get_conn().commit()
    return iid


def get_catalog_item(item_id: str) -> Optional[dict]:
    r = get_conn().execute("SELECT * FROM catalog_items WHERE id=?", (item_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        d["data"] = json.loads(r["data"])
    except (json.JSONDecodeError, TypeError):
        d["data"] = {}
    return d


def update_catalog_item(item_id: str, *, data: Any = None, sort: Optional[int] = None,
                        enabled: Optional[bool] = None) -> bool:
    sets, vals = [], []
    if data is not None:
        sets.append("data=?"); vals.append(json.dumps(data, ensure_ascii=False))
        # 目录版本只描述定义内容；排序和启停不应让客户端误判技能包有更新。
        sets.append("version=version+1")
    if sort is not None:
        sets.append("sort=?"); vals.append(sort)
    if enabled is not None:
        sets.append("enabled=?"); vals.append(1 if enabled else 0)
    if not sets:
        return False
    sets.append("updated_at=?"); vals.append(time.time())
    vals.append(item_id)
    cur = get_conn().execute(f"UPDATE catalog_items SET {', '.join(sets)} WHERE id=?", vals)
    get_conn().commit()
    return cur.rowcount > 0


def delete_catalog_item(item_id: str) -> bool:
    cur = get_conn().execute("DELETE FROM catalog_items WHERE id=?", (item_id,))
    get_conn().commit()
    return cur.rowcount > 0


def list_all_catalog_items(scope: str = "builtin", include_disabled: bool = False) -> list[dict]:
    """某 scope 下所有目录项（跨 category）。默认只 enabled（客户端一次性下行，WB-066）；
    `include_disabled` 时返回全部并带 `enabled`——供门户高级 JSON 视图（WB-082）。"""
    where = "scope=?" if include_disabled else "scope=? AND enabled=1"
    rows = get_conn().execute(
        f"SELECT * FROM catalog_items WHERE {where} ORDER BY category, sort", (scope,)
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        try:
            data = json.loads(r["data"])
        except (json.JSONDecodeError, TypeError):
            data = {}
        out.append({"id": r["id"], "category": r["category"], "kind": r["kind"], "data": data,
                    "sort": r["sort"], "version": r["version"], "enabled": bool(r["enabled"])})
    return out


# ---- 内置工具目录（WB-266）----------------------------------------------

def _decode_tool_catalog(row: sqlite3.Row | None) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    item = dict(row)
    try:
        item["permissions"] = json.loads(item.get("permissions") or "[]")
    except (json.JSONDecodeError, TypeError):
        item["permissions"] = []
    for key in ("parameters", "scripts"):
        try:
            item[key] = json.loads(item.get(key) or "{}")
        except (json.JSONDecodeError, TypeError):
            item[key] = {}
    item["permissions"] = [str(value) for value in item["permissions"] if str(value)]
    item["enabled"] = bool(item.get("enabled"))
    item["bindable"] = bool(item.get("bindable"))
    return item


def list_tool_catalog(*, include_disabled: bool = False, bindable_only: bool = False) -> list[dict[str, Any]]:
    where: list[str] = []
    if not include_disabled:
        where.append("enabled=1")
    if bindable_only:
        where.append("bindable=1")
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    rows = get_conn().execute(
        f"SELECT * FROM tool_catalog {clause} ORDER BY sort,name"
    ).fetchall()
    return [item for row in rows if (item := _decode_tool_catalog(row)) is not None]


def get_tool_catalog(name: str) -> Optional[dict[str, Any]]:
    return _decode_tool_catalog(
        get_conn().execute("SELECT * FROM tool_catalog WHERE name=?", (name,)).fetchone()
    )


def update_tool_catalog(name: str, *, actor_id: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
    before = get_tool_catalog(name)
    if before is None or not patch:
        return before
    allowed = {
        "label", "description", "category", "risk_level", "enabled", "bindable",
        "min_app_version", "sort", "parameters", "scripts", "timeout_seconds",
        "output_limit", "permissions", "contract_version",
    }
    values = {key: value for key, value in patch.items() if key in allowed}
    if not values:
        return before
    sets: list[str] = []
    params: list[Any] = []
    for key, value in values.items():
        sets.append(f"{key}=?")
        if key in {"enabled", "bindable"}:
            params.append(1 if value else 0)
        elif key in {"permissions", "parameters", "scripts"}:
            params.append(json.dumps(value, ensure_ascii=False))
        else:
            params.append(value)
    now = time.time()
    sets.append("updated_at=?")
    params.extend((now, name))
    get_conn().execute(f"UPDATE tool_catalog SET {', '.join(sets)} WHERE name=?", params)
    after = get_tool_catalog(name)
    get_conn().execute(
        "INSERT INTO tool_catalog_audit "
        "(id,tool_name,actor_id,action,before_data,after_data,created_at) VALUES (?,?,?,?,?,?,?)",
        (
            new_uuid(), name, actor_id, "updated",
            json.dumps(before, ensure_ascii=False, sort_keys=True),
            json.dumps(after or {}, ensure_ascii=False, sort_keys=True), now,
        ),
    )
    get_conn().commit()
    return after


def create_shell_tool(*, actor_id: str, data: dict[str, Any]) -> dict[str, Any]:
    now = time.time()
    conn = get_conn()
    conn.execute(
        """INSERT INTO tool_catalog
           (name,label,description,category,risk_level,exposure,permissions,enabled,bindable,
            contract_version,min_app_version,implementation_type,parameters,scripts,timeout_seconds,
            output_limit,sort,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data["name"], data["label"], data.get("description", ""), data.get("category", "脚本"),
            data.get("risk_level", "high"), "skill",
            json.dumps(data.get("permissions", []), ensure_ascii=False),
            1 if data.get("enabled", True) else 0, 1 if data.get("bindable", True) else 0,
            data.get("contract_version", "1"), data.get("min_app_version", "1.0.0"), "shell",
            json.dumps(data.get("parameters", {}), ensure_ascii=False),
            json.dumps(data.get("scripts", {}), ensure_ascii=False),
            int(data.get("timeout_seconds", 30)), int(data.get("output_limit", 65536)),
            int(data.get("sort", 0)), now, now,
        ),
    )
    created = get_tool_catalog(data["name"]) or {}
    conn.execute(
        "INSERT INTO tool_catalog_audit "
        "(id,tool_name,actor_id,action,before_data,after_data,created_at) VALUES (?,?,?,?,?,?,?)",
        (
            new_uuid(), data["name"], actor_id, "created", "{}",
            json.dumps(created, ensure_ascii=False, sort_keys=True), now,
        ),
    )
    conn.commit()
    return created


def delete_shell_tool(name: str, *, actor_id: str) -> bool:
    before = get_tool_catalog(name)
    if not before or before.get("implementation_type") != "shell":
        return False
    now = time.time()
    conn = get_conn()
    conn.execute("DELETE FROM tool_catalog WHERE name=?", (name,))
    conn.execute(
        "INSERT INTO tool_catalog_audit "
        "(id,tool_name,actor_id,action,before_data,after_data,created_at) VALUES (?,?,?,?,?,?,?)",
        (
            new_uuid(), name, actor_id, "deleted",
            json.dumps(before, ensure_ascii=False, sort_keys=True), "{}", now,
        ),
    )
    conn.commit()
    return True


def list_tool_catalog_audit(name: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = get_conn().execute(
        "SELECT * FROM tool_catalog_audit WHERE tool_name=? ORDER BY created_at DESC, rowid DESC LIMIT ?",
        (name, max(1, min(int(limit), 200))),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for key in ("before_data", "after_data"):
            try:
                item[key] = json.loads(item.get(key) or "{}")
            except (json.JSONDecodeError, TypeError):
                item[key] = {}
        result.append(item)
    return result


# ---- Skill release governance（WB-250）----------------------------------

_SKILL_RELEASE_STATES = {
    "draft", "testing", "approved", "rolling_out", "published", "withdrawn", "superseded",
}


def _decode_skill_release(row: sqlite3.Row | None) -> Optional[dict[str, Any]]:
    if row is None:
        return None
    item = dict(row)
    for field in ("data", "test_report"):
        try:
            item[field] = json.loads(item[field] or "{}")
        except (json.JSONDecodeError, TypeError):
            item[field] = {}
    return item


def create_skill_release(
    *, data: dict[str, Any], sort: int, author_id: str, catalog_item_id: str = "",
    base_release_id: str = "", min_app_version: str = "0.0.0",
) -> dict[str, Any]:
    slug = str(data.get("slug") or "").strip()
    encoded = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    content_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    conn = get_conn()
    now = time.time()
    with conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(version),0)+1 AS version FROM skill_releases WHERE slug=?", (slug,),
        ).fetchone()
        version = int(row["version"] if row else 1)
        release_id = new_uuid()
        conn.execute(
            """INSERT INTO skill_releases
               (id,catalog_item_id,slug,version,state,data,sort,content_hash,base_release_id,
                min_app_version,author_id,created_at,updated_at)
               VALUES (?,?,?,?,'draft',?,?,?,?,?,?,?,?)""",
            (release_id, catalog_item_id or None, slug, version, encoded, int(sort), content_hash,
             base_release_id, min_app_version or "0.0.0", author_id, now, now),
        )
        conn.execute(
            "INSERT INTO skill_release_audit (id,release_id,action,actor_id,details,created_at) "
            "VALUES (?,?,?,?,?,?)",
            (new_uuid(), release_id, "draft_created", author_id, "{}", now),
        )
    return get_skill_release(release_id) or {}


def get_skill_release(release_id: str) -> Optional[dict[str, Any]]:
    return _decode_skill_release(get_conn().execute(
        "SELECT * FROM skill_releases WHERE id=?", (release_id,),
    ).fetchone())


def list_skill_releases(*, slug: str = "", catalog_item_id: str = "") -> list[dict[str, Any]]:
    where, params = [], []
    if slug:
        where.append("slug=?"); params.append(slug)
    if catalog_item_id:
        where.append("catalog_item_id=?"); params.append(catalog_item_id)
    sql = "SELECT * FROM skill_releases"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY slug, version DESC"
    return [_decode_skill_release(row) or {} for row in get_conn().execute(sql, params).fetchall()]


def set_skill_release_state(
    release_id: str, state: str, actor_id: str, *, reviewer_id: str | None = None,
    test_status: str | None = None, test_report: dict[str, Any] | None = None,
    rollout_channel: str | None = None, rollout_percent: int | None = None,
    effective_at: float | None = None, action: str = "state_changed",
    details: dict[str, Any] | None = None,
) -> Optional[dict[str, Any]]:
    if state not in _SKILL_RELEASE_STATES:
        raise ValueError(f"invalid skill release state: {state}")
    sets: list[str] = ["state=?", "updated_at=?"]
    values: list[Any] = [state, time.time()]
    for field, value in (
        ("reviewer_id", reviewer_id), ("test_status", test_status),
        ("test_report", json.dumps(test_report, ensure_ascii=False) if test_report is not None else None),
        ("rollout_channel", rollout_channel), ("rollout_percent", rollout_percent),
        ("effective_at", effective_at),
    ):
        if value is not None:
            sets.append(f"{field}=?"); values.append(value)
    if state in {"rolling_out", "published"}:
        sets.append("published_at=COALESCE(published_at,?)"); values.append(time.time())
    values.append(release_id)
    conn = get_conn()
    with conn:
        cur = conn.execute(f"UPDATE skill_releases SET {', '.join(sets)} WHERE id=?", values)
        if not cur.rowcount:
            return None
        conn.execute(
            "INSERT INTO skill_release_audit (id,release_id,action,actor_id,details,created_at) "
            "VALUES (?,?,?,?,?,?)",
            (new_uuid(), release_id, action, actor_id,
             json.dumps(details or {}, ensure_ascii=False), time.time()),
        )
    return get_skill_release(release_id)


def supersede_other_skill_releases(slug: str, release_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE skill_releases SET state='superseded',updated_at=? "
            "WHERE slug=? AND id<>? AND state IN ('rolling_out','published')",
            (time.time(), slug, release_id),
        )


def attach_skill_release_catalog_item(release_id: str, catalog_item_id: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE skill_releases SET catalog_item_id=?,updated_at=? WHERE id=?",
            (catalog_item_id, time.time(), release_id),
        )


def skill_release_audit(release_id: str) -> list[dict[str, Any]]:
    rows = get_conn().execute(
        "SELECT * FROM skill_release_audit WHERE release_id=? ORDER BY created_at DESC", (release_id,),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["details"] = json.loads(item["details"] or "{}")
        except (json.JSONDecodeError, TypeError):
            item["details"] = {}
        result.append(item)
    return result


def skill_release_metrics(release_id: str) -> dict[str, Any]:
    row = get_conn().execute(
        "SELECT * FROM skill_release_metrics WHERE release_id=?", (release_id,),
    ).fetchone()
    return dict(row) if row else {
        "release_id": release_id, "installs": 0, "install_failures": 0,
        "runs": 0, "run_failures": 0, "rollbacks": 0, "updated_at": 0,
    }


def record_skill_release_metric(release_id: str, event: str) -> dict[str, Any]:
    columns = {
        "installed": "installs", "install_failed": "install_failures",
        "run_succeeded": "runs", "run_failed": "run_failures", "rollback": "rollbacks",
    }
    column = columns.get(event)
    if not column:
        raise ValueError("invalid skill release metric event")
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO skill_release_metrics (release_id,updated_at) VALUES (?,?) "
            "ON CONFLICT(release_id) DO UPDATE SET updated_at=excluded.updated_at",
            (release_id, now),
        )
        if event == "run_failed":
            conn.execute(
                "UPDATE skill_release_metrics SET runs=runs+1,run_failures=run_failures+1,updated_at=? "
                "WHERE release_id=?", (now, release_id),
            )
        else:
            conn.execute(
                f"UPDATE skill_release_metrics SET {column}={column}+1,updated_at=? WHERE release_id=?",
                (now, release_id),
            )
    return skill_release_metrics(release_id)


# ---- 平台设置 settings（WB-095）：服务端凭据/配置的 k-v 存储 -------------

def get_setting(k: str) -> Optional[str]:
    r = get_conn().execute("SELECT v FROM settings WHERE k=?", (k,)).fetchone()
    return r["v"] if r else None


def set_setting(k: str, v: str) -> None:
    get_conn().execute(
        "INSERT INTO settings (k,v,updated_at) VALUES (?,?,?) "
        "ON CONFLICT(k) DO UPDATE SET v=excluded.v, updated_at=excluded.updated_at",
        (k, v, time.time()),
    )
    get_conn().commit()


def delete_setting(k: str) -> bool:
    cur = get_conn().execute("DELETE FROM settings WHERE k=?", (k,))
    get_conn().commit()
    return cur.rowcount > 0


def get_platform_secret(k: str) -> Optional[str]:
    row = get_conn().execute("SELECT v FROM platform_secrets WHERE k=?", (k,)).fetchone()
    return row["v"] if row else None


def set_platform_secret(k: str, value: Optional[str]) -> None:
    conn = get_conn()
    if value:
        conn.execute(
            "INSERT INTO platform_secrets (k,v,updated_at) VALUES (?,?,?) "
            "ON CONFLICT(k) DO UPDATE SET v=excluded.v,updated_at=excluded.updated_at",
            (k, value, time.time()),
        )
    else:
        conn.execute("DELETE FROM platform_secrets WHERE k=?", (k,))
    conn.commit()


def add_platform_setting_audit(
    *, setting_key: str, actor_id: str, action: str,
    before_value: str, after_value: str,
) -> None:
    get_conn().execute(
        "INSERT INTO platform_settings_audit "
        "(id,setting_key,actor_id,action,before_value,after_value,created_at) VALUES (?,?,?,?,?,?,?)",
        (new_uuid(), setting_key, actor_id, action, before_value, after_value, time.time()),
    )
    get_conn().commit()


def list_platform_settings_audit(limit: int = 100) -> list[dict[str, Any]]:
    rows = get_conn().execute(
        "SELECT id,setting_key,actor_id,action,before_value,after_value,created_at "
        "FROM platform_settings_audit ORDER BY created_at DESC LIMIT ?",
        (max(1, min(int(limit), 200)),),
    ).fetchall()
    return [dict(row) for row in rows]


def get_org_model_policy(org_id: str) -> Optional[dict[str, Any]]:
    row = get_conn().execute(
        "SELECT policy,revision,updated_by,updated_at FROM org_model_policies WHERE org_id=?",
        (org_id,),
    ).fetchone()
    if not row:
        return None
    try:
        policy = json.loads(row["policy"] or "{}")
    except (json.JSONDecodeError, TypeError):
        policy = {}
    return {
        "org_id": org_id, "policy": policy if isinstance(policy, dict) else {},
        "revision": int(row["revision"] or 0), "updated_by": row["updated_by"],
        "updated_at": float(row["updated_at"] or 0),
    }


def set_org_model_policy(org_id: str, policy: dict[str, Any], actor_id: str) -> dict[str, Any]:
    now = time.time()
    get_conn().execute(
        """INSERT INTO org_model_policies(org_id,policy,revision,updated_by,updated_at)
           VALUES (?,?,1,?,?) ON CONFLICT(org_id) DO UPDATE SET
             policy=excluded.policy,revision=org_model_policies.revision+1,
             updated_by=excluded.updated_by,updated_at=excluded.updated_at""",
        (org_id, json.dumps(policy, ensure_ascii=False, separators=(",", ":")), actor_id, now),
    )
    get_conn().commit()
    return get_org_model_policy(org_id) or {}


def list_org_model_policies_for(account_id: str) -> list[dict[str, Any]]:
    rows = get_conn().execute(
        """SELECT DISTINCT o.id FROM orgs o LEFT JOIN org_members m ON m.org_id=o.id
           WHERE o.owner_id=? OR m.account_id=? ORDER BY o.created_at""",
        (account_id, account_id),
    ).fetchall()
    return [value for row in rows if (value := get_org_model_policy(row["id"])) is not None]


# ---- 团队计划/任务 work_items（WB-081；专业化字段 WB-104）-----------------

def _row_to_work_item(r: sqlite3.Row) -> dict:
    d = dict(r)
    try:
        d["labels"] = json.loads(d.get("labels") or "[]")
    except (json.JSONDecodeError, TypeError):
        d["labels"] = []
    for key, fallback in (("custom_fields", {}), ("dependency_ids", [])):
        try:
            d[key] = json.loads(d.get(key) or json.dumps(fallback))
        except (json.JSONDecodeError, TypeError):
            d[key] = fallback
    return d


def create_work_item(*, project_id: str, title: str, status: str = "todo",
                     source: str = "手动", assignee: str = "", description: str = "",
                     priority: str = "", due_date: str = "", start_date: str = "",
                     labels: Optional[list[str]] = None, parent_id: str = "",
                     milestone_id: str = "", estimate_h: float = 0.0, spent_h: float = 0.0,
                     custom_fields: Optional[dict[str, Any]] = None,
                     dependency_ids: Optional[list[str]] = None, sprint_id: str = "") -> dict:
    wid = new_uuid(); now = time.time()
    mx = get_conn().execute(
        "SELECT COALESCE(MAX(sort),0) FROM work_items WHERE project_id=? AND status=?",
        (project_id, status),
    ).fetchone()[0]
    get_conn().execute(
        "INSERT INTO work_items (id,project_id,title,status,source,assignee,description,"
        "priority,due_date,start_date,labels,parent_id,milestone_id,estimate_h,spent_h,custom_fields,dependency_ids,sprint_id,sort,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (wid, project_id, title, status, source, assignee, description,
         priority, due_date, start_date, json.dumps(labels or [], ensure_ascii=False),
         parent_id, milestone_id, float(estimate_h or 0), float(spent_h or 0),
         json.dumps(custom_fields or {}, ensure_ascii=False),
         json.dumps(dependency_ids or [], ensure_ascii=False), sprint_id, mx + 1, now, now),
    )
    get_conn().commit()
    return get_work_item(wid)  # type: ignore[return-value]


def list_work_items(project_id: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM work_items WHERE project_id=? ORDER BY status, sort", (project_id,)
    ).fetchall()
    return [_row_to_work_item(r) for r in rows]


def migrate_assignees_to_account_id() -> None:
    """一次性把存量 work_items.assignee 由自由文本归一到 account_id（WB-112c-B）：
    按项目成员名匹配 → 该成员 account_id；匹配不上保留原值兜底（铁律不丢数据）。幂等。"""
    conn = get_conn()
    proj_ids = [r["id"] for r in conn.execute("SELECT id FROM projects").fetchall()]
    for pid in proj_ids:
        mem = list_project_members(pid)
        by_id = {m["account_id"] for m in mem}
        by_name = {(m["name"] or "").lower(): m["account_id"] for m in mem if m.get("name")}
        rows = conn.execute(
            "SELECT id, assignee FROM work_items WHERE project_id=? AND assignee!=''", (pid,)
        ).fetchall()
        for r in rows:
            a = (r["assignee"] or "").strip()
            if a and a not in by_id:
                nid = by_name.get(a.lower())
                if nid:
                    conn.execute("UPDATE work_items SET assignee=? WHERE id=?", (nid, r["id"]))
    conn.commit()


def get_work_item(wid: str) -> Optional[dict]:
    r = get_conn().execute("SELECT * FROM work_items WHERE id=?", (wid,)).fetchone()
    return _row_to_work_item(r) if r else None


def update_work_item(wid: str, **fields: Any) -> Optional[dict]:
    allowed = {"title", "status", "source", "assignee", "description", "sort",
               "priority", "due_date", "start_date", "labels", "parent_id", "milestone_id",
               "estimate_h", "spent_h", "custom_fields", "dependency_ids", "sprint_id"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed and v is not None:
            if k in {"labels", "custom_fields", "dependency_ids"}:
                v = json.dumps(v, ensure_ascii=False)
            sets.append(f"{k}=?"); vals.append(v)
    if not sets:
        return get_work_item(wid)
    sets.append("updated_at=?"); vals.append(time.time())
    vals.append(wid)
    cur = get_conn().execute(f"UPDATE work_items SET {', '.join(sets)} WHERE id=?", vals)
    get_conn().commit()
    return get_work_item(wid) if cur.rowcount else None


def accept_work_item_delivery(
    *, project_id: str, work_item_id: str, run_id: str,
    artifact_count: int, actor_id: str, actor_name: str,
) -> tuple[dict, bool]:
    """Atomically accept once; replaying the same attestation returns the same result."""
    conn = get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT * FROM work_items WHERE id=? AND project_id=?",
            (work_item_id, project_id),
        ).fetchone()
        if row is None:
            raise KeyError("work item not found")
        acceptance = conn.execute(
            "SELECT * FROM work_item_acceptances WHERE work_item_id=?",
            (work_item_id,),
        ).fetchone()
        if acceptance is not None:
            if (
                acceptance["run_id"] != run_id
                or int(acceptance["artifact_count"]) != int(artifact_count)
            ):
                raise ValueError("work item was accepted with a different delivery")
            conn.commit()
            current = get_work_item(work_item_id)
            assert current is not None
            return current, True
        if row["status"] != "review":
            raise ValueError("work item is not awaiting acceptance")
        now = time.time()
        conn.execute(
            "UPDATE work_items SET status='done',updated_at=? WHERE id=?",
            (now, work_item_id),
        )
        conn.execute(
            """INSERT INTO work_item_acceptances
               (work_item_id,project_id,run_id,artifact_count,accepted_by,accepted_at)
               VALUES (?,?,?,?,?,?)""",
            (work_item_id, project_id, run_id, int(artifact_count), actor_id, now),
        )
        conn.execute(
            """INSERT INTO work_item_activity
               (id,project_id,work_item_id,actor,kind,detail,created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                new_uuid(), project_id, work_item_id, actor_name, "accepted",
                f"run={run_id}; artifacts={int(artifact_count)}", now,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    accepted = get_work_item(work_item_id)
    assert accepted is not None
    return accepted, False


# ---- 项目风险与决策台账（WB-350）----------------------------------------

def get_project_governance(record_id: str) -> Optional[dict]:
    row = get_conn().execute(
        "SELECT * FROM project_governance WHERE id=?", (record_id,),
    ).fetchone()
    return dict(row) if row else None


def list_project_governance(project_id: str) -> list[dict]:
    return [dict(row) for row in get_conn().execute(
        "SELECT * FROM project_governance WHERE project_id=? ORDER BY updated_at DESC,id",
        (project_id,),
    ).fetchall()]


def create_project_governance(
    *, project_id: str, record_type: str, title: str, description: str, status: str,
    severity: str, owner_id: str, response: str, rationale: str,
    work_item_id: str, milestone_id: str, run_id: str, artifact_id: str,
    evidence_label: str, created_by: str,
) -> dict:
    record_id = new_uuid(); now = time.time()
    resolved_at = now if status in {"closed", "accepted", "superseded"} else 0.0
    get_conn().execute(
        """INSERT INTO project_governance
           (id,project_id,record_type,title,description,status,severity,owner_id,response,rationale,
            work_item_id,milestone_id,run_id,artifact_id,evidence_label,created_by,created_at,updated_at,resolved_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (record_id, project_id, record_type, title, description, status, severity, owner_id,
         response, rationale, work_item_id, milestone_id, run_id, artifact_id, evidence_label,
         created_by, now, now, resolved_at),
    )
    get_conn().commit()
    return get_project_governance(record_id)  # type: ignore[return-value]


def update_project_governance(record_id: str, **fields: Any) -> Optional[dict]:
    allowed = {
        "title", "description", "status", "severity", "owner_id", "response", "rationale",
        "work_item_id", "milestone_id", "run_id", "artifact_id", "evidence_label",
    }
    sets: list[str] = []
    values: list[Any] = []
    for key, value in fields.items():
        if key in allowed and value is not None:
            sets.append(f"{key}=?"); values.append(value)
    if not sets:
        return get_project_governance(record_id)
    if "status" in fields:
        resolved = time.time() if fields["status"] in {"closed", "accepted", "superseded"} else 0.0
        sets.append("resolved_at=?"); values.append(resolved)
    sets.append("updated_at=?"); values.append(time.time())
    values.append(record_id)
    cur = get_conn().execute(
        f"UPDATE project_governance SET {', '.join(sets)} WHERE id=?", values,
    )
    get_conn().commit()
    return get_project_governance(record_id) if cur.rowcount else None


def delete_project_governance(record_id: str) -> bool:
    cur = get_conn().execute("DELETE FROM project_governance WHERE id=?", (record_id,))
    get_conn().commit()
    return cur.rowcount > 0


def log_project_governance_activity(
    *, project_id: str, record_id: str, actor_id: str, kind: str, detail: str = "",
) -> None:
    get_conn().execute(
        """INSERT INTO project_governance_activity
           (id,project_id,record_id,actor_id,kind,detail,sequence,created_at)
           VALUES (?,?,?,?,?,?,COALESCE((SELECT MAX(sequence)+1
                                         FROM project_governance_activity
                                         WHERE project_id=?),1),?)""",
        (new_uuid(), project_id, record_id, actor_id, kind, detail[:2000], project_id, time.time()),
    )
    get_conn().commit()


def list_project_governance_activity(project_id: str, record_id: str = "") -> list[dict]:
    if record_id:
        rows = get_conn().execute(
            "SELECT * FROM project_governance_activity WHERE project_id=? AND record_id=? "
            "ORDER BY sequence DESC,id DESC",
            (project_id, record_id),
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT * FROM project_governance_activity WHERE project_id=? "
            "ORDER BY sequence DESC,id DESC LIMIT 500",
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_project_custom_fields(project_id: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM project_custom_fields WHERE project_id=? ORDER BY sort,created_at", (project_id,),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["options"] = json.loads(item.get("options") or "[]")
        except (json.JSONDecodeError, TypeError):
            item["options"] = []
        item["required"] = bool(item.get("required"))
        result.append(item)
    return result


def create_project_custom_field(*, project_id: str, name: str, field_type: str,
                                options: list[str], required: bool = False) -> dict:
    field_id = new_uuid(); now = time.time()
    sort = get_conn().execute(
        "SELECT COALESCE(MAX(sort),0)+1 FROM project_custom_fields WHERE project_id=?", (project_id,),
    ).fetchone()[0]
    get_conn().execute(
        "INSERT INTO project_custom_fields (id,project_id,name,field_type,options,required,sort,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (field_id, project_id, name, field_type, json.dumps(options, ensure_ascii=False), int(required), sort, now, now),
    )
    get_conn().commit()
    return next(item for item in list_project_custom_fields(project_id) if item["id"] == field_id)


def update_project_custom_field(field_id: str, project_id: str, **fields: Any) -> Optional[dict]:
    allowed = {"name", "field_type", "options", "required", "sort"}
    sets: list[str] = []
    values: list[Any] = []
    for key, value in fields.items():
        if key not in allowed or value is None:
            continue
        if key == "options":
            value = json.dumps(value, ensure_ascii=False)
        elif key == "required":
            value = int(bool(value))
        sets.append(f"{key}=?")
        values.append(value)
    if not sets:
        return next((item for item in list_project_custom_fields(project_id) if item["id"] == field_id), None)
    sets.append("updated_at=?"); values.extend((time.time(), field_id, project_id))
    cur = get_conn().execute(
        f"UPDATE project_custom_fields SET {', '.join(sets)} WHERE id=? AND project_id=?", values
    )
    get_conn().commit()
    if not cur.rowcount:
        return None
    return next((item for item in list_project_custom_fields(project_id) if item["id"] == field_id), None)


def delete_project_custom_field(field_id: str, project_id: str) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM project_custom_fields WHERE id=? AND project_id=?", (field_id, project_id))
    if cur.rowcount:
        rows = conn.execute("SELECT id,custom_fields FROM work_items WHERE project_id=?", (project_id,)).fetchall()
        for row in rows:
            try:
                values = json.loads(row["custom_fields"] or "{}")
            except (json.JSONDecodeError, TypeError):
                values = {}
            if field_id in values:
                values.pop(field_id, None)
                conn.execute("UPDATE work_items SET custom_fields=?,updated_at=? WHERE id=?",
                             (json.dumps(values, ensure_ascii=False), time.time(), row["id"]))
    conn.commit()
    return cur.rowcount > 0


def list_sprints(project_id: str) -> list[dict]:
    return [dict(row) for row in get_conn().execute(
        "SELECT * FROM sprints WHERE project_id=? ORDER BY sort,created_at", (project_id,),
    ).fetchall()]


def get_sprint(sprint_id: str) -> Optional[dict]:
    row = get_conn().execute("SELECT * FROM sprints WHERE id=?", (sprint_id,)).fetchone()
    return dict(row) if row else None


def create_sprint(*, project_id: str, name: str, goal: str, start_date: str,
                  end_date: str, status: str = "planned", milestone_id: str = "") -> dict:
    sprint_id = new_uuid(); now = time.time(); conn = get_conn()
    sort = conn.execute(
        "SELECT COALESCE(MAX(sort),0)+1 FROM sprints WHERE project_id=?", (project_id,),
    ).fetchone()[0]
    if status == "active":
        conn.execute(
            "UPDATE sprints SET status='closed',updated_at=? "
            "WHERE project_id=? AND status='active'",
            (now, project_id),
        )
    conn.execute(
        "INSERT INTO sprints "
        "(id,project_id,milestone_id,name,goal,start_date,end_date,status,sort,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            sprint_id, project_id, milestone_id, name, goal,
            start_date, end_date, status, sort, now, now,
        ),
    )
    conn.commit()
    return get_sprint(sprint_id)  # type: ignore[return-value]


def update_sprint(sprint_id: str, **fields: Any) -> Optional[dict]:
    allowed = {"name", "goal", "start_date", "end_date", "status", "sort", "milestone_id"}
    conn = get_conn()
    current = conn.execute(
        "SELECT project_id FROM sprints WHERE id=?", (sprint_id,),
    ).fetchone()
    if current is None:
        return None
    sets, values = [], []
    for key, value in fields.items():
        if key in allowed and value is not None:
            sets.append(f"{key}=?"); values.append(value)
    if not sets:
        return get_sprint(sprint_id)
    now = time.time()
    if fields.get("status") == "active":
        conn.execute(
            "UPDATE sprints SET status='closed',updated_at=? "
            "WHERE project_id=? AND status='active' AND id<>?",
            (now, current["project_id"], sprint_id),
        )
    sets.append("updated_at=?"); values.extend([now, sprint_id])
    cur = conn.execute(f"UPDATE sprints SET {', '.join(sets)} WHERE id=?", values)
    conn.commit()
    return get_sprint(sprint_id) if cur.rowcount else None


def delete_sprint(sprint_id: str, project_id: str) -> bool:
    conn = get_conn()
    conn.execute("UPDATE work_items SET sprint_id='',updated_at=? WHERE sprint_id=? AND project_id=?",
                 (time.time(), sprint_id, project_id))
    cur = conn.execute("DELETE FROM sprints WHERE id=? AND project_id=?", (sprint_id, project_id))
    conn.commit()
    return cur.rowcount > 0


def delete_work_item(wid: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT project_id FROM work_items WHERE id=?", (wid,)).fetchone()
    if row is not None:
        project_id = row["project_id"]
        now = time.time()
        conn.execute(
            "UPDATE project_governance SET work_item_id='',updated_at=? "
            "WHERE work_item_id=? AND project_id=?",
            (now, wid, project_id),
        )
        # 删除父项默认提升直接子任务为根任务，避免一个普通删除动作静默吞掉整组工作。
        conn.execute(
            "UPDATE work_items SET parent_id='',updated_at=? WHERE parent_id=? AND project_id=?",
            (now, wid, project_id),
        )
        # dependency_ids 是 JSON 列，删除目标后显式清除悬空引用。
        for dependent in conn.execute(
            "SELECT id,dependency_ids FROM work_items WHERE project_id=? AND id!=?",
            (project_id, wid),
        ).fetchall():
            try:
                dependencies = json.loads(dependent["dependency_ids"] or "[]")
            except (json.JSONDecodeError, TypeError):
                dependencies = []
            cleaned = [item for item in dependencies if item != wid]
            if cleaned != dependencies:
                conn.execute(
                    "UPDATE work_items SET dependency_ids=?,updated_at=? WHERE id=?",
                    (json.dumps(cleaned, ensure_ascii=False), now, dependent["id"]),
                )
    conn.execute("DELETE FROM work_item_activity WHERE work_item_id=?", (wid,))
    conn.execute("DELETE FROM work_item_acceptances WHERE work_item_id=?", (wid,))
    cur = conn.execute("DELETE FROM work_items WHERE id=?", (wid,))
    conn.commit()
    return cur.rowcount > 0


# ---- 真·知识库 + 文档 knowledge_bases / kb_documents（WB-171）------------------
# 向量维度由 embedding 模型唯一决定（GLM 建库只吃 embedding_id）；DAO 层强制派生，
# 绝不信客户端传来的 dim（对齐 console.html 的 KB_EMB_DIMS / 铁律#1）。
KB_EMB_DIMS = {3: 1024, 11: 2048, 12: 2048}


def kb_embedding_dim(embedding_id: int) -> int:
    return KB_EMB_DIMS.get(int(embedding_id or 11), 2048)


def _row_to_kb(r: sqlite3.Row) -> dict:
    d = dict(r)
    try:
        d["tags"] = json.loads(d.get("tags") or "[]")
    except (json.JSONDecodeError, TypeError):
        d["tags"] = []
    return d


def create_kb(*, project_id: str, name: str, description: str = "", icon: str = "📚",
              embedding_id: int = 11, knowledge_type: int = 5, sentence_size: int = 300,
              contextual: int = 0, tags: Optional[list[str]] = None,
              provider: str = "legacy", provider_id: str = "",
              provider_status: str = "legacy_pending", provider_error: str = "") -> dict:
    kid = new_uuid(); now = time.time()
    mx = get_conn().execute(
        "SELECT COALESCE(MAX(sort),0) FROM knowledge_bases WHERE project_id=?", (project_id,)
    ).fetchone()[0]
    get_conn().execute(
        "INSERT INTO knowledge_bases (id,project_id,name,description,icon,embedding_id,embedding_dim,"
        "knowledge_type,sentence_size,contextual,tags,provider,provider_id,provider_status,provider_error,"
        "sort,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (kid, project_id, name, description, icon, int(embedding_id), kb_embedding_dim(embedding_id),
          int(knowledge_type), int(sentence_size), 1 if contextual else 0,
          json.dumps(tags or [], ensure_ascii=False), provider, provider_id, provider_status, provider_error,
          mx + 1, now, now),
    )
    get_conn().commit()
    return get_kb(kid)  # type: ignore[return-value]


def list_kbs(project_id: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM knowledge_bases WHERE project_id=? ORDER BY sort, created_at", (project_id,)
    ).fetchall()
    out = []
    for r in rows:
        kb = _row_to_kb(r)
        kb["doc_count"] = count_kb_documents(kb["id"])
        out.append(kb)
    return out


def list_ready_kb_ids(project_id: str) -> list[str]:
    rows = get_conn().execute(
        "SELECT id FROM knowledge_bases WHERE project_id=? AND provider='weknora' "
        "AND provider_id<>'' AND provider_status='ready' ORDER BY sort,created_at",
        (project_id,),
    ).fetchall()
    return [str(row["id"]) for row in rows]


def get_kb(kid: str) -> Optional[dict]:
    r = get_conn().execute("SELECT * FROM knowledge_bases WHERE id=?", (kid,)).fetchone()
    if not r:
        return None
    kb = _row_to_kb(r)
    kb["doc_count"] = count_kb_documents(kid)
    return kb


def update_kb(kid: str, **fields: Any) -> Optional[dict]:
    allowed = {"name", "description", "icon", "embedding_id", "knowledge_type",
               "sentence_size", "contextual", "tags", "sort", "provider", "provider_id",
               "provider_status", "provider_error"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed and v is not None:
            if k == "tags":
                v = json.dumps(v, ensure_ascii=False)
            elif k == "contextual":
                v = 1 if v else 0
            sets.append(f"{k}=?"); vals.append(v)
    if "embedding_id" in fields and fields["embedding_id"] is not None:
        # 维度随模型强派生，绝不独立可改。
        sets.append("embedding_dim=?"); vals.append(kb_embedding_dim(fields["embedding_id"]))
    if not sets:
        return get_kb(kid)
    sets.append("updated_at=?"); vals.append(time.time())
    vals.append(kid)
    cur = get_conn().execute(f"UPDATE knowledge_bases SET {', '.join(sets)} WHERE id=?", vals)
    get_conn().commit()
    return get_kb(kid) if cur.rowcount else None


def delete_kb(kid: str) -> list[str]:
    """删库 + 级联删文档行。返回该库所有文档的 storage_path（供路由删磁盘文件）。库不存在返回 []。"""
    conn = get_conn()
    if conn.execute("SELECT 1 FROM knowledge_bases WHERE id=?", (kid,)).fetchone() is None:
        return []
    paths = [r["storage_path"] for r in
             conn.execute("SELECT storage_path FROM kb_documents WHERE kb_id=?", (kid,)).fetchall()
             if r["storage_path"]]
    conn.execute("DELETE FROM kb_documents WHERE kb_id=?", (kid,))
    conn.execute("DELETE FROM knowledge_bases WHERE id=?", (kid,))
    conn.commit()
    return paths


def count_kb_documents(kid: str) -> int:
    return get_conn().execute(
        "SELECT COUNT(*) FROM kb_documents WHERE kb_id=?", (kid,)
    ).fetchone()[0]


def create_kb_document(*, kb_id: str, project_id: str, filename: str, size: int,
                       content_type: str = "", doc_type: str = "", storage_path: str = "",
                       provider_id: str = "", doc_id: Optional[str] = None) -> dict:
    did = doc_id or new_uuid(); now = time.time()
    get_conn().execute(
        "INSERT INTO kb_documents (id,kb_id,project_id,filename,size,content_type,doc_type,"
        "storage_path,provider_id,vector_status,fail_msg,created_at) VALUES (?,?,?,?,?,?,?,?,?,0,'',?)",
        (did, kb_id, project_id, filename, int(size), content_type, doc_type, storage_path, provider_id, now),
    )
    get_conn().commit()
    return get_kb_document(did)  # type: ignore[return-value]


def list_kb_documents(kb_id: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM kb_documents WHERE kb_id=? ORDER BY created_at DESC", (kb_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_kb_document(did: str) -> Optional[dict]:
    r = get_conn().execute("SELECT * FROM kb_documents WHERE id=?", (did,)).fetchone()
    return dict(r) if r else None


def update_kb_document_provider(did: str, provider_id: str) -> None:
    get_conn().execute(
        "UPDATE kb_documents SET provider_id=?,vector_status=0,fail_msg='' WHERE id=?",
        (provider_id, did),
    )
    get_conn().commit()


def delete_kb_document(did: str) -> Optional[str]:
    """删单文档行，返回其 storage_path（供路由删磁盘文件）；不存在返回 None。"""
    conn = get_conn()
    r = conn.execute("SELECT storage_path FROM kb_documents WHERE id=?", (did,)).fetchone()
    if r is None:
        return None
    conn.execute("DELETE FROM kb_documents WHERE id=?", (did,))
    conn.commit()
    return r["storage_path"] or ""


# ---- 里程碑 milestones（WB-104）---------------------------------------

def create_milestone(*, project_id: str, name: str, description: str = "",
                     due_date: str = "", status: str = "open") -> dict:
    mid = new_uuid(); now = time.time()
    mx = get_conn().execute(
        "SELECT COALESCE(MAX(sort),0) FROM milestones WHERE project_id=?", (project_id,)
    ).fetchone()[0]
    get_conn().execute(
        "INSERT INTO milestones (id,project_id,name,description,due_date,status,sort,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (mid, project_id, name, description, due_date, status, mx + 1, now, now),
    )
    get_conn().commit()
    return get_milestone(mid)  # type: ignore[return-value]


def list_milestones(project_id: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM milestones WHERE project_id=? ORDER BY sort", (project_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_milestone(mid: str) -> Optional[dict]:
    r = get_conn().execute("SELECT * FROM milestones WHERE id=?", (mid,)).fetchone()
    return dict(r) if r else None


def update_milestone(mid: str, **fields: Any) -> Optional[dict]:
    allowed = {"name", "description", "due_date", "status", "sort"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed and v is not None:
            sets.append(f"{k}=?"); vals.append(v)
    if not sets:
        return get_milestone(mid)
    sets.append("updated_at=?"); vals.append(time.time())
    vals.append(mid)
    cur = get_conn().execute(f"UPDATE milestones SET {', '.join(sets)} WHERE id=?", vals)
    get_conn().commit()
    return get_milestone(mid) if cur.rowcount else None


def delete_milestone(mid: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT project_id FROM milestones WHERE id=?", (mid,)).fetchone()
    if row is not None:
        # 只解绑同项目任务，不碰别项目里恰好同 id 引用（WB-157）。
        conn.execute(
            "UPDATE project_governance SET milestone_id='',updated_at=? "
            "WHERE milestone_id=? AND project_id=?",
            (time.time(), mid, row["project_id"]),
        )
        conn.execute("UPDATE work_items SET milestone_id='' WHERE milestone_id=? AND project_id=?",
                     (mid, row["project_id"]))
        conn.execute(
            "UPDATE sprints SET milestone_id='',updated_at=? "
            "WHERE milestone_id=? AND project_id=?",
            (time.time(), mid, row["project_id"]),
        )
    cur = conn.execute("DELETE FROM milestones WHERE id=?", (mid,))
    conn.commit()
    return cur.rowcount > 0


# ---- 任务活动流 work_item_activity（WB-104）---------------------------

def log_work_item_activity(*, project_id: str, work_item_id: str, actor: str,
                           kind: str, detail: str = "") -> None:
    get_conn().execute(
        "INSERT INTO work_item_activity (id,project_id,work_item_id,actor,kind,detail,created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (new_uuid(), project_id, work_item_id, actor, kind, detail, time.time()),
    )
    get_conn().commit()


def list_work_item_activity(project_id: str, work_item_id: Optional[str] = None,
                            limit: int = 100) -> list[dict]:
    if work_item_id:
        rows = get_conn().execute(
            "SELECT * FROM work_item_activity WHERE work_item_id=? ORDER BY created_at DESC LIMIT ?",
            (work_item_id, limit),
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT * FROM work_item_activity WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# ---- 团队时间线（WB-062 Phase 3）----------------------------------------

def add_timeline_event(
    *, project_id: str, actor_id: str, actor_name: str = "", kind: str = "session",
    title: str = "", summary: str = "", ext_id: Optional[str] = None,
) -> bool:
    """append 一条时间线事件，(project_id, ext_id) 去重。返回是否**新插入**（重复上报 → False）。"""
    cur = get_conn().execute(
        "INSERT OR IGNORE INTO timeline_events "
        "(id,project_id,actor_id,actor_name,kind,title,summary,ext_id,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (new_uuid(), project_id, actor_id, actor_name[:60], kind, title[:200], summary[:2000],
         ext_id, time.time()),
    )
    get_conn().commit()
    return cur.rowcount > 0


def list_timeline(project_id: str, limit: int = 100) -> list[dict]:
    rows = get_conn().execute(
        "SELECT id,project_id,actor_id,actor_name,kind,title,summary,ext_id,created_at "
        "FROM timeline_events WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
        (project_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ---- 更深协作：评论 / 通知 / 在线状态（WB-065）--------------------------

def touch_last_seen(account_id: str) -> None:
    get_conn().execute("UPDATE accounts SET last_seen=? WHERE id=?", (time.time(), account_id))
    get_conn().commit()


def add_comment(*, project_id: str, author_id: str, author_name: str, body: str, work_item_id: str = "") -> dict:
    cid = new_uuid()
    now = time.time()
    get_conn().execute(
        "INSERT INTO comments (id,project_id,work_item_id,author_id,author_name,body,created_at) VALUES (?,?,?,?,?,?,?)",
        (cid, project_id, work_item_id, author_id, author_name, body, now),
    )
    get_conn().commit()
    return {"id": cid, "project_id": project_id, "work_item_id": work_item_id, "author_id": author_id,
            "author_name": author_name, "body": body, "created_at": now}


def list_comments(project_id: str, work_item_id: str = "", limit: int = 200) -> list[dict]:
    """work_item_id='' = 项目级评论（任务级评论不混入）；给 wid = 该任务的评论（WB-115）。"""
    rows = get_conn().execute(
        "SELECT * FROM comments WHERE project_id=? AND work_item_id=? ORDER BY created_at ASC LIMIT ?",
        (project_id, work_item_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def add_notification(*, account_id: str, kind: str, title: str, body: str = "",
                     project_id: Optional[str] = None, actor_name: Optional[str] = None,
                     dedupe_key: str = "") -> bool:
    cur = get_conn().execute(
        "INSERT OR IGNORE INTO server_notifications "
        "(id,account_id,kind,title,body,project_id,actor_name,dedupe_key,read,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,0,?)",
        (new_uuid(), account_id, kind, title, body, project_id, actor_name,
         dedupe_key[:500], time.time()),
    )
    get_conn().commit()
    return cur.rowcount > 0


def list_notifications(account_id: str, limit: int = 50) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM server_notifications WHERE account_id=? ORDER BY created_at DESC LIMIT ?",
        (account_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def unread_notification_count(account_id: str) -> int:
    return get_conn().execute(
        "SELECT COUNT(*) FROM server_notifications WHERE account_id=? AND read=0", (account_id,)
    ).fetchone()[0]


def mark_notifications_read(account_id: str, ids: Optional[list[str]] = None) -> None:
    conn = get_conn()
    if ids:
        ph = ",".join("?" * len(ids))
        conn.execute(f"UPDATE server_notifications SET read=1 WHERE account_id=? AND id IN ({ph})", (account_id, *ids))
    else:
        conn.execute("UPDATE server_notifications SET read=1 WHERE account_id=?", (account_id,))
    conn.commit()


def observe_project_health(project_id: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Atomically establish the Server baseline or append one health transition."""
    from shared.project_health import classify_health_transition

    status = str(payload.get("status") or "")
    if status not in {"healthy", "attention", "critical"}:
        return None
    source = "server"
    snapshot = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    now = time.time()
    conn = get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT status FROM project_health_state WHERE project_id=?", (project_id,),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO project_health_state (project_id,status,snapshot,source,checked_at,changed_at) "
                "VALUES (?,?,?,?,?,?)",
                (project_id, status, snapshot, source, now, now),
            )
            conn.commit()
            return None
        transition = classify_health_transition(str(row["status"]), status)
        if transition is None:
            conn.execute(
                "UPDATE project_health_state SET snapshot=?,source=?,checked_at=? WHERE project_id=?",
                (snapshot, source, now, project_id),
            )
            conn.commit()
            return None
        event = {
            "id": new_uuid(), "project_id": project_id, **transition,
            "source": source, "snapshot": payload, "created_at": now,
        }
        conn.execute(
            "INSERT INTO project_health_events "
            "(id,project_id,from_status,to_status,direction,rank_delta,source,snapshot,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (event["id"], project_id, event["from_status"], event["to_status"],
             event["direction"], event["rank_delta"], source, snapshot, now),
        )
        conn.execute(
            "UPDATE project_health_state SET status=?,snapshot=?,source=?,checked_at=?,changed_at=? "
            "WHERE project_id=?",
            (status, snapshot, source, now, now, project_id),
        )
        conn.commit()
        return event
    except Exception:
        conn.rollback()
        raise


def list_project_health_events(project_id: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = get_conn().execute(
        "SELECT * FROM project_health_events WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
        (project_id, limit),
    ).fetchall()
    events = []
    for row in rows:
        item = dict(row)
        try:
            item["snapshot"] = json.loads(item["snapshot"])
        except (json.JSONDecodeError, TypeError):
            item["snapshot"] = {}
        events.append(item)
    return events


_ONLINE_WINDOW = 120  # 秒：last_seen 在此窗口内算 online（客户端每请求刷新 + 轮询）


def list_presence(project_id: str) -> list[dict]:
    """项目成员 + last_seen + online（近 _ONLINE_WINDOW 秒活跃）。"""
    now = time.time()
    out: list[dict] = []
    for m in list_project_members(project_id):
        r = get_conn().execute("SELECT last_seen FROM accounts WHERE id=?", (m["account_id"],)).fetchone()
        ls = r["last_seen"] if r else 0
        out.append({**m, "last_seen": ls, "online": bool(ls) and (now - ls) < _ONLINE_WINDOW})
    return out
