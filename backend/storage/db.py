"""SQLite persistence.

Thin DAO over stdlib sqlite3 — no ORM. Chat streaming is the async hot path
(LLM over httpx); DB writes happen at the boundaries of a stream (session create,
message persist) and are quick, so synchronous sqlite calls are fine here.

Connections are thread-local (WB-009): a single shared sqlite3.Connection is not
safe for concurrent use, and this backend touches the DB from both the event-loop
thread (async run_chat) and anyio worker threads (sync routes). Each thread gets
its own connection; WAL mode plus a busy_timeout let those connections write
concurrently without "database is locked" storms.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import mimetypes
import re
import secrets
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from config import settings
from storage.catalog_seed import BUILTIN_CONNECTORS, BUILTIN_EXPERTS, BUILTIN_SKILLS

# 橱窗目录种子源（WB-060）：由 catalog.ts 导出的静态商品卡，逐字迁进本文件同级 JSON，
# 首次启动 seed 进 catalog_showcase 表。放这里而非硬编码在 .py，正是「数据不写死在代码」。
_SHOWCASE_JSON = Path(__file__).resolve().parent / "catalog_showcase.json"
_SKILL_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
from storage.models import (
    LOCAL_USER_ID,
    LOCAL_USER_NAME,
    Automation,
    AutomationFire,
    Artifact,
    CatalogConnector,
    CatalogExpert,
    Expert,
    Message,
    Project,
    Role,
    Run,
    Session,
    User,
    WorkItem,
)

_local = threading.local()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # Wait (up to 5s) for a competing writer instead of failing immediately.
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
    """WB-210：把旧中心服务命名一次性前向迁移为 Server。

    迁移完成后只保留 server_* 表/列和值；运行时没有旧变量、旧路由或双读兼容分支。
    """
    for old, new in (
        ("hub_identities", "server_identities"),
        ("hub_imports", "server_imports"),
        ("hub_link", "server_link"),
    ):
        if _table_exists(conn, old) and not _table_exists(conn, new):
            conn.execute(f"ALTER TABLE {old} RENAME TO {new}")

    for table, columns in (
        ("server_identities", (("hub_token", "server_token"),)),
        ("server_imports", (("hub_id", "server_id"), ("hub_account_id", "server_account_id"))),
        ("server_link", (("hub_account_id", "server_account_id"), ("hub_account_name", "server_account_name"))),
    ):
        if not _table_exists(conn, table):
            continue
        have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for old, new in columns:
            if old in have and new not in have:
                conn.execute(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")

    if _table_exists(conn, "projects"):
        conn.execute("UPDATE projects SET origin='server' WHERE origin='hub'")
    if _table_exists(conn, "catalog_skills"):
        conn.execute("UPDATE catalog_skills SET scope='server' WHERE scope='hub'")
    conn.commit()


def init_db() -> None:
    conn = get_conn()
    _migrate_server_naming(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            plan TEXT NOT NULL,
            password_hash TEXT
        );

        -- Bearer tokens for real accounts (M7 C1). No token on a request → the
        -- fixed local owner, so single-machine use keeps working without login.
        CREATE TABLE IF NOT EXISTS auth_tokens (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_auth_tokens_user ON auth_tokens(user_id);

        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            project_id TEXT,
            space TEXT,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            automation_id TEXT,
            run_status TEXT,
            run_summary TEXT,
            run_kind TEXT
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            actor TEXT NOT NULL,
            trace TEXT NOT NULL DEFAULT '[]',
            usage TEXT,
            created_at REAL NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session
            ON messages(session_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_sessions_owner
            ON sessions(owner_id, updated_at DESC);

        -- A Session is conversation context; every real execution is a Run (WB-242).
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            project_id TEXT,
            work_item_id TEXT,
            mode TEXT NOT NULL,
            status TEXT NOT NULL,
            workspace TEXT NOT NULL DEFAULT 'default',
            idempotency_key TEXT,
            retry_of TEXT,
            plan TEXT NOT NULL DEFAULT '[]',
            permission_snapshot TEXT NOT NULL DEFAULT '{}',
            checkpoint TEXT NOT NULL DEFAULT '{}',
            error_code TEXT,
            error_message TEXT,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            tool_calls INTEGER NOT NULL DEFAULT 0,
            started_at REAL,
            ended_at REAL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_runs_work_item ON runs(work_item_id, created_at DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_owner_idempotency
            ON runs(owner_id, idempotency_key) WHERE idempotency_key IS NOT NULL;

        CREATE TABLE IF NOT EXISTS artifacts (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            project_id TEXT,
            kind TEXT NOT NULL DEFAULT 'file',
            path TEXT NOT NULL,
            name TEXT NOT NULL,
            mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
            source_tool TEXT NOT NULL DEFAULT '',
            size INTEGER NOT NULL DEFAULT 0,
            sha256 TEXT NOT NULL,
            validation_status TEXT NOT NULL DEFAULT 'passed',
            validation TEXT NOT NULL DEFAULT '{}',
            preview_path TEXT,
            acceptance_status TEXT NOT NULL DEFAULT 'pending',
            accepted_by TEXT,
            accepted_at REAL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE,
            UNIQUE (run_id, path)
        );
        CREATE INDEX IF NOT EXISTS idx_artifacts_run ON artifacts(run_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_artifacts_project ON artifacts(project_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            instruction TEXT NOT NULL DEFAULT '',
            connectors TEXT NOT NULL DEFAULT '[]',
            experts TEXT NOT NULL DEFAULT '[]',
            skills TEXT NOT NULL DEFAULT '[]',
            knowledge_ids TEXT NOT NULL DEFAULT '[]',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            origin TEXT NOT NULL DEFAULT 'local',
            server_updated_at REAL NOT NULL DEFAULT 0,
            server_dirty INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_projects_owner
            ON projects(owner_id, updated_at DESC);

        -- 自定义专家（我的专家 · WB-049），owner 维度。persona 在 run_chat 里
        -- 注入系统提示，命中优先于内置 EXPERTS 字典，让自造专家真影响回答。
        CREATE TABLE IF NOT EXISTS experts (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            name TEXT NOT NULL,
            subtitle TEXT NOT NULL DEFAULT '',
            avatar TEXT NOT NULL DEFAULT '🧑',
            intro TEXT NOT NULL DEFAULT '',
            persona TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '[]',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_experts_owner
            ON experts(owner_id, updated_at DESC);

        -- Project membership (M7 C2): who can see/act in a project besides its
        -- owner. The owner has no row here (they're tracked by projects.owner_id);
        -- rows are Admin/Member/Viewer. Access = owner OR a row here.
        CREATE TABLE IF NOT EXISTS project_members (
            project_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL DEFAULT 0,
            server_updated_at REAL NOT NULL DEFAULT 0,
            server_dirty INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (project_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_project_members_user
            ON project_members(user_id);

        CREATE TABLE IF NOT EXISTS work_items (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'todo',
            source TEXT NOT NULL DEFAULT '手动',
            assignee TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            due_date TEXT,
            attachments TEXT NOT NULL DEFAULT '[]',
            priority TEXT NOT NULL DEFAULT '',
            start_date TEXT,
            labels TEXT NOT NULL DEFAULT '[]',
            parent_id TEXT NOT NULL DEFAULT '',
            milestone_id TEXT NOT NULL DEFAULT '',
            estimate_h REAL NOT NULL DEFAULT 0,
            spent_h REAL NOT NULL DEFAULT 0,
            server_updated_at REAL NOT NULL DEFAULT 0,
            server_dirty INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_work_items_project
            ON work_items(project_id, created_at);

        CREATE TABLE IF NOT EXISTS work_item_launches (
            id TEXT PRIMARY KEY,
            work_item_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            session_id TEXT,
            run_id TEXT,
            status TEXT NOT NULL DEFAULT 'queued',
            error_code TEXT,
            error_message TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            finished_at REAL,
            FOREIGN KEY (work_item_id) REFERENCES work_items(id) ON DELETE CASCADE
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_work_item_launches_key
            ON work_item_launches(owner_id, idempotency_key);
        CREATE INDEX IF NOT EXISTS idx_work_item_launches_item
            ON work_item_launches(work_item_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS milestones (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            due_date TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            sort INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            server_updated_at REAL NOT NULL DEFAULT 0,
            server_dirty INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_milestones_project
            ON milestones(project_id, sort);

        CREATE TABLE IF NOT EXISTS automations (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            name TEXT NOT NULL,
            prompt TEXT NOT NULL,
            trigger_kind TEXT NOT NULL DEFAULT 'interval',
            interval_min INTEGER NOT NULL DEFAULT 60,
            at_time TEXT NOT NULL DEFAULT '09:00',
            project_id TEXT,
            model TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            timeout_sec INTEGER NOT NULL DEFAULT 300,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            retry_backoff_sec INTEGER NOT NULL DEFAULT 30,
            max_total_tokens INTEGER NOT NULL DEFAULT 0,
            notify_policy TEXT NOT NULL DEFAULT 'failure,recovery',
            concurrency_policy TEXT NOT NULL DEFAULT 'skip',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            next_run_at REAL NOT NULL,
            last_run_at REAL,
            last_session_id TEXT,
            last_status TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_automations_owner
            ON automations(owner_id, created_at DESC);

        -- One durable logical trigger; retries mutate this row and each attempt is
        -- independently evidenced by its Run + idempotency key (WB-251).
        CREATE TABLE IF NOT EXISTS automation_fires (
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
            error_code TEXT,
            error_message TEXT,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            next_attempt_at REAL,
            notified TEXT NOT NULL DEFAULT '[]',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            finished_at REAL,
            FOREIGN KEY (automation_id) REFERENCES automations(id) ON DELETE CASCADE
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_automation_fires_key
            ON automation_fires(automation_id, fire_key);
        CREATE INDEX IF NOT EXISTS idx_automation_fires_due
            ON automation_fires(status, next_attempt_at);
        CREATE INDEX IF NOT EXISTS idx_automation_fires_owner
            ON automation_fires(owner_id, created_at DESC);

        -- In-app message center (M7 C4): real cross-user events land here, one row
        -- per recipient. Fed by collaboration actions (added to a project, role
        -- changed, removed). read=0 until the user opens the center.
        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL DEFAULT '',
            project_id TEXT,
            actor_name TEXT,
            read INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_notifications_user
            ON notifications(user_id, created_at DESC);

        -- 目录：专家定义（WB-059）。内置人格从硬编码迁到此表（scope='builtin'），
        -- 运行时读库注入。scope/functional/owner_id 为后续 org/user 与橱窗卡（WB-060）预埋。
        CREATE TABLE IF NOT EXISTS catalog_experts (
            id TEXT PRIMARY KEY,
            scope TEXT NOT NULL DEFAULT 'builtin',
            owner_id TEXT,
            slug TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL,
            subtitle TEXT NOT NULL DEFAULT '',
            avatar TEXT NOT NULL DEFAULT '🧑',
            intro TEXT NOT NULL DEFAULT '',
            persona TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '[]',
            category TEXT NOT NULL DEFAULT '',
            badge TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            functional INTEGER NOT NULL DEFAULT 1,
            enabled INTEGER NOT NULL DEFAULT 1,
            sort INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_catalog_experts_name ON catalog_experts(name);

        -- 目录：连接器定义（WB-059）。连接器启动注册表从硬编码迁到此表。
        -- launch = 启动 spec（JSON）；运行时读库解析 spawn/接入 MCP。凭据仍只在 backend/.env。
        CREATE TABLE IF NOT EXISTS catalog_connectors (
            id TEXT PRIMARY KEY,
            scope TEXT NOT NULL DEFAULT 'builtin',
            owner_id TEXT,
            slug TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL,
            icon TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'rdy',
            launch TEXT NOT NULL DEFAULT '{}',
            enabled INTEGER NOT NULL DEFAULT 1,
            sort INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_catalog_connectors_name ON catalog_connectors(name);

        -- 目录：技能定义（WB-183）。补齐 WB-059 漏掉的第三块 —— 技能定义此前一直硬编码在
        -- agent/skills.py 的 SKILLS 字典里（改提示词要改代码重启，改专家却只要改数据）。
        -- instructions = 真定义（注入系统提示，对应专家的 persona / 连接器的 launch）；
        -- tools = 工具名 JSON 数组，运行时由 agent/skills.py::_TOOL_REGISTRY 按名解析成真 Tool
        --   （Tool 是 Python 对象进不了 DB，同连接器「spec 存库、实现在代码」的分工）。
        -- slug 是主键语义（WB-179 的身份统一等它）；迁移期 name 仍是 loadout 实际取值，两者并存。
        CREATE TABLE IF NOT EXISTS catalog_skills (
            id TEXT PRIMARY KEY,
            scope TEXT NOT NULL DEFAULT 'builtin',
            owner_id TEXT,
            slug TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL,
            icon TEXT NOT NULL DEFAULT '🧩',
            description TEXT NOT NULL DEFAULT '',
            instructions TEXT NOT NULL DEFAULT '',
            version TEXT NOT NULL DEFAULT '',
            tools TEXT NOT NULL DEFAULT '[]',
            permissions TEXT NOT NULL DEFAULT '[]',
            tool_contract_version TEXT NOT NULL DEFAULT '1',
            server_release_id TEXT NOT NULL DEFAULT '',
            server_content_hash TEXT NOT NULL DEFAULT '',
            files TEXT NOT NULL DEFAULT '[]',
            category TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            withdrawn INTEGER NOT NULL DEFAULT 0,
            compatible INTEGER NOT NULL DEFAULT 1,
            compatibility_error TEXT NOT NULL DEFAULT '',
            min_app_version TEXT NOT NULL DEFAULT '0.0.0',
            enabled INTEGER NOT NULL DEFAULT 1,
            sort INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_catalog_skills_slug ON catalog_skills(slug);
        CREATE INDEX IF NOT EXISTS idx_catalog_skills_name ON catalog_skills(name);

        -- WB-249：机器级只读包与 owner 级安装/启停状态分离。package_key 指向共享物理包；
        -- 同一包可被多个 owner 引用，删除只软删本行，最后一个引用才允许进入可恢复 trash。
        CREATE TABLE IF NOT EXISTS skill_installations (
            owner_id TEXT NOT NULL,
            slug TEXT NOT NULL,
            package_key TEXT NOT NULL,
            release_id TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            deleted_at REAL,
            trash_path TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (owner_id, slug)
        );
        CREATE INDEX IF NOT EXISTS idx_skill_installations_package
            ON skill_installations(package_key, deleted_at);

        -- 橱窗目录（WB-060）：catalog.ts 的静态商品卡迁到此表，前端改从 /api/catalog 取（静态兜底仍在）。
        -- 通用承载：数组类导出每元素一行（可按行上/下架 enabled、改 sort）；对象类导出（QUICK/CONN_META）
        -- is_scalar=1 单行整存。data = 该元素/对象的 JSON，逐字对齐迁移前。功能定义(专家人格/连接器 spec)
        -- 在 catalog_experts/catalog_connectors(WB-059)，此表只装纯浏览卡——职责分离。
        CREATE TABLE IF NOT EXISTS catalog_showcase (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            sort INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1,
            data TEXT NOT NULL,
            is_scalar INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_catalog_showcase_kind ON catalog_showcase(kind, sort);

        -- 上行同步 outbox（WB-062 Phase 3）：执行产出先落本地，再由后台 worker 推 Server；
        -- 确认后 synced=1；断线/离线自动补推。绝不放凭据/工作区文件进 payload（铁律 4/11）。
        CREATE TABLE IF NOT EXISTS outbox (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            synced INTEGER NOT NULL DEFAULT 0,
            tries INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_outbox_pending ON outbox(synced, created_at);

        -- WB-112d：Server 团队时间线的 last-known-good 本地缓存。append-only 元数据，
        -- Server 不可达时仍能回读；不含会话正文、凭据或工作区文件。
        CREATE TABLE IF NOT EXISTS server_timeline_cache (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            actor_id TEXT NOT NULL DEFAULT '',
            actor_name TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL DEFAULT 'session',
            title TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            ext_id TEXT,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_server_timeline_cache_project
            ON server_timeline_cache(project_id, created_at DESC);

        -- WB-112e：增量镜像保留本地离线改动，发生本地/Server 分叉时显式留痕。
        CREATE TABLE IF NOT EXISTS server_sync_conflicts (
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            local_updated_at REAL NOT NULL DEFAULT 0,
            remote_updated_at REAL NOT NULL DEFAULT 0,
            local_data TEXT NOT NULL DEFAULT '{}',
            remote_data TEXT NOT NULL DEFAULT '{}',
            detected_at REAL NOT NULL,
            PRIMARY KEY (entity_type, entity_id)
        );
        CREATE INDEX IF NOT EXISTS idx_server_sync_conflicts_project
            ON server_sync_conflicts(project_id, detected_at DESC);

        -- 成员删除没有本地行可承载 dirty 标志，以 tombstone 保住离线删除意图。
        CREATE TABLE IF NOT EXISTS server_member_tombstones (
            project_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            local_deleted_at REAL NOT NULL,
            server_updated_at REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (project_id, user_id)
        );

        -- 本地 user（= Server account id）→ 其 Server token，供后台 outbox worker 以本人身份推送。
        CREATE TABLE IF NOT EXISTS server_identities (
            user_id TEXT PRIMARY KEY,
            server_token TEXT NOT NULL,
            updated_at REAL NOT NULL
        );

        -- 存量导入映射（WB-063）：本地资源 → 其在 Server 的 id，保证「重复导入不产生重复数据」。
        CREATE TABLE IF NOT EXISTS server_imports (
            local_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            server_id TEXT NOT NULL,
            server_account_id TEXT NOT NULL,
            created_at REAL NOT NULL
        );

        -- LOCAL_USER_ID ↔ Server 账号 的绑定（WB-063）：记住本机存量数据导入到了哪个 Server 账号。
        CREATE TABLE IF NOT EXISTS server_link (
            local_user_id TEXT PRIMARY KEY,
            server_account_id TEXT NOT NULL,
            server_account_name TEXT NOT NULL DEFAULT '',
            linked_at REAL NOT NULL
        );

        -- Server 目录下发镜像（WB-066）：客户端从 Server 拉的目录项，覆盖本地 showcase 分类；
        -- Server 空/离线 → 本地 builtin 种子作兜底（架构 §5「Server 下发 + 本地 override」）。
        CREATE TABLE IF NOT EXISTS catalog_downlink (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            data TEXT NOT NULL,
            sort INTEGER NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_catalog_downlink_cat ON catalog_downlink(category, sort);

        -- 外部渠道 ⇄ 会话映射（WB-072）：一个外部会话（如某个 Telegram chat）绑定到
        -- 一个长期 AgentMate 会话，续聊不断线。同时充当白名单：存在绑定 = 已授权。
        CREATE TABLE IF NOT EXISTS channel_sessions (
            channel TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            created_at REAL NOT NULL,
            PRIMARY KEY (channel, chat_id)
        );

        -- 渠道游标（WB-072）：长轮询已处理到的 update 偏移量，重启后从此续拉，
        -- 不重复驱动 agent（先进则 at-most-once：宁可漏也不重复执行副作用）。
        CREATE TABLE IF NOT EXISTS channel_state (
            channel TEXT PRIMARY KEY,
            update_offset INTEGER NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL
        );

        -- 助理设置（WB-077）：单助理的页面内配置。bot_token 存这里（用户显式决定；DB 已被
        -- .gitignore，永不提交、绝不回传前端），.env 作回退。enabled 为 NULL 时回退 env 开关。
        CREATE TABLE IF NOT EXISTS assistant_settings (
            owner_id TEXT PRIMARY KEY,
            bot_token TEXT,
            name TEXT,
            persona TEXT,
            model TEXT,
            enabled INTEGER,
            updated_at REAL NOT NULL
        );

        -- 自定义模型（WB-124）：按 owner 隔离的多厂商模型配置。api_key 只存后端、绝不回传前端
        -- （铁律#4，DB 已 .gitignore）。name = 用户可见显示名（per owner 唯一，作为 picker 选择键）；
        -- model_id/api_base/api_key 三者构成一次真实的 OpenAI 兼容调用（各厂商各自的凭据）。
        CREATE TABLE IF NOT EXISTS custom_models (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            name TEXT NOT NULL,
            model_id TEXT NOT NULL,
            api_base TEXT,
            api_key TEXT,
            icon TEXT NOT NULL DEFAULT '🧩',
            color TEXT NOT NULL DEFAULT '',
            mult TEXT NOT NULL DEFAULT '',
            sort INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_custom_models_owner_name ON custom_models(owner_id, name);

        -- 隐藏的内置模型（WB-124）：用户把用不到的内置项从 picker 隐藏。存在一行 = 隐藏。
        -- （WB-128 起旧「假内置」列表已移除、改厂商预置；此表保留仅为兼容存量，不再写新。）
        CREATE TABLE IF NOT EXISTS hidden_builtin_models (
            owner_id TEXT NOT NULL,
            name TEXT NOT NULL,
            PRIMARY KEY (owner_id, name)
        );

        -- 厂商 API Key（WB-128）：每个 owner 每个内置厂商一把 key。只存后端、绝不回前端（铁律#4）；
        -- 列表只暴露 has_key 布尔。厂商定义（base_url/模型名）在 storage/provider_seed.py，运行时读注册表。
        CREATE TABLE IF NOT EXISTS provider_keys (
            owner_id TEXT NOT NULL,
            provider_id TEXT NOT NULL,
            api_key TEXT NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (owner_id, provider_id)
        );

        -- 模型能力/成本元数据（WB-132）：为 Auto 模式铺路。model_ref = 选择键（@provider:model 或自定义名）。
        -- capabilities = JSON 标签列表(text/image/audio/video/tools/reasoning)；单价按每百万 token；按 owner 隔离。
        CREATE TABLE IF NOT EXISTS model_meta (
            owner_id TEXT NOT NULL,
            model_ref TEXT NOT NULL,
            capabilities TEXT NOT NULL DEFAULT '[]',
            input_cost REAL,
            input_cost_cached REAL,
            output_cost REAL,
            context_window INTEGER,
            currency TEXT,
            note TEXT,
            updated_at REAL NOT NULL,
            PRIMARY KEY (owner_id, model_ref)
        );

        -- 厂商 base_url/请求路径覆盖（WB-129）：预置只作起点，用户可改成自己的实际网关/代理。
        -- 有效值 = 覆盖 ∨ 预置默认；空串/无行 = 用预置默认。
        CREATE TABLE IF NOT EXISTS provider_config (
            owner_id TEXT NOT NULL,
            provider_id TEXT NOT NULL,
            base_url TEXT,
            chat_path TEXT,
            updated_at REAL NOT NULL,
            PRIMARY KEY (owner_id, provider_id)
        );

        -- 通用「按 owner 的偏好」KV（WB-136 起）：一格一条设置，value 存字符串。
        -- 目前用到的 key：default_model（未显式选模型时跟随的默认模型 ref，取代 .env LLM_MODEL）。
        CREATE TABLE IF NOT EXISTS user_settings (
            owner_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at REAL NOT NULL,
            PRIMARY KEY (owner_id, key)
        );

        -- 安全审计日志（WB-152）：真记录工具执行/拦截（run_command、网络访问等）。按 owner 隔离。
        -- action: 'executed'(已执行) / 'blocked'(被策略拦截)。
        CREATE TABLE IF NOT EXISTS audit_log (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            tool TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL DEFAULT 'executed',
            created_at REAL NOT NULL
        );

        -- 用户记忆（WB-148）：关于用户本人、长期有效的事实，注入之后对话的系统提示（真生效）。
        -- source: 'conversation'(对话自动抽取) / 'manual'(手动添加)。按 owner 隔离。
        CREATE TABLE IF NOT EXISTS user_memories (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            content TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            created_at REAL NOT NULL
        );

        -- 厂商模型覆盖（WB-128）：hidden=1 隐藏某预置模型；hidden=0 且非预置 = 用户新增的模型名
        -- （厂商上新时补进来）。预置模型的有效列表 = 注册表 − 隐藏 ∪ 新增。
        CREATE TABLE IF NOT EXISTS provider_models (
            owner_id TEXT NOT NULL,
            provider_id TEXT NOT NULL,
            model_id TEXT NOT NULL,
            hidden INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            PRIMARY KEY (owner_id, provider_id, model_id)
        );

        -- 多助理（WB-086/087）：每个助理一套独立能力配置 + 一条共享会话。
        -- mode: exec(执行,全工具) / plan(计划,只读+ask_user) / ask(问答,无工具)——权限映射（设计 §4）。
        -- workspace: default / project:<id> / dedicated（专属 workspace/assistants/<id>/）。
        CREATE TABLE IF NOT EXISTS assistants (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            name TEXT NOT NULL,
            avatar TEXT,
            instruction TEXT,
            model TEXT,
            mode TEXT NOT NULL DEFAULT 'exec',
            workspace TEXT NOT NULL DEFAULT 'default',
            experts TEXT NOT NULL DEFAULT '[]',
            skills TEXT NOT NULL DEFAULT '[]',
            connectors TEXT NOT NULL DEFAULT '[]',
            enabled INTEGER NOT NULL DEFAULT 1,
            session_id TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_assistants_owner ON assistants(owner_id, created_at);

        -- 渠道（WB-086/087）：属于某助理，类型相关 config（Telegram: bot_token 存这里，backend-only、
        -- write-only、绝不回传前端）。update_offset = 该 bot 各自的长轮询游标（多 bot 各自续拉）。
        CREATE TABLE IF NOT EXISTS channels (
            id TEXT PRIMARY KEY,
            assistant_id TEXT NOT NULL,
            type TEXT NOT NULL,
            config TEXT NOT NULL DEFAULT '{}',
            enabled INTEGER NOT NULL DEFAULT 1,
            update_offset INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_channels_assistant ON channels(assistant_id);

        -- 渠道 chat ⇄ 会话映射（WB-087，泛化自 channel_sessions）：按 channel_id 键，
        -- 因不同 bot 的私聊 chat_id 会相同（= 用户 id），必须按渠道区分。存在绑定 = 已授权。
        CREATE TABLE IF NOT EXISTS channel_chat_sessions (
            channel_id TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            created_at REAL NOT NULL,
            PRIMARY KEY (channel_id, chat_id)
        );
        """
    )
    conn.commit()
    _migrate_columns()
    _ensure_local_user()
    _seed_catalog()
    _seed_showcase()
    _migrate_expert_team_identities()
    # WB-183/184：这些旧橱窗数据已由 catalog_skills / Server 实时镜像接管。清运行库孤儿，
    # 防止旧版本种过的静态三元组与虚假 SkillHub 统计在升级后复活。
    conn.execute(
        "DELETE FROM catalog_showcase WHERE kind IN "
        "('SK_GRID','SK_CATS','SKILLHUB_GRID','SKILLHUB_FEATURED','SKILLHUB_CATS')"
    )
    conn.commit()
    _migrate_assistants()


def _migrate_columns() -> None:
    """幂等补列：老库缺少后加的列时 ALTER TABLE 补上（CREATE TABLE IF NOT EXISTS 不会改已存在的表）。"""
    conn = get_conn()
    # WB-026: work_items 增 description / due_date / attachments。
    # WB-108: 专业 PM 字段 priority / start_date / labels / parent_id / milestone_id（与 Server 对齐）。
    have = {r["name"] for r in conn.execute("PRAGMA table_info(work_items)").fetchall()}
    for col, ddl in (
        ("description", "description TEXT NOT NULL DEFAULT ''"),
        ("due_date", "due_date TEXT"),
        ("attachments", "attachments TEXT NOT NULL DEFAULT '[]'"),
        ("priority", "priority TEXT NOT NULL DEFAULT ''"),
        ("start_date", "start_date TEXT"),
        ("labels", "labels TEXT NOT NULL DEFAULT '[]'"),
        ("parent_id", "parent_id TEXT NOT NULL DEFAULT ''"),
        ("milestone_id", "milestone_id TEXT NOT NULL DEFAULT ''"),
        ("estimate_h", "estimate_h REAL NOT NULL DEFAULT 0"),   # WB-117 工时对齐
        ("spent_h", "spent_h REAL NOT NULL DEFAULT 0"),
        ("server_updated_at", "server_updated_at REAL NOT NULL DEFAULT 0"),
        ("server_dirty", "server_dirty INTEGER NOT NULL DEFAULT 0"),
    ):
        if col not in have:
            conn.execute(f"ALTER TABLE work_items ADD COLUMN {ddl}")

    # M7 C1: users 增 password_hash（真账户密码）。
    have_u = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "password_hash" not in have_u:
        conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")

    # WB-035: sessions 增 automation_id —— 把自动化产出的会话反向关联回其自动化，供「运行历史」。
    have_s = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if "automation_id" not in have_s:
        conn.execute("ALTER TABLE sessions ADD COLUMN automation_id TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_automation "
        "ON sessions(automation_id, created_at DESC)"
    )
    # 老库回填：此前未记 automation_id，用每条自动化已知的 last_session_id 把最近一次运行关联上，
    # 升级后「运行历史」至少能看到最近一次而非空列表。仅动 automation_id 尚为 NULL 的行，幂等。
    conn.execute(
        "UPDATE sessions SET automation_id = "
        "(SELECT a.id FROM automations a WHERE a.last_session_id = sessions.id) "
        "WHERE automation_id IS NULL "
        "AND EXISTS (SELECT 1 FROM automations a WHERE a.last_session_id = sessions.id)"
    )
    # WB-043: sessions 增逐次运行结果——run_status（running/ok/error）、run_summary（失败原因/摘要）、
    # run_kind（test/scheduled）。仅自动化运行的会话有值，其余 NULL。幂等补列。
    for col in ("run_status", "run_summary", "run_kind"):
        if col not in have_s:
            conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} TEXT")

    # WB-062 Phase 2: projects 增 origin（'local'|'server'）——标记从 Server 下行拉取的只读镜像项目。
    have_p = {r["name"] for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
    if "origin" not in have_p:
        conn.execute("ALTER TABLE projects ADD COLUMN origin TEXT NOT NULL DEFAULT 'local'")
    # WB-198：项目级知识库是本机执行配置，Server 镜像更新不覆盖该列。
    if "knowledge_ids" not in have_p:
        conn.execute("ALTER TABLE projects ADD COLUMN knowledge_ids TEXT NOT NULL DEFAULT '[]'")
    if "server_updated_at" not in have_p:
        conn.execute("ALTER TABLE projects ADD COLUMN server_updated_at REAL NOT NULL DEFAULT 0")
    if "server_dirty" not in have_p:
        conn.execute("ALTER TABLE projects ADD COLUMN server_dirty INTEGER NOT NULL DEFAULT 0")

    have_pm = {r["name"] for r in conn.execute("PRAGMA table_info(project_members)").fetchall()}
    for col, ddl in (
        ("updated_at", "updated_at REAL NOT NULL DEFAULT 0"),
        ("server_updated_at", "server_updated_at REAL NOT NULL DEFAULT 0"),
        ("server_dirty", "server_dirty INTEGER NOT NULL DEFAULT 0"),
    ):
        if col not in have_pm:
            conn.execute(f"ALTER TABLE project_members ADD COLUMN {ddl}")
    conn.execute("UPDATE project_members SET updated_at=created_at WHERE updated_at=0")

    have_ms = {r["name"] for r in conn.execute("PRAGMA table_info(milestones)").fetchall()}
    for col, ddl in (
        ("server_updated_at", "server_updated_at REAL NOT NULL DEFAULT 0"),
        ("server_dirty", "server_dirty INTEGER NOT NULL DEFAULT 0"),
    ):
        if col not in have_ms:
            conn.execute(f"ALTER TABLE milestones ADD COLUMN {ddl}")

    # WB-220：连接器推荐位引用稳定 slug；存量 builtin 用产品种子回填。
    have_cc = {r["name"] for r in conn.execute("PRAGMA table_info(catalog_connectors)").fetchall()}
    if "slug" not in have_cc:
        conn.execute("ALTER TABLE catalog_connectors ADD COLUMN slug TEXT NOT NULL DEFAULT ''")
    for connector in BUILTIN_CONNECTORS:
        conn.execute(
            "UPDATE catalog_connectors SET slug=? WHERE scope='builtin' AND name=? AND slug=''",
            (connector.get("slug", ""), connector["name"]),
        )

    # WB-206：旧库已种过 skill-creator-guide，_seed_catalog 按 slug 查重不会覆盖；只迁移仍为
    # 原始种子值的行，保留 Console/用户已运营过的自定义定义。
    old_creator_instruction = "当用户想创建自定义技能时，说明技能 = 提示词 + 工具包 的结构，并给出可落地的模板。"
    new_creator_instruction = (
        "帮助用户创建自定义技能：先澄清用途、触发场景、输入输出与约束，整理出稳定英文 slug、"
        "名称、描述和完整 Markdown 指令；信息足够后必须调用 create_local_skill 真正创建并安装，"
        "不要只给模板或假装已创建。"
    )
    conn.execute(
        "UPDATE catalog_skills SET description=?, instructions=?, tools=?, updated_at=? "
        "WHERE scope='builtin' AND slug='skill-creator-guide' AND instructions=?",
        ("通过对话梳理技能用途、触发场景与执行指令，并安装为本机技能。",
         new_creator_instruction, json.dumps(["create_local_skill"], ensure_ascii=False),
         time.time(), old_creator_instruction),
    )

    # WB-219：Server 自有技能可携带安全文本文件（references/脚本/模板），随目录下行并在安装时落盘。
    have_cs = {r["name"] for r in conn.execute("PRAGMA table_info(catalog_skills)").fetchall()}
    if "files" not in have_cs:
        conn.execute("ALTER TABLE catalog_skills ADD COLUMN files TEXT NOT NULL DEFAULT '[]'")
    if "version" not in have_cs:
        conn.execute("ALTER TABLE catalog_skills ADD COLUMN version TEXT NOT NULL DEFAULT ''")
    for col, ddl in (
        ("withdrawn", "withdrawn INTEGER NOT NULL DEFAULT 0"),
        ("compatible", "compatible INTEGER NOT NULL DEFAULT 1"),
        ("compatibility_error", "compatibility_error TEXT NOT NULL DEFAULT ''"),
        ("min_app_version", "min_app_version TEXT NOT NULL DEFAULT '0.0.0'"),
        ("permissions", "permissions TEXT NOT NULL DEFAULT '[]'"),
        ("tool_contract_version", "tool_contract_version TEXT NOT NULL DEFAULT '1'"),
        ("server_release_id", "server_release_id TEXT NOT NULL DEFAULT ''"),
        ("server_content_hash", "server_content_hash TEXT NOT NULL DEFAULT ''"),
    ):
        if col not in have_cs:
            conn.execute(f"ALTER TABLE catalog_skills ADD COLUMN {ddl}")

    # WB-134: model_meta 增缓存命中输入价 + 币种（定价分档 / ¥·$ 区分）。
    have_mm = {r["name"] for r in conn.execute("PRAGMA table_info(model_meta)").fetchall()}
    for col, ddl in (("input_cost_cached", "input_cost_cached REAL"), ("currency", "currency TEXT")):
        if col not in have_mm:
            conn.execute(f"ALTER TABLE model_meta ADD COLUMN {ddl}")

    # WB-166 认知记忆：user_memories 增强度/衰减/软状态字段（参考 AgentOS）。
    # importance 0..1 重要度、usage_count 命中次数（强化）、status active/superseded/archived（软状态，不硬删）、
    # superseded_by 更替留链、last_used_at 最近命中时间（衰减/强化基准）、embedding 本地嵌入向量 BLOB（档二 WB-167 填）。
    have_mem = {r["name"] for r in conn.execute("PRAGMA table_info(user_memories)").fetchall()}
    for col, ddl in (
        ("importance", "importance REAL NOT NULL DEFAULT 0.5"),
        ("usage_count", "usage_count INTEGER NOT NULL DEFAULT 0"),
        ("status", "status TEXT NOT NULL DEFAULT 'active'"),
        ("superseded_by", "superseded_by TEXT"),
        ("last_used_at", "last_used_at REAL"),
        ("embedding", "embedding BLOB"),
        # WB-170：产生该向量的嵌入模型标签（如 local:bge-small-zh-v1.5 / glm:embedding-3）。
        # 跨模型余弦无意义，检索/去重只比对同 tag；切后端后旧 tag 向量被重嵌入回填。
        ("embedding_model", "embedding_model TEXT"),
    ):
        if col not in have_mem:
            conn.execute(f"ALTER TABLE user_memories ADD COLUMN {ddl}")
    conn.commit()


def _ensure_local_user() -> None:
    conn = get_conn()
    row = conn.execute("SELECT id FROM users WHERE id=?", (LOCAL_USER_ID,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO users (id, name, role, plan) VALUES (?,?,?,?)",
            (LOCAL_USER_ID, LOCAL_USER_NAME, Role.OWNER.value, "体验版"),
        )
        conn.commit()


def _seed_catalog() -> None:
    """首次启动把内置专家人格 / 连接器注册表种进目录表（WB-059）。幂等：按 (scope='builtin', name)
    查重，缺失才插——已存在的（含用户改过的）不覆盖。种子源见 storage/catalog_seed.py。"""
    conn = get_conn()
    now = time.time()
    for i, e in enumerate(BUILTIN_EXPERTS):
        name = e["name"]
        exists = conn.execute(
            "SELECT 1 FROM catalog_experts WHERE scope='builtin' AND name=?", (name,)
        ).fetchone()
        if exists:
            # WB-231：早期 builtin 以中文展示名充当 slug；升级为与 Server 一致的稳定身份。
            conn.execute(
                "UPDATE catalog_experts SET slug=? WHERE scope='builtin' AND name=? AND slug<>?",
                (e["slug"], name, e["slug"]),
            )
            continue
        conn.execute(
            """INSERT INTO catalog_experts
               (id,scope,owner_id,slug,name,subtitle,avatar,intro,persona,tags,category,badge,source,
                functional,enabled,sort,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (new_uuid(), "builtin", None, e["slug"], name, "", "🧑", "", e["persona"],
             "[]", "", "", "内置", 1, 1, i, now, now),
        )
    for i, c in enumerate(BUILTIN_CONNECTORS):
        name = c["name"]
        exists = conn.execute(
            "SELECT 1 FROM catalog_connectors WHERE scope='builtin' AND name=?", (name,)
        ).fetchone()
        if exists:
            continue
        conn.execute(
            """INSERT INTO catalog_connectors
               (id,scope,owner_id,slug,name,icon,description,status,launch,enabled,sort,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (new_uuid(), "builtin", None, c.get("slug", ""), name, c.get("icon", ""), c.get("description", ""),
             c.get("status", "rdy"), json.dumps(c.get("launch", {}), ensure_ascii=False),
             1, i, now, now),
        )
    for i, s in enumerate(BUILTIN_SKILLS):  # WB-183
        slug = s["slug"]
        exists = conn.execute(
            "SELECT 1 FROM catalog_skills WHERE scope='builtin' AND slug=?", (slug,)
        ).fetchone()
        if exists:
            continue
        conn.execute(
            """INSERT INTO catalog_skills
               (id,scope,owner_id,slug,name,icon,description,instructions,tools,files,category,source,
                enabled,sort,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (new_uuid(), "builtin", None, slug, s["name"], s.get("icon", "🧩"),
             s.get("description", ""), s.get("instructions", ""),
             json.dumps(s.get("tools", []), ensure_ascii=False),
             json.dumps(s.get("files", []), ensure_ascii=False), s.get("category", ""),
             "内置", 1, i, now, now),
        )
    conn.commit()


def _seed_showcase() -> None:
    """首次启动把 catalog.ts 导出的橱窗商品卡种进 catalog_showcase（WB-060）。
    数组类导出 → 每元素一行（可按行上/下架、改 sort）；对象类导出（QUICK/CONN_META）→ 单行整存。
    幂等：按 kind 查重，某 kind 已有行则跳过（保留用户改动）。种子源 catalog_showcase.json。"""
    conn = get_conn()
    try:
        data = json.loads(_SHOWCASE_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return  # 种子文件缺失/损坏不阻断启动（前端橱窗有静态兜底）
    now = time.time()
    for kind, value in data.items():
        if conn.execute("SELECT 1 FROM catalog_showcase WHERE kind=? LIMIT 1", (kind,)).fetchone():
            continue
        if isinstance(value, list):
            rows = [(new_uuid(), kind, i, 1, json.dumps(el, ensure_ascii=False), 0, now, now)
                    for i, el in enumerate(value)]
        else:  # dict/scalar → 单行整存
            rows = [(new_uuid(), kind, 0, 1, json.dumps(value, ensure_ascii=False), 1, now, now)]
        conn.executemany(
            "INSERT INTO catalog_showcase (id,kind,sort,enabled,data,is_scalar,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            rows,
        )
    conn.commit()


# ---- users --------------------------------------------------------------

def get_user(user_id: str) -> Optional[User]:
    row = get_conn().execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        return None
    return User(id=row["id"], name=row["name"], role=Role(row["role"]), plan=row["plan"])


def _row_to_user(row) -> User:
    return User(id=row["id"], name=row["name"], role=Role(row["role"]), plan=row["plan"])


# ---- accounts / auth (M7 C1) --------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000)
    return f"pbkdf2$100000${salt}${dk.hex()}"


def verify_password(password: str, stored: Optional[str]) -> bool:
    if not stored:
        return False
    try:
        _algo, iters, salt, hexdk = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iters))
        return secrets.compare_digest(dk.hex(), hexdk)
    except Exception:
        return False


def get_user_by_name(name: str) -> Optional[tuple[User, Optional[str]]]:
    """Returns (user, password_hash) for login, or None."""
    row = get_conn().execute("SELECT * FROM users WHERE name=?", (name,)).fetchone()
    return (_row_to_user(row), row["password_hash"]) if row else None


def create_user(*, name: str, password: str, role: Role = Role.OWNER, plan: str = "体验版") -> User:
    uid = new_uuid()
    get_conn().execute(
        "INSERT INTO users (id,name,role,plan,password_hash) VALUES (?,?,?,?,?)",
        (uid, name[:60], role.value, plan, hash_password(password)),
    )
    get_conn().commit()
    return User(id=uid, name=name[:60], role=role, plan=plan)


def list_users() -> list[User]:
    rows = get_conn().execute("SELECT * FROM users ORDER BY name").fetchall()
    return [_row_to_user(r) for r in rows]


def create_token(user_id: str) -> str:
    token = secrets.token_hex(32)
    get_conn().execute(
        "INSERT INTO auth_tokens (token,user_id,created_at) VALUES (?,?,?)",
        (token, user_id, time.time()),
    )
    get_conn().commit()
    return token


def user_id_for_token(token: str) -> Optional[str]:
    row = get_conn().execute("SELECT user_id FROM auth_tokens WHERE token=?", (token,)).fetchone()
    return row["user_id"] if row else None


def delete_token(token: str) -> None:
    get_conn().execute("DELETE FROM auth_tokens WHERE token=?", (token,))
    get_conn().commit()


# ---- Server 账号镜像（WB-062）----------------------------------------------
# 本地 backend 把 Server 校验过的账号镜像进 users（无本地口令），让所有 owner-scoped 代码
# 无改动地认它；已校验的 Server token 缓存进 auth_tokens，后续请求走本地、不再打 Server。

def upsert_external_user(user_id: str, name: str, plan: str = "体验版") -> None:
    """把 Server 账号镜像进本地 users（幂等 upsert，无 password_hash）。id = Server account id。"""
    get_conn().execute(
        "INSERT INTO users (id,name,role,plan) VALUES (?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, plan=excluded.plan",
        (user_id, ((name or "").strip()[:60] or user_id[:8]), Role.OWNER.value, plan),
    )
    get_conn().commit()


def cache_token(token: str, user_id: str) -> None:
    """缓存已校验的 Server token → account 映射（后续请求本地命中，不再校验 Server）。"""
    get_conn().execute(
        "INSERT OR IGNORE INTO auth_tokens (token,user_id,created_at) VALUES (?,?,?)",
        (token, user_id, time.time()),
    )
    get_conn().commit()


def _json_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _record_server_conflict(
    entity_type: str, entity_id: str, project_id: str, reason: str,
    local_updated_at: float, remote_updated_at: float,
    local_data: dict, remote_data: dict, *, commit: bool = True,
) -> None:
    conn = get_conn()
    conn.execute(
        """INSERT INTO server_sync_conflicts
           (entity_type,entity_id,project_id,reason,local_updated_at,remote_updated_at,local_data,remote_data,detected_at)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(entity_type,entity_id) DO UPDATE SET
             project_id=excluded.project_id,reason=excluded.reason,
             local_updated_at=excluded.local_updated_at,remote_updated_at=excluded.remote_updated_at,
             local_data=excluded.local_data,remote_data=excluded.remote_data,detected_at=excluded.detected_at""",
        (entity_type, entity_id, project_id, reason, float(local_updated_at or 0),
         float(remote_updated_at or 0), json.dumps(local_data, ensure_ascii=False, sort_keys=True),
         json.dumps(remote_data, ensure_ascii=False, sort_keys=True), time.time()),
    )
    if commit:
        conn.commit()


def _clear_server_conflict(entity_type: str, entity_id: str, *, commit: bool = True) -> None:
    conn = get_conn()
    conn.execute(
        "DELETE FROM server_sync_conflicts WHERE entity_type=? AND entity_id=?",
        (entity_type, entity_id),
    )
    if commit:
        conn.commit()


def list_server_sync_conflicts(project_id: str) -> list[dict]:
    rows = get_conn().execute(
        """SELECT entity_type,entity_id,project_id,reason,local_updated_at,remote_updated_at,
                  local_data,remote_data,detected_at
           FROM server_sync_conflicts WHERE project_id=? ORDER BY detected_at DESC""",
        (project_id,),
    ).fetchall()
    out: list[dict] = []
    for row in rows:
        item = dict(row)
        for key in ("local_data", "remote_data"):
            try:
                item[key] = json.loads(item[key] or "{}")
            except (json.JSONDecodeError, TypeError):
                item[key] = {}
        out.append(item)
    return out


def count_server_sync_conflicts(project_id: str) -> int:
    return int(get_conn().execute(
        "SELECT COUNT(*) FROM server_sync_conflicts WHERE project_id=?", (project_id,)
    ).fetchone()[0])


def mirror_server_timeline(project_id: str, events: list[dict]) -> None:
    """增量缓存 Server append-only 时间线；不删除旧事件，供离线 last-known-good 回读。"""
    conn = get_conn()
    for event in events:
        event_id = str(event.get("id") or "")
        if not event_id:
            continue
        conn.execute(
            """INSERT INTO server_timeline_cache
               (id,project_id,actor_id,actor_name,kind,title,summary,ext_id,created_at)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET actor_id=excluded.actor_id,actor_name=excluded.actor_name,
                 kind=excluded.kind,title=excluded.title,summary=excluded.summary,
                 ext_id=excluded.ext_id,created_at=excluded.created_at""",
            (event_id, project_id, str(event.get("actor_id") or ""),
             str(event.get("actor_name") or "")[:60], str(event.get("kind") or "session")[:40],
             str(event.get("title") or "")[:200], str(event.get("summary") or "")[:2000],
             event.get("ext_id"), float(event.get("created_at") or time.time())),
        )
    conn.commit()


def list_server_timeline(project_id: str, limit: int = 100) -> list[dict]:
    rows = get_conn().execute(
        """SELECT id,project_id,actor_id,actor_name,kind,title,summary,ext_id,created_at
           FROM server_timeline_cache WHERE project_id=? ORDER BY created_at DESC LIMIT ?""",
        (project_id, max(1, min(int(limit), 500))),
    ).fetchall()
    return [dict(row) for row in rows]


def mirror_server_project(
    *, id: str, name: str, owner_id: str, instruction: str = "",
    connectors: Optional[list] = None, experts: Optional[list] = None, skills: Optional[list] = None,
    created_at: Optional[float] = None, updated_at: Optional[float] = None,
) -> None:
    """按 ``id + updated_at`` 合并 Server 项目元数据。

    Server 更新且本地未改时应用远端；本地离线改动存在时保留本地值并登记冲突，避免 pull
    静默覆盖。``knowledge_ids`` 是本机字段，不参与比较或覆盖。
    """
    conn = get_conn()
    remote_ts = float(updated_at or time.time())
    remote = {
        "name": name[:120], "owner_id": owner_id, "instruction": instruction,
        "connectors": list(connectors or []), "experts": list(experts or []),
        "skills": list(skills or []),
    }
    row = conn.execute("SELECT * FROM projects WHERE id=?", (id,)).fetchone()
    if row is None:
        conn.execute(
            """INSERT INTO projects
               (id,name,owner_id,instruction,connectors,experts,skills,created_at,updated_at,origin,server_updated_at,server_dirty)
               VALUES (?,?,?,?,?,?,?,?,?,'server',?,0)""",
            (id, remote["name"], owner_id, instruction,
             json.dumps(remote["connectors"], ensure_ascii=False),
             json.dumps(remote["experts"], ensure_ascii=False),
             json.dumps(remote["skills"], ensure_ascii=False),
             float(created_at or remote_ts), remote_ts, remote_ts),
        )
        _clear_server_conflict("project", id, commit=False)
        conn.commit()
        return
    local = {
        "name": row["name"], "owner_id": row["owner_id"], "instruction": row["instruction"],
        "connectors": _json_list(row["connectors"]), "experts": _json_list(row["experts"]),
        "skills": _json_list(row["skills"]),
    }
    if row["origin"] != "server":
        _record_server_conflict("project", id, id, "id_collision", row["updated_at"], remote_ts, local, remote, commit=False)
        conn.commit()
        return
    baseline = float(row["server_updated_at"] or 0)
    dirty = bool(row["server_dirty"])
    if baseline == 0 and local != remote and float(row["updated_at"] or 0) > remote_ts:
        dirty = True  # 老版本没有 dirty 标志时，以 updated_at 保护可能的离线改动。
    if dirty and local != remote:
        reason = "concurrent_update" if remote_ts > baseline else "local_ahead"
        # owner_id 是权限边界，始终服从 Server；其余协作字段保留本地待人工处理。
        conn.execute(
            "UPDATE projects SET owner_id=?,server_updated_at=?,server_dirty=1 WHERE id=?",
            (owner_id, remote_ts, id),
        )
        _record_server_conflict("project", id, id, reason, row["updated_at"], remote_ts, local, remote, commit=False)
    else:
        conn.execute(
            """UPDATE projects SET name=?,owner_id=?,instruction=?,connectors=?,experts=?,skills=?,
               updated_at=?,origin='server',server_updated_at=?,server_dirty=0 WHERE id=?""",
            (remote["name"], owner_id, instruction,
             json.dumps(remote["connectors"], ensure_ascii=False),
             json.dumps(remote["experts"], ensure_ascii=False),
             json.dumps(remote["skills"], ensure_ascii=False), remote_ts, remote_ts, id),
        )
        _clear_server_conflict("project", id, commit=False)
    conn.commit()


def replace_server_project_members(
    project_id: str, members: list[dict], *, acknowledge_ids: Optional[set[str]] = None,
) -> None:
    """按成员 ``account_id + updated_at`` 增量合并，不再整表删插。

    本地离线角色改动/删除通过 dirty 或 tombstone 保留，并写入可查询冲突台账。
    """
    conn = get_conn()
    remote_ids: set[str] = set()
    for m in members:
        aid = str(m.get("account_id") or "")
        if not aid:
            continue
        remote_ids.add(aid)
        upsert_external_user(aid, m.get("name", ""))  # 成员/owner 账号镜像进 users
        if m.get("is_owner"):
            _clear_server_conflict("project_member", f"{project_id}:{aid}", commit=False)
            continue  # owner 由 projects.owner_id 记，不入 project_members
        try:
            role = Role(m.get("role", "Member"))
        except ValueError:
            role = Role.MEMBER
        remote_ts = float(m.get("updated_at") or m.get("created_at") or time.time())
        entity_id = f"{project_id}:{aid}"
        local = conn.execute(
            "SELECT * FROM project_members WHERE project_id=? AND user_id=?", (project_id, aid)
        ).fetchone()
        tombstone = conn.execute(
            "SELECT * FROM server_member_tombstones WHERE project_id=? AND user_id=?", (project_id, aid)
        ).fetchone()
        remote = {"role": role.value, "name": str(m.get("name") or "")}
        if local is None and tombstone is not None:
            _record_server_conflict(
                "project_member", entity_id, project_id, "local_deleted",
                tombstone["local_deleted_at"], remote_ts, {"deleted": True}, remote, commit=False,
            )
            conn.execute(
                "UPDATE server_member_tombstones SET server_updated_at=? WHERE project_id=? AND user_id=?",
                (remote_ts, project_id, aid),
            )
            continue
        if local is None:
            conn.execute(
                """INSERT INTO project_members
                   (project_id,user_id,role,created_at,updated_at,server_updated_at,server_dirty)
                   VALUES (?,?,?,?,?,?,0)""",
                (project_id, aid, role.value, float(m.get("created_at") or remote_ts), remote_ts, remote_ts),
            )
            _clear_server_conflict("project_member", entity_id, commit=False)
            continue
        local_payload = {"role": local["role"], "name": remote["name"]}
        baseline = float(local["server_updated_at"] or 0)
        dirty = bool(local["server_dirty"])
        if baseline == 0 and local_payload != remote and float(local["updated_at"] or 0) > remote_ts:
            dirty = True
        if dirty and local_payload != remote:
            # 角色是权限边界：Server 恢复后必须以权威角色为准；本地意图完整留在冲突台账。
            conn.execute(
                """UPDATE project_members SET role=?,updated_at=?,server_updated_at=?,server_dirty=0
                   WHERE project_id=? AND user_id=?""",
                (role.value, remote_ts, remote_ts, project_id, aid),
            )
            _record_server_conflict(
                "project_member", entity_id, project_id, "permission_conflict",
                local["updated_at"], remote_ts, local_payload, remote, commit=False,
            )
        else:
            conn.execute(
                """UPDATE project_members SET role=?,updated_at=?,server_updated_at=?,server_dirty=0
                   WHERE project_id=? AND user_id=?""",
                (role.value, remote_ts, remote_ts, project_id, aid),
            )
            conn.execute("DELETE FROM server_member_tombstones WHERE project_id=? AND user_id=?", (project_id, aid))
            existing_conflict = conn.execute(
                "SELECT reason FROM server_sync_conflicts WHERE entity_type='project_member' AND entity_id=?",
                (entity_id,),
            ).fetchone()
            if aid in (acknowledge_ids or set()) or not existing_conflict or existing_conflict["reason"] != "permission_conflict":
                _clear_server_conflict("project_member", entity_id, commit=False)

    # 完整 Server 快照中消失的行：干净镜像删除；本地新增/修改保留并显式报冲突。
    rows = conn.execute("SELECT * FROM project_members WHERE project_id=?", (project_id,)).fetchall()
    for local in rows:
        aid = local["user_id"]
        if aid in remote_ids:
            continue
        entity_id = f"{project_id}:{aid}"
        if bool(local["server_dirty"]) or not float(local["server_updated_at"] or 0):
            _record_server_conflict(
                "project_member", entity_id, project_id, "permission_conflict",
                local["updated_at"], 0, {"role": local["role"]}, {"deleted": True}, commit=False,
            )
        conn.execute("DELETE FROM project_members WHERE project_id=? AND user_id=?", (project_id, aid))
        if not bool(local["server_dirty"]) and float(local["server_updated_at"] or 0):
            _clear_server_conflict("project_member", entity_id, commit=False)
    tombstones = conn.execute("SELECT user_id FROM server_member_tombstones WHERE project_id=?", (project_id,)).fetchall()
    for tombstone in tombstones:
        if tombstone["user_id"] not in remote_ids:
            entity_id = f"{project_id}:{tombstone['user_id']}"
            conn.execute("DELETE FROM server_member_tombstones WHERE project_id=? AND user_id=?", (project_id, tombstone["user_id"]))
            _clear_server_conflict("project_member", entity_id, commit=False)
    conn.commit()


def reconcile_server_project_access(account_id: str, remote_project_ids: set[str]) -> None:
    """撤销 Server 已不再授予的项目访问；权限收敛不受本地 dirty/冲突保护影响。"""
    conn = get_conn()
    for project, _role in list_projects_for(account_id):
        if project.origin != "server" or project.id in remote_project_ids:
            continue
        if project.owner_id == account_id:
            # 有效 token 下 owner 项目消失意味着远端项目已删除；移除本地控制面入口，
            # 会话/工作区仍留本机但因项目门禁不可访问，避免误删执行数据。
            conn.execute("DELETE FROM project_members WHERE project_id=?", (project.id,))
            conn.execute("DELETE FROM projects WHERE id=?", (project.id,))
        else:
            conn.execute(
                "DELETE FROM project_members WHERE project_id=? AND user_id=?",
                (project.id, account_id),
            )
        conn.execute(
            "DELETE FROM server_member_tombstones WHERE project_id=? AND user_id=?",
            (project.id, account_id),
        )
    conn.commit()


# ---- Server 上行 outbox + 身份（WB-062 Phase 3）----------------------------

def set_server_identity(user_id: str, server_token: str) -> None:
    """记住某账号的 Server token，供后台 outbox worker 以本人身份推送。幂等 upsert。"""
    get_conn().execute(
        "INSERT INTO server_identities (user_id,server_token,updated_at) VALUES (?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET server_token=excluded.server_token, updated_at=excluded.updated_at",
        (user_id, server_token, time.time()),
    )
    get_conn().commit()


def get_server_identity(user_id: str) -> Optional[str]:
    r = get_conn().execute("SELECT server_token FROM server_identities WHERE user_id=?", (user_id,)).fetchone()
    return r["server_token"] if r else None


def enqueue_outbox(*, kind: str, actor_id: str, project_id: str, payload: dict) -> None:
    get_conn().execute(
        "INSERT INTO outbox (id,kind,actor_id,project_id,payload,synced,tries,created_at) "
        "VALUES (?,?,?,?,?,0,0,?)",
        (new_uuid(), kind, actor_id, project_id, json.dumps(payload, ensure_ascii=False), time.time()),
    )
    get_conn().commit()


def list_pending_outbox(limit: int = 50) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM outbox WHERE synced=0 ORDER BY created_at ASC LIMIT ?", (limit,)
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        try:
            d["payload"] = json.loads(r["payload"])
        except (json.JSONDecodeError, TypeError):
            d["payload"] = {}
        out.append(d)
    return out


def mark_outbox_synced(outbox_id: str) -> None:
    get_conn().execute("UPDATE outbox SET synced=1 WHERE id=?", (outbox_id,))
    get_conn().commit()


def bump_outbox_tries(outbox_id: str) -> None:
    get_conn().execute("UPDATE outbox SET tries=tries+1 WHERE id=?", (outbox_id,))
    get_conn().commit()


# ---- 存量导入 + LOCAL↔Server 绑定（WB-063）--------------------------------

def record_import(local_id: str, kind: str, server_id: str, server_account_id: str) -> None:
    get_conn().execute(
        "INSERT OR REPLACE INTO server_imports (local_id,kind,server_id,server_account_id,created_at) "
        "VALUES (?,?,?,?,?)",
        (local_id, kind, server_id, server_account_id, time.time()),
    )
    get_conn().commit()


def get_import(local_id: str) -> Optional[dict]:
    r = get_conn().execute("SELECT * FROM server_imports WHERE local_id=?", (local_id,)).fetchone()
    return dict(r) if r else None


def set_server_link(local_user_id: str, server_account_id: str, server_account_name: str = "") -> None:
    get_conn().execute(
        "INSERT INTO server_link (local_user_id,server_account_id,server_account_name,linked_at) VALUES (?,?,?,?) "
        "ON CONFLICT(local_user_id) DO UPDATE SET server_account_id=excluded.server_account_id, "
        "server_account_name=excluded.server_account_name, linked_at=excluded.linked_at",
        (local_user_id, server_account_id, server_account_name, time.time()),
    )
    get_conn().commit()


def get_server_link(local_user_id: str) -> Optional[dict]:
    r = get_conn().execute("SELECT * FROM server_link WHERE local_user_id=?", (local_user_id,)).fetchone()
    return dict(r) if r else None


# ---- sessions -----------------------------------------------------------

def create_session(
    *,
    owner_id: str,
    title: str,
    kind: str = "chat",
    space: Optional[str] = None,
    project_id: Optional[str] = None,
    automation_id: Optional[str] = None,
    run_kind: Optional[str] = None,
    run_status: Optional[str] = None,
) -> Session:
    # automation_id links a run back to the automation that produced it (WB-035);
    # None for ordinary chat/project sessions. run_kind/run_status hold the per-run
    # outcome for automation runs (WB-043) — the scheduler sets them.
    now = time.time()
    s = Session(
        id=new_uuid(),
        title=title[:120],
        owner_id=owner_id,
        project_id=project_id,
        space=space,
        kind=kind,
        status="idle",
        created_at=now,
        updated_at=now,
        run_status=run_status,
        run_kind=run_kind,
    )
    get_conn().execute(
        """INSERT INTO sessions (id,title,owner_id,project_id,space,kind,status,created_at,updated_at,automation_id,run_status,run_kind)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (s.id, s.title, s.owner_id, s.project_id, s.space, s.kind, s.status, s.created_at, s.updated_at, automation_id, run_status, run_kind),
    )
    get_conn().commit()
    return s


def get_session(session_id: str, owner_id: Optional[str] = None) -> Optional[Session]:
    # owner_id, when given, scopes the lookup so a caller can't read another
    # user's session by guessing its id (WB-013).
    if owner_id is not None:
        row = get_conn().execute(
            "SELECT * FROM sessions WHERE id=? AND owner_id=?", (session_id, owner_id)
        ).fetchone()
    else:
        row = get_conn().execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not row:
        return None
    return _row_to_session(row)


def get_assistant_session(owner_id: str) -> Optional[Session]:
    """某 owner 的助理会话（外部渠道共用的单一长期会话，kind=assistant）。WB-072 Slice 2：
    App 助理页与 Telegram 桥接共享它——每个 owner 至多一个，取最早那条。"""
    row = get_conn().execute(
        "SELECT * FROM sessions WHERE owner_id=? AND kind='assistant' ORDER BY created_at ASC LIMIT 1",
        (owner_id,),
    ).fetchone()
    return _row_to_session(row) if row else None


def get_session_for(session_id: str, user_id: str) -> Optional[Session]:
    """Session if the caller owns it, OR it belongs to a project the caller is a
    member of — read-only shared visibility (M7 C3). Personal (non-project)
    sessions of other users stay private."""
    s = get_session(session_id)
    if not s:
        return None
    if s.owner_id == user_id:
        return s
    if s.project_id and project_access_role(s.project_id, user_id) is not None:
        return s
    return None


def list_sessions(owner_id: str, space: Optional[str] = None) -> list[Session]:
    if space:
        rows = get_conn().execute(
            "SELECT * FROM sessions WHERE owner_id=? AND space=? ORDER BY updated_at DESC",
            (owner_id, space),
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT * FROM sessions WHERE owner_id=? ORDER BY updated_at DESC",
            (owner_id,),
        ).fetchall()
    return [_row_to_session(r) for r in rows]


def list_automation_runs(automation_id: str, owner_id: str) -> list[Session]:
    """All sessions produced by one automation, newest first (WB-035). owner-scoped."""
    rows = get_conn().execute(
        "SELECT * FROM sessions WHERE automation_id=? AND owner_id=? ORDER BY created_at DESC",
        (automation_id, owner_id),
    ).fetchall()
    return [_row_to_session(r) for r in rows]


def touch_session(session_id: str, status: Optional[str] = None) -> None:
    if status is not None:
        get_conn().execute(
            "UPDATE sessions SET updated_at=?, status=? WHERE id=?",
            (time.time(), status, session_id),
        )
    else:
        get_conn().execute(
            "UPDATE sessions SET updated_at=? WHERE id=?", (time.time(), session_id)
        )
    get_conn().commit()


def rename_session(session_id: str, title: str) -> None:
    get_conn().execute(
        "UPDATE sessions SET title=?, updated_at=? WHERE id=?",
        (title[:120], time.time(), session_id),
    )
    get_conn().commit()


def delete_session(session_id: str) -> None:
    get_conn().execute("DELETE FROM sessions WHERE id=?", (session_id,))
    get_conn().commit()


def clear_conversations(owner_id: str) -> int:
    """清空 owner 的个人对话（kind='chat'）及其消息（WB-149）。返回删除的会话数。
    只删个人对话，不动项目执行/助理/自动化会话，避免误伤其它子系统的引用。
    消息经 messages 表的 ON DELETE CASCADE（+PRAGMA foreign_keys=ON）自动删除——
    不手动展开 id 列表删消息，既免 SQLite 变量数上限（会话很多时），也更快。"""
    conn = get_conn()
    cur = conn.execute("DELETE FROM sessions WHERE owner_id=? AND kind='chat'", (owner_id,))
    conn.commit()
    return cur.rowcount


def _row_to_session(row: sqlite3.Row) -> Session:
    return Session(
        id=row["id"],
        title=row["title"],
        owner_id=row["owner_id"],
        project_id=row["project_id"],
        space=row["space"],
        kind=row["kind"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        run_status=row["run_status"],
        run_summary=row["run_summary"],
        run_kind=row["run_kind"],
    )


def mark_session_run(session_id: str, *, run_status: str, run_summary: Optional[str] = None) -> None:
    """Record an automation run's outcome on its session (WB-043)."""
    get_conn().execute(
        "UPDATE sessions SET run_status=?, run_summary=?, updated_at=? WHERE id=?",
        (run_status, run_summary, time.time(), session_id),
    )
    get_conn().commit()


def list_all_automation_runs(owner_id: str, limit: int = 100) -> list[Session]:
    """Every automation run this owner produced, newest first (WB-043) — the cross-
    automation 运行记录 feed. Owner-scoped, capped."""
    rows = get_conn().execute(
        "SELECT * FROM sessions WHERE kind='automation' AND owner_id=? ORDER BY created_at DESC LIMIT ?",
        (owner_id, limit),
    ).fetchall()
    return [_row_to_session(r) for r in rows]


# ---- runs / artifacts (WB-242) -----------------------------------------

RUN_STATUSES = {
    "draft", "planning", "waiting_approval", "running", "paused",
    "failed", "completed", "accepted", "cancelled",
}
_RUN_TRANSITIONS = {
    "draft": {"planning", "running", "cancelled"},
    "planning": {"waiting_approval", "running", "failed", "completed", "cancelled"},
    "waiting_approval": {"running", "failed", "cancelled"},
    "running": {"waiting_approval", "paused", "failed", "completed", "cancelled"},
    "paused": {"running", "failed", "cancelled"},
    "failed": set(),
    "completed": {"accepted"},
    "accepted": set(),
    "cancelled": set(),
}


def _load_json(raw: Any, fallback: Any) -> Any:
    try:
        return json.loads(raw) if raw else fallback
    except (json.JSONDecodeError, TypeError):
        return fallback


def _row_to_run(row: sqlite3.Row) -> Run:
    return Run(
        id=row["id"], session_id=row["session_id"], owner_id=row["owner_id"],
        project_id=row["project_id"], work_item_id=row["work_item_id"], mode=row["mode"],
        status=row["status"], workspace=row["workspace"],
        idempotency_key=row["idempotency_key"], retry_of=row["retry_of"],
        plan=_load_json(row["plan"], []),
        permission_snapshot=_load_json(row["permission_snapshot"], {}),
        checkpoint=_load_json(row["checkpoint"], {}), error_code=row["error_code"],
        error_message=row["error_message"], prompt_tokens=int(row["prompt_tokens"] or 0),
        completion_tokens=int(row["completion_tokens"] or 0), tool_calls=int(row["tool_calls"] or 0),
        started_at=row["started_at"], ended_at=row["ended_at"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _row_to_artifact(row: sqlite3.Row) -> Artifact:
    return Artifact(
        id=row["id"], run_id=row["run_id"], owner_id=row["owner_id"],
        project_id=row["project_id"], kind=row["kind"], path=row["path"], name=row["name"],
        mime_type=row["mime_type"], source_tool=row["source_tool"], size=int(row["size"] or 0),
        sha256=row["sha256"], validation_status=row["validation_status"],
        validation=_load_json(row["validation"], {}), preview_path=row["preview_path"],
        acceptance_status=row["acceptance_status"], accepted_by=row["accepted_by"],
        accepted_at=row["accepted_at"], created_at=row["created_at"], updated_at=row["updated_at"],
    )


def create_run(
    *, session_id: str, owner_id: str, project_id: Optional[str], mode: str,
    workspace: str = "default", work_item_id: Optional[str] = None,
    idempotency_key: Optional[str] = None, retry_of: Optional[str] = None,
    status: Optional[str] = None, permission_snapshot: Optional[dict[str, Any]] = None,
) -> tuple[Run, bool]:
    """Create one execution atomically; duplicate owner/idempotency keys reuse it."""
    session = get_session(session_id)
    if not session or session.owner_id != owner_id or session.project_id != project_id:
        raise ValueError("run session scope mismatch")
    if work_item_id:
        item = get_work_item(work_item_id)
        if not item or item.project_id != project_id:
            raise ValueError("run work item scope mismatch")
    if retry_of:
        original = get_run(retry_of)
        if (
            not original or original.owner_id != owner_id or original.session_id != session_id
            or original.status not in {"failed", "cancelled", "paused"}
        ):
            raise ValueError("invalid retry source")
    key = (idempotency_key or "").strip()[:200] or None
    if key:
        existing = get_conn().execute(
            "SELECT * FROM runs WHERE owner_id=? AND idempotency_key=?", (owner_id, key)
        ).fetchone()
        if existing:
            return _row_to_run(existing), False
    initial = status or ("planning" if mode == "plan" else "running")
    if initial not in RUN_STATUSES:
        raise ValueError(f"invalid run status: {initial}")
    now = time.time()
    rid = new_uuid()
    try:
        get_conn().execute(
            """INSERT INTO runs
               (id,session_id,owner_id,project_id,work_item_id,mode,status,workspace,
                idempotency_key,retry_of,plan,permission_snapshot,checkpoint,started_at,
                created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (rid, session_id, owner_id, project_id, work_item_id, mode, initial, workspace,
             key, retry_of, "[]", json.dumps(permission_snapshot or {}, ensure_ascii=False),
             "{}", now if initial in {"planning", "running"} else None, now, now),
        )
        get_conn().commit()
    except sqlite3.IntegrityError:
        if key:
            row = get_conn().execute(
                "SELECT * FROM runs WHERE owner_id=? AND idempotency_key=?", (owner_id, key)
            ).fetchone()
            if row:
                return _row_to_run(row), False
        raise
    return get_run(rid), True  # type: ignore[return-value]


def get_run(run_id: str) -> Optional[Run]:
    row = get_conn().execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    return _row_to_run(row) if row else None


def get_run_by_idempotency(owner_id: str, idempotency_key: str) -> Optional[Run]:
    row = get_conn().execute(
        "SELECT * FROM runs WHERE owner_id=? AND idempotency_key=?",
        (owner_id, idempotency_key.strip()[:200]),
    ).fetchone()
    return _row_to_run(row) if row else None


def get_run_for(run_id: str, user_id: str) -> Optional[Run]:
    run = get_run(run_id)
    if not run:
        return None
    if run.owner_id == user_id:
        return run
    if run.project_id and project_access_role(run.project_id, user_id) is not None:
        return run
    return None


def list_runs(
    user_id: str, *, session_id: Optional[str] = None, project_id: Optional[str] = None,
    work_item_id: Optional[str] = None, limit: int = 100,
) -> list[Run]:
    clauses = ["(owner_id=? OR (project_id IS NOT NULL AND project_id IN "
               "(SELECT project_id FROM project_members WHERE user_id=?)) OR project_id IN "
               "(SELECT id FROM projects WHERE owner_id=?))"]
    values: list[Any] = [user_id, user_id, user_id]
    for column, value in (("session_id", session_id), ("project_id", project_id), ("work_item_id", work_item_id)):
        if value:
            clauses.append(f"{column}=?")
            values.append(value)
    values.append(max(1, min(int(limit), 500)))
    rows = get_conn().execute(
        f"SELECT * FROM runs WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?", values
    ).fetchall()
    return [_row_to_run(row) for row in rows]


def set_run_status(
    run_id: str, status: str, *, error_code: Optional[str] = None,
    error_message: Optional[str] = None, checkpoint: Optional[dict[str, Any]] = None,
) -> Run:
    run = get_run(run_id)
    if not run:
        raise KeyError(run_id)
    if status not in RUN_STATUSES:
        raise ValueError(f"invalid run status: {status}")
    if status != run.status and status not in _RUN_TRANSITIONS[run.status]:
        raise ValueError(f"invalid run transition: {run.status} -> {status}")
    now = time.time()
    ended = now if status in {"failed", "completed", "accepted", "cancelled"} else None
    get_conn().execute(
        """UPDATE runs SET status=?, error_code=?, error_message=?, checkpoint=?,
           ended_at=COALESCE(?,ended_at), updated_at=? WHERE id=?""",
        (status, error_code, error_message,
         json.dumps(checkpoint if checkpoint is not None else run.checkpoint, ensure_ascii=False),
         ended, now, run_id),
    )
    get_conn().commit()
    return get_run(run_id)  # type: ignore[return-value]


def update_run_runtime(
    run_id: str, *, permission_snapshot: Optional[dict[str, Any]] = None,
    plan: Optional[list[dict[str, Any]]] = None, prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None, tool_calls: Optional[int] = None,
) -> Run:
    run = get_run(run_id)
    if not run:
        raise KeyError(run_id)
    get_conn().execute(
        """UPDATE runs SET permission_snapshot=?, plan=?, prompt_tokens=?, completion_tokens=?,
           tool_calls=?, updated_at=? WHERE id=?""",
        (json.dumps(permission_snapshot if permission_snapshot is not None else run.permission_snapshot, ensure_ascii=False),
         json.dumps(plan if plan is not None else run.plan, ensure_ascii=False),
         run.prompt_tokens if prompt_tokens is None else max(0, int(prompt_tokens)),
         run.completion_tokens if completion_tokens is None else max(0, int(completion_tokens)),
         run.tool_calls if tool_calls is None else max(0, int(tool_calls)), time.time(), run_id),
    )
    get_conn().commit()
    return get_run(run_id)  # type: ignore[return-value]


def create_retry_run(run_id: str, owner_id: str, idempotency_key: Optional[str] = None) -> tuple[Run, bool]:
    original = get_run(run_id)
    if not original or original.owner_id != owner_id:
        raise KeyError(run_id)
    if original.status not in {"failed", "cancelled", "paused"}:
        raise ValueError("only failed, cancelled or paused runs can be retried")
    return create_run(
        session_id=original.session_id, owner_id=original.owner_id, project_id=original.project_id,
        work_item_id=original.work_item_id, mode=original.mode, workspace=original.workspace,
        idempotency_key=idempotency_key, retry_of=original.id, status="paused",
        permission_snapshot=original.permission_snapshot,
    )


def upsert_artifact(
    *, run_id: str, path: str, full_path: Path, source_tool: str,
    kind: str = "file", validation: Optional[dict[str, Any]] = None,
    preview_path: Optional[str] = None,
) -> Artifact:
    run = get_run(run_id)
    if not run:
        raise KeyError(run_id)
    if not full_path.is_file():
        raise FileNotFoundError(full_path)
    digest = hashlib.sha256()
    with full_path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    now = time.time()
    aid = new_uuid()
    mime = mimetypes.guess_type(full_path.name)[0] or "application/octet-stream"
    check = validation or {"exists": True, "sha256": True}
    get_conn().execute(
        """INSERT INTO artifacts
           (id,run_id,owner_id,project_id,kind,path,name,mime_type,source_tool,size,sha256,
            validation_status,validation,preview_path,acceptance_status,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(run_id,path) DO UPDATE SET
             kind=excluded.kind,name=excluded.name,mime_type=excluded.mime_type,
             source_tool=excluded.source_tool,size=excluded.size,sha256=excluded.sha256,
             validation_status=excluded.validation_status,validation=excluded.validation,
             preview_path=excluded.preview_path,acceptance_status='pending',accepted_by=NULL,
             accepted_at=NULL,updated_at=excluded.updated_at""",
        (aid, run_id, run.owner_id, run.project_id, kind, path, full_path.name, mime,
         source_tool, full_path.stat().st_size, digest.hexdigest(), "passed",
         json.dumps(check, ensure_ascii=False), preview_path, "pending", now, now),
    )
    get_conn().commit()
    row = get_conn().execute("SELECT * FROM artifacts WHERE run_id=? AND path=?", (run_id, path)).fetchone()
    return _row_to_artifact(row)


def get_artifact(artifact_id: str) -> Optional[Artifact]:
    row = get_conn().execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
    return _row_to_artifact(row) if row else None


def get_artifact_for(artifact_id: str, user_id: str) -> Optional[Artifact]:
    artifact = get_artifact(artifact_id)
    return artifact if artifact and get_run_for(artifact.run_id, user_id) else None


def list_artifacts(run_id: str) -> list[Artifact]:
    rows = get_conn().execute(
        "SELECT * FROM artifacts WHERE run_id=? ORDER BY created_at DESC", (run_id,)
    ).fetchall()
    return [_row_to_artifact(row) for row in rows]


def review_artifact(artifact_id: str, status: str, actor_id: str) -> Artifact:
    if status not in {"accepted", "rejected", "pending"}:
        raise ValueError("invalid artifact acceptance status")
    now = time.time()
    get_conn().execute(
        """UPDATE artifacts SET acceptance_status=?, accepted_by=?, accepted_at=?, updated_at=?
           WHERE id=?""",
        (status, actor_id if status != "pending" else None,
         now if status != "pending" else None, now, artifact_id),
    )
    get_conn().commit()
    artifact = get_artifact(artifact_id)
    if not artifact:
        raise KeyError(artifact_id)
    if status == "accepted":
        remaining = get_conn().execute(
            "SELECT COUNT(*) AS n FROM artifacts WHERE run_id=? AND acceptance_status!='accepted'",
            (artifact.run_id,),
        ).fetchone()["n"]
        run = get_run(artifact.run_id)
        if remaining == 0 and run and run.status == "completed":
            set_run_status(run.id, "accepted")
    return artifact


# ---- messages -----------------------------------------------------------

def add_message(
    *,
    session_id: str,
    role: str,
    content: str,
    actor: str,
    trace: Optional[list[dict[str, Any]]] = None,
    usage: Optional[dict[str, Any]] = None,
) -> Message:
    m = Message(
        id=new_uuid(),
        session_id=session_id,
        role=role,
        content=content,
        actor=actor,
        trace=trace or [],
        usage=usage,
        created_at=time.time(),
    )
    get_conn().execute(
        """INSERT INTO messages (id,session_id,role,content,actor,trace,usage,created_at)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            m.id,
            m.session_id,
            m.role,
            m.content,
            m.actor,
            json.dumps(m.trace, ensure_ascii=False),
            json.dumps(m.usage, ensure_ascii=False) if m.usage else None,
            m.created_at,
        ),
    )
    get_conn().commit()
    return m


# ---- projects -----------------------------------------------------------

def create_project(
    *,
    owner_id: str,
    name: str,
    instruction: str = "",
    connectors: Optional[list[str]] = None,
    experts: Optional[list[str]] = None,
    skills: Optional[list[str]] = None,
    knowledge_ids: Optional[list[str]] = None,
) -> Project:
    now = time.time()
    p = Project(
        id=new_uuid(),
        name=name[:120],
        owner_id=owner_id,
        instruction=instruction,
        connectors=connectors or [],
        experts=experts or [],
        skills=skills or [],
        knowledge_ids=knowledge_ids or [],
        created_at=now,
        updated_at=now,
    )
    get_conn().execute(
        """INSERT INTO projects (id,name,owner_id,instruction,connectors,experts,skills,knowledge_ids,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            p.id, p.name, p.owner_id, p.instruction,
            json.dumps(p.connectors, ensure_ascii=False),
            json.dumps(p.experts, ensure_ascii=False),
            json.dumps(p.skills, ensure_ascii=False),
            json.dumps(p.knowledge_ids, ensure_ascii=False),
            p.created_at, p.updated_at,
        ),
    )
    get_conn().commit()
    return p


def _row_to_project(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        name=row["name"],
        owner_id=row["owner_id"],
        instruction=row["instruction"],
        connectors=json.loads(row["connectors"]),
        experts=json.loads(row["experts"]),
        skills=json.loads(row["skills"]),
        knowledge_ids=json.loads(row["knowledge_ids"]) if "knowledge_ids" in row.keys() else [],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        origin=row["origin"] if "origin" in row.keys() else "local",
    )


def get_project(project_id: str, owner_id: Optional[str] = None) -> Optional[Project]:
    if owner_id is not None:
        row = get_conn().execute(
            "SELECT * FROM projects WHERE id=? AND owner_id=?", (project_id, owner_id)
        ).fetchone()
    else:
        row = get_conn().execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    return _row_to_project(row) if row else None


def list_projects(owner_id: str) -> list[Project]:
    rows = get_conn().execute(
        "SELECT * FROM projects WHERE owner_id=? ORDER BY updated_at DESC", (owner_id,)
    ).fetchall()
    return [_row_to_project(r) for r in rows]


def update_project(
    project_id: str,
    *,
    name: Optional[str] = None,
    instruction: Optional[str] = None,
    connectors: Optional[list[str]] = None,
    experts: Optional[list[str]] = None,
    skills: Optional[list[str]] = None,
    knowledge_ids: Optional[list[str]] = None,
) -> Project:
    sets: list[str] = []
    vals: list[Any] = []
    server_fields_changed = any(value is not None for value in (name, instruction, connectors, experts, skills))
    if name is not None:
        sets.append("name=?"); vals.append(name[:120])
    if instruction is not None:
        sets.append("instruction=?"); vals.append(instruction)
    if connectors is not None:
        sets.append("connectors=?"); vals.append(json.dumps(connectors, ensure_ascii=False))
    if experts is not None:
        sets.append("experts=?"); vals.append(json.dumps(experts, ensure_ascii=False))
    if skills is not None:
        sets.append("skills=?"); vals.append(json.dumps(skills, ensure_ascii=False))
    if knowledge_ids is not None:
        sets.append("knowledge_ids=?"); vals.append(json.dumps(knowledge_ids, ensure_ascii=False))
    if server_fields_changed:
        sets.append("server_dirty=CASE WHEN origin='server' THEN 1 ELSE server_dirty END")
    sets.append("updated_at=?"); vals.append(time.time())
    vals.append(project_id)
    get_conn().execute(f"UPDATE projects SET {', '.join(sets)} WHERE id=?", vals)
    get_conn().commit()
    p = get_project(project_id)
    assert p is not None
    return p


def list_project_sessions(project_id: str) -> list[Session]:
    rows = get_conn().execute(
        "SELECT * FROM sessions WHERE project_id=? ORDER BY updated_at DESC", (project_id,)
    ).fetchall()
    return [_row_to_session(r) for r in rows]


# ---- experts (自定义专家 · WB-049) -------------------------------------

def create_expert(
    *,
    owner_id: str,
    name: str,
    subtitle: str = "",
    avatar: str = "🧑",
    intro: str = "",
    persona: str = "",
    tags: Optional[list[str]] = None,
) -> Expert:
    now = time.time()
    e = Expert(
        id=new_uuid(),
        owner_id=owner_id,
        name=name[:60],
        subtitle=subtitle[:60],
        avatar=(avatar or "🧑")[:8],
        intro=intro[:2000],
        persona=persona[:4000],
        tags=[t[:20] for t in (tags or [])[:8]],
        created_at=now,
        updated_at=now,
    )
    get_conn().execute(
        """INSERT INTO experts (id,owner_id,name,subtitle,avatar,intro,persona,tags,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            e.id, e.owner_id, e.name, e.subtitle, e.avatar, e.intro, e.persona,
            json.dumps(e.tags, ensure_ascii=False), e.created_at, e.updated_at,
        ),
    )
    get_conn().commit()
    return e


def _row_to_expert(row: sqlite3.Row) -> Expert:
    return Expert(
        id=row["id"],
        owner_id=row["owner_id"],
        name=row["name"],
        subtitle=row["subtitle"],
        avatar=row["avatar"],
        intro=row["intro"],
        persona=row["persona"],
        tags=json.loads(row["tags"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def get_expert(expert_id: str, owner_id: Optional[str] = None) -> Optional[Expert]:
    if owner_id is not None:
        row = get_conn().execute(
            "SELECT * FROM experts WHERE id=? AND owner_id=?", (expert_id, owner_id)
        ).fetchone()
    else:
        row = get_conn().execute("SELECT * FROM experts WHERE id=?", (expert_id,)).fetchone()
    return _row_to_expert(row) if row else None


def list_experts(owner_id: str) -> list[Expert]:
    rows = get_conn().execute(
        "SELECT * FROM experts WHERE owner_id=? ORDER BY updated_at DESC", (owner_id,)
    ).fetchall()
    return [_row_to_expert(r) for r in rows]


def delete_expert(expert_id: str, owner_id: str) -> bool:
    cur = get_conn().execute(
        "DELETE FROM experts WHERE id=? AND owner_id=?", (expert_id, owner_id)
    )
    get_conn().commit()
    return cur.rowcount > 0


# ---- catalog: 目录定义（WB-059）----------------------------------------
# 内置专家人格 + 连接器启动注册表从硬编码迁到 catalog_experts / catalog_connectors。
# 运行时读库：persona_for → builtin_persona；mcp_client → connector_specs。

def _row_to_catalog_expert(r: sqlite3.Row) -> CatalogExpert:
    return CatalogExpert(
        id=r["id"], scope=r["scope"], owner_id=r["owner_id"], slug=r["slug"], name=r["name"],
        subtitle=r["subtitle"], avatar=r["avatar"], intro=r["intro"], persona=r["persona"],
        tags=json.loads(r["tags"]) if r["tags"] else [], category=r["category"], badge=r["badge"],
        source=r["source"], functional=bool(r["functional"]), enabled=bool(r["enabled"]),
        sort=r["sort"], created_at=r["created_at"], updated_at=r["updated_at"],
    )


def expert_spec_for(key: str) -> Optional[dict[str, str]]:
    """按稳定 slug 或兼容展示名解析真专家定义；Server 同身份覆盖 builtin。"""
    row = get_conn().execute(
        "SELECT slug,name,persona FROM catalog_experts "
        "WHERE (slug=? OR name=?) AND functional=1 AND enabled=1 AND persona<>'' "
        "ORDER BY CASE scope WHEN 'server' THEN 0 ELSE 1 END, sort LIMIT 1",
        (key, key),
    ).fetchone()
    return {"slug": row["slug"], "name": row["name"], "persona": row["persona"]} if row else None


def builtin_persona(name: str) -> Optional[str]:
    """兼容旧调用：某个专家 slug/名称对应的内置/目录人格。命中 enabled 且 functional，
    Server 同名定义优先；Server 不下发时回退 builtin（调用方再回退通用人格）。"""
    spec = expert_spec_for(name)
    return spec["persona"] if spec else None


def list_catalog_experts(scope: Optional[str] = None, functional: Optional[bool] = None) -> list[CatalogExpert]:
    sql = "SELECT * FROM catalog_experts WHERE enabled=1"
    vals: list[Any] = []
    if scope is not None:
        sql += " AND scope=?"; vals.append(scope)
    if functional is not None:
        sql += " AND functional=?"; vals.append(1 if functional else 0)
    sql += " ORDER BY sort, name"
    rows = get_conn().execute(sql, vals).fetchall()
    return [_row_to_catalog_expert(r) for r in rows]


def expert_catalog_specs() -> list[dict[str, Any]]:
    """去重后的公开专家定义，Server 覆盖 builtin；用户自定义专家不进入此公共推荐目录。"""
    rows = get_conn().execute(
        "SELECT scope,slug,name,subtitle,avatar,intro,persona,tags,category,badge,source,functional "
        "FROM catalog_experts WHERE enabled=1 "
        "ORDER BY CASE scope WHEN 'server' THEN 0 WHEN 'builtin' THEN 1 ELSE 2 END, sort, name"
    ).fetchall()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if row["slug"] in seen or row["scope"] not in {"server", "builtin"}:
            continue
        seen.add(row["slug"])
        try:
            tags = json.loads(row["tags"]) if row["tags"] else []
        except (json.JSONDecodeError, TypeError):
            tags = []
        out.append({
            "slug": row["slug"], "name": row["name"], "subtitle": row["subtitle"],
            "avatar": row["avatar"], "intro": row["intro"], "persona": row["persona"],
            "tags": tags if isinstance(tags, list) else [], "category": row["category"],
            "badge": row["badge"], "source": row["source"], "functional": bool(row["functional"]),
            "scope": row["scope"],
        })
    return out


def replace_server_expert_catalog(items: list[dict[str, Any]]) -> dict[str, int]:
    """用 Server EXPERT_DEFS 全量替换本机 server scope；本机自定义 experts 表完全不动。"""
    conn = get_conn()
    have_a = {r["name"] for r in conn.execute("PRAGMA table_info(automations)").fetchall()}
    for col, ddl in (
        ("timeout_sec", "timeout_sec INTEGER NOT NULL DEFAULT 300"),
        ("max_attempts", "max_attempts INTEGER NOT NULL DEFAULT 3"),
        ("retry_backoff_sec", "retry_backoff_sec INTEGER NOT NULL DEFAULT 30"),
        ("max_total_tokens", "max_total_tokens INTEGER NOT NULL DEFAULT 0"),
        ("notify_policy", "notify_policy TEXT NOT NULL DEFAULT 'failure,recovery'"),
        ("concurrency_policy", "concurrency_policy TEXT NOT NULL DEFAULT 'skip'"),
    ):
        if col not in have_a:
            conn.execute(f"ALTER TABLE automations ADD COLUMN {ddl}")
    now = time.time()
    rows: list[tuple[Any, ...]] = []
    seen: set[str] = set()
    skipped = 0
    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            skipped += 1
            continue
        slug = str(raw.get("slug", "")).strip()
        name = str(raw.get("name", "")).strip()
        persona = str(raw.get("persona", "")).strip()
        tags = raw.get("tags", [])
        if (
            not _SKILL_SLUG_RE.fullmatch(slug) or slug in seen or not name or not persona
            or not isinstance(tags, list)
        ):
            skipped += 1
            continue
        seen.add(slug)
        rows.append((
            new_uuid(), "server", None, slug, name, str(raw.get("subtitle", "")),
            str(raw.get("avatar", "🧑")), str(raw.get("intro", "")), persona,
            json.dumps([str(tag) for tag in tags if str(tag).strip()], ensure_ascii=False),
            str(raw.get("category", "")), str(raw.get("badge", "")), str(raw.get("source", "Server")),
            1 if raw.get("functional", True) else 0, 1, int(raw.get("sort", index)), now, now,
        ))
    with conn:
        conn.execute("DELETE FROM catalog_experts WHERE scope='server'")
        conn.executemany(
            "INSERT INTO catalog_experts "
            "(id,scope,owner_id,slug,name,subtitle,avatar,intro,persona,tags,category,badge,source,"
            "functional,enabled,sort,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
    return {"inserted": len(rows), "skipped": skipped}


def _row_to_catalog_connector(r: sqlite3.Row) -> CatalogConnector:
    try:
        launch = json.loads(r["launch"]) if r["launch"] else {}
    except (json.JSONDecodeError, TypeError):
        launch = {}
    return CatalogConnector(
        id=r["id"], scope=r["scope"], owner_id=r["owner_id"], slug=r["slug"], name=r["name"], icon=r["icon"],
        description=r["description"], status=r["status"], launch=launch if isinstance(launch, dict) else {},
        enabled=bool(r["enabled"]), sort=r["sort"], created_at=r["created_at"], updated_at=r["updated_at"],
    )


def connector_specs() -> dict[str, dict[str, Any]]:
    """连接器名 → 启动 spec（enabled 行），替代 mcp_client 里原硬编码的 CONNECTORS 字典。
    Server 同名定义覆盖 builtin；Server 不下发或被清空时自动回退 builtin。"""
    rows = get_conn().execute(
        "SELECT name, launch FROM catalog_connectors WHERE enabled=1 "
        "ORDER BY CASE scope WHEN 'server' THEN 0 ELSE 1 END, sort, name"
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r["name"] in out:
            continue
        try:
            spec = json.loads(r["launch"]) if r["launch"] else {}
        except (json.JSONDecodeError, TypeError):
            spec = {}
        out[r["name"]] = spec if isinstance(spec, dict) else {}
    return out


def skill_specs() -> list[dict[str, Any]]:
    """内置/目录技能定义清单（enabled 行，按 sort），替代 agent/skills.py 原硬编码的 SKILLS 字典（WB-183）。

    每条：{slug, name, icon, description, instructions, tools:[工具名], category}。
    `tools` 是**名字**——运行时由 `agent/skills.py::_TOOL_REGISTRY` 解析成真 Tool 对象
    （同连接器「launch spec 存库、实现在代码」的分工）。
    """
    rows = get_conn().execute(
        "SELECT scope,slug,name,icon,description,instructions,version,tools,permissions,"
        "tool_contract_version,server_release_id,server_content_hash,files,category,source,"
        "withdrawn,compatible,compatibility_error,min_app_version "
        "FROM catalog_skills WHERE enabled=1 OR (scope='server' AND withdrawn=1) "
        "ORDER BY CASE scope WHEN 'server' THEN 0 ELSE 1 END, sort, name"
    ).fetchall()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for r in rows:
        if r["slug"] in seen:
            continue  # Server 同 slug 覆盖 builtin；前端与运行时都只暴露一个稳定身份。
        seen.add(r["slug"])
        if bool(r["withdrawn"]):
            continue  # Explicit Server tombstone suppresses the same-slug builtin.
        try:
            tools = json.loads(r["tools"]) if r["tools"] else []
        except (json.JSONDecodeError, TypeError):
            tools = []
        try:
            files = json.loads(r["files"]) if r["files"] else []
        except (json.JSONDecodeError, TypeError):
            files = []
        try:
            permissions = json.loads(r["permissions"]) if r["permissions"] else []
        except (json.JSONDecodeError, TypeError):
            permissions = []
        out.append({
            "slug": r["slug"], "name": r["name"], "icon": r["icon"],
            "description": r["description"], "instructions": r["instructions"],
            "version": r["version"],
            "tools": tools if isinstance(tools, list) else [],
            "permissions": permissions if isinstance(permissions, list) else [],
            "tool_contract_version": r["tool_contract_version"],
            "server_release_id": r["server_release_id"],
            "server_content_hash": r["server_content_hash"],
            "files": files if isinstance(files, list) else [],
            "category": r["category"], "source": r["source"], "scope": r["scope"],
            "compatible": bool(r["compatible"]),
            "compatibility_error": r["compatibility_error"],
            "min_app_version": r["min_app_version"],
        })
    return out


def connector_catalog_specs() -> list[dict[str, Any]]:
    """返回去重后的连接器公开元数据，供推荐位解析；不包含本机凭据值。"""
    rows = get_conn().execute(
        "SELECT scope,slug,name,icon,description,status FROM catalog_connectors WHERE enabled=1 "
        "ORDER BY CASE scope WHEN 'server' THEN 0 ELSE 1 END, sort, name"
    ).fetchall()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if row["name"] in seen:
            continue
        seen.add(row["name"])
        out.append({
            "slug": row["slug"], "name": row["name"], "icon": row["icon"], "description": row["description"],
            "status": row["status"], "scope": row["scope"],
        })
    return out


def replace_server_connector_catalog(items: list[dict[str, Any]]) -> dict[str, int]:
    """把 Server 的公开连接器定义映射进本机运行目录；密钥值和 OAuth 状态永不接收。"""
    conn = get_conn()
    now = time.time()
    rows: list[tuple[Any, ...]] = []
    seen_names: set[str] = set()
    skipped = 0
    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            skipped += 1
            continue
        name = str(raw.get("name", "")).strip()
        status = str(raw.get("status", "")).strip()
        launch = raw.get("launch")
        if not name or name in seen_names or status not in {"rdy", "tok"} or not isinstance(launch, dict):
            skipped += 1
            continue
        builtin_server = str(launch.get("builtin_server", "")).strip()
        command = str(launch.get("command", "")).strip()
        if bool(builtin_server) == bool(command):
            skipped += 1
            continue
        secret_env = launch.get("secret_env", {})
        if not isinstance(secret_env, dict) or not all(
            isinstance(k, str) and isinstance(v, str)
            and re.fullmatch(r"[A-Z_][A-Z0-9_]*", k) and re.fullmatch(r"[A-Z_][A-Z0-9_]*", v)
            for k, v in secret_env.items()
        ):
            skipped += 1
            continue
        safe_launch = {
            key: value for key, value in launch.items()
            if key in {"builtin_server", "builtin", "command", "args", "secret_env", "requires", "requires_bin"}
        }
        seen_names.add(name)
        slug = str(raw.get("slug", "")).strip()
        if not _SKILL_SLUG_RE.fullmatch(slug):
            skipped += 1
            continue
        rows.append((
            new_uuid(), "server", None, slug, name, str(raw.get("icon", "🔗")),
            str(raw.get("desc") or raw.get("description") or ""), status,
            json.dumps(safe_launch, ensure_ascii=False), 1, int(raw.get("sort", index)), now, now,
        ))
    with conn:
        conn.execute("DELETE FROM catalog_connectors WHERE scope='server'")
        conn.executemany(
            "INSERT INTO catalog_connectors "
            "(id,scope,owner_id,slug,name,icon,description,status,launch,enabled,sort,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
    return {"inserted": len(rows), "skipped": skipped}


def replace_server_skill_catalog(items: list[dict[str, Any]]) -> dict[str, int]:
    """用 Server 的 APP_SKILLS 全量替换 App 侧 `scope=server` 技能定义（WB-183 Phase C）。

    本机 builtin 行不动，Server 不下发或下发为空时自然回退本机定义。slug 非法、字段缺失或重复的
    目录项跳过；工具名仍由运行时代码注册表裁决，运营数据不能凭空创造工具能力。
    """
    conn = get_conn()
    now = time.time()
    rows: list[tuple[Any, ...]] = []
    seen: set[str] = set()
    skipped = 0
    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            skipped += 1
            continue
        slug = str(raw.get("slug", "")).strip()
        name = str(raw.get("name", "")).strip()
        withdrawn = bool(raw.get("withdrawn"))
        description = str(raw.get("description", "")).strip()
        instructions = str(raw.get("instructions", "")).strip()
        if (
            not slug or not name or (not withdrawn and (not description or not instructions))
            or len(name) > 120 or len(description) > 500 or len(instructions) > 50_000
            or not _SKILL_SLUG_RE.fullmatch(slug) or slug in seen
        ):
            skipped += 1
            continue
        tools = raw.get("tools", [])
        if not isinstance(tools, list):
            tools = []
        permissions = raw.get("permissions", [])
        if not isinstance(permissions, list):
            permissions = []
        files = raw.get("files", [])
        if not isinstance(files, list):
            files = []
        files = [
            {"path": str(item.get("path", "")), "content": str(item.get("content", ""))}
            for item in files if isinstance(item, dict) and item.get("path")
        ]
        seen.add(slug)
        rows.append((
            new_uuid(), "server", None, slug, name, str(raw.get("icon", "🧩")),
            description, instructions, str(raw.get("version", "")),
            json.dumps([str(t) for t in tools], ensure_ascii=False),
            json.dumps(sorted({str(value) for value in permissions if str(value)}), ensure_ascii=False),
            str(raw.get("tool_contract_version", "1")),
            str(raw.get("release_id", "")), str(raw.get("content_hash", "")),
            json.dumps(files, ensure_ascii=False), str(raw.get("category", "")),
            str(raw.get("source", "Server")), 1 if withdrawn else 0,
            1 if raw.get("compatible", True) else 0,
            str(raw.get("compatibility_error", "")), str(raw.get("min_app_version", "0.0.0")),
            0 if withdrawn else 1, int(raw.get("sort", index)), now, now,
        ))
    with conn:
        conn.execute("DELETE FROM catalog_skills WHERE scope='server'")
        conn.executemany(
            """INSERT INTO catalog_skills
               (id,scope,owner_id,slug,name,icon,description,instructions,version,tools,permissions,
                tool_contract_version,server_release_id,server_content_hash,files,category,source,
                withdrawn,compatible,compatibility_error,min_app_version,enabled,sort,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
    return {"inserted": len(rows), "skipped": skipped}


def skill_spec_for(key: str) -> Optional[dict[str, Any]]:
    """按 **slug 或 name** 取一条技能定义；无则 None（调用方据此如实报「未就绪」，WB-179）。

    迁移期两者都认：slug 是目标主键（WB-179 的身份统一），但 loadout 现在存的仍是展示名。
    同 key 命中多行时以 sort 靠前者为准（builtin 种子 sort 小、稳定生效），同 connector_specs。
    """
    k = (key or "").strip()
    if not k:
        return None
    for s in skill_specs():
        if s["slug"] == k or s["name"] == k:
            return s
    return None


def skill_installations(owner_id: str, *, include_deleted: bool = False) -> list[dict[str, Any]]:
    where = "owner_id=?" if include_deleted else "owner_id=? AND deleted_at IS NULL"
    rows = get_conn().execute(
        f"SELECT * FROM skill_installations WHERE {where} ORDER BY slug", (owner_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def skill_installation(owner_id: str, slug: str) -> Optional[dict[str, Any]]:
    row = get_conn().execute(
        "SELECT * FROM skill_installations WHERE owner_id=? AND slug=?", (owner_id, slug),
    ).fetchone()
    return dict(row) if row else None


def upsert_skill_installation(
    owner_id: str, slug: str, package_key: str, *, release_id: str = "",
    content_hash: str = "", enabled: bool = True,
) -> dict[str, Any]:
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO skill_installations
               (owner_id,slug,package_key,release_id,content_hash,enabled,deleted_at,trash_path,created_at,updated_at)
               VALUES (?,?,?,?,?,?,NULL,'',?,?)
               ON CONFLICT(owner_id,slug) DO UPDATE SET
                 package_key=excluded.package_key,release_id=excluded.release_id,
                 content_hash=excluded.content_hash,enabled=excluded.enabled,
                 deleted_at=NULL,trash_path='',updated_at=excluded.updated_at""",
            (owner_id, slug, package_key, release_id, content_hash, 1 if enabled else 0, now, now),
        )
    return skill_installation(owner_id, slug) or {}


def set_skill_installation_enabled(owner_id: str, slug: str, enabled: bool) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE skill_installations SET enabled=?,updated_at=? "
            "WHERE owner_id=? AND slug=? AND deleted_at IS NULL",
            (1 if enabled else 0, time.time(), owner_id, slug),
        )
    return cur.rowcount > 0


def delete_skill_installation(owner_id: str, slug: str, *, trash_path: str = "") -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE skill_installations SET enabled=0,deleted_at=?,trash_path=?,updated_at=? "
            "WHERE owner_id=? AND slug=? AND deleted_at IS NULL",
            (time.time(), trash_path, time.time(), owner_id, slug),
        )
    return cur.rowcount > 0


def set_skill_installation_trash(owner_id: str, slug: str, trash_path: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE skill_installations SET trash_path=?,updated_at=? WHERE owner_id=? AND slug=?",
            (trash_path, time.time(), owner_id, slug),
        )


def set_skill_package_trash(package_key: str, trash_path: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE skill_installations SET trash_path=?,updated_at=? "
            "WHERE package_key=? AND deleted_at IS NOT NULL",
            (trash_path, time.time(), package_key),
        )


def skill_package_ref_count(package_key: str) -> int:
    row = get_conn().execute(
        "SELECT COUNT(*) AS n FROM skill_installations WHERE package_key=?",
        (package_key,),
    ).fetchone()
    return int(row["n"] if row else 0)


def skill_package_active_ref_count(package_key: str) -> int:
    row = get_conn().execute(
        "SELECT COUNT(*) AS n FROM skill_installations WHERE package_key=? AND deleted_at IS NULL",
        (package_key,),
    ).fetchone()
    return int(row["n"] if row else 0)


def skill_has_project_references(slug: str) -> bool:
    for row in get_conn().execute("SELECT skills FROM projects").fetchall():
        try:
            values = json.loads(row["skills"] or "[]")
        except (json.JSONDecodeError, TypeError):
            values = []
        if isinstance(values, list) and slug in values:
            return True
    return False


def restore_skill_installation(owner_id: str, slug: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE skill_installations SET enabled=1,deleted_at=NULL,trash_path='',updated_at=? "
            "WHERE owner_id=? AND slug=? AND deleted_at IS NOT NULL",
            (time.time(), owner_id, slug),
        )
    return cur.rowcount > 0


def forget_skill_trash(trash_path: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM skill_installations WHERE trash_path=? AND deleted_at IS NOT NULL",
            (trash_path,),
        )


def skill_catalog_state(key: str) -> dict[str, Any]:
    """Return Server authority state even when a tombstone suppresses normal specs."""
    value = (key or "").strip()
    if not value:
        return {"withdrawn": False}
    row = get_conn().execute(
        "SELECT slug,name,withdrawn,compatible,compatibility_error,min_app_version "
        "FROM catalog_skills WHERE scope='server' AND (slug=? OR name=?) "
        "ORDER BY sort LIMIT 1",
        (value, value),
    ).fetchone()
    if not row:
        return {"withdrawn": False}
    return {
        "slug": row["slug"], "withdrawn": bool(row["withdrawn"]),
        "compatible": bool(row["compatible"]),
        "compatibility_error": row["compatibility_error"],
        "min_app_version": row["min_app_version"],
    }


def migrate_skill_identities(resolve: Callable[[str], Optional[str]]) -> dict[str, int]:
    """把 projects/assistants 的历史技能展示名原地归一为 slug（WB-183 Phase B）。

    不改 schema：两列本来就是 JSON 数组。能解析的展示名改为 slug，无法解析且不是合法
    slug 的旧商品卡名丢弃；重复项去重。函数幂等，每次启动可安全重跑。
    """
    conn = get_conn()
    changed = dropped = 0
    for table in ("projects", "assistants"):
        rows = conn.execute(f"SELECT id, skills FROM {table}").fetchall()
        for row in rows:
            try:
                old = json.loads(row["skills"] or "[]")
            except (json.JSONDecodeError, TypeError):
                old = []
            if not isinstance(old, list):
                old = []
            new: list[str] = []
            for raw in old:
                value = resolve(str(raw))
                if not value:
                    dropped += 1
                    continue
                if value not in new:
                    new.append(value)
            if new != old:
                conn.execute(
                    f"UPDATE {table} SET skills=? WHERE id=?",
                    (json.dumps(new, ensure_ascii=False), row["id"]),
                )
                changed += 1
    conn.commit()
    return {"changed": changed, "dropped": dropped}


def _migrate_expert_team_identities() -> None:
    """WB-231：为旧库已播种的默认专家团补稳定 expert_slug；不改运营自建团队/已有引用。"""
    conn = get_conn()
    try:
        seed = json.loads(_SHOWCASE_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    seed_teams = {
        team.get("name"): team for team in seed.get("EXP_TEAMS", []) if isinstance(team, dict)
    }
    changed = False
    for row in conn.execute(
        "SELECT id,data FROM catalog_showcase WHERE kind='EXP_TEAMS' AND enabled=1"
    ).fetchall():
        try:
            team = json.loads(row["data"])
        except (json.JSONDecodeError, TypeError):
            continue
        source = seed_teams.get(team.get("name")) if isinstance(team, dict) else None
        if not source:
            continue
        slug_by_name = {
            member.get("name"): member.get("expert_slug")
            for member in source.get("members", []) if isinstance(member, dict)
        }
        members = team.get("members", [])
        if not isinstance(members, list):
            continue
        updated = False
        for member in members:
            if not isinstance(member, dict) or member.get("expert_slug"):
                continue
            slug = slug_by_name.get(member.get("name"))
            if slug:
                member["expert_slug"] = slug
                updated = True
        if updated:
            conn.execute(
                "UPDATE catalog_showcase SET data=?, updated_at=? WHERE id=?",
                (json.dumps(team, ensure_ascii=False), time.time(), row["id"]),
            )
            changed = True
    if changed:
        conn.commit()


def list_catalog_connectors(scope: Optional[str] = None) -> list[CatalogConnector]:
    if scope is not None:
        rows = get_conn().execute(
            "SELECT * FROM catalog_connectors WHERE enabled=1 AND scope=? ORDER BY sort, name", (scope,)
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT * FROM catalog_connectors WHERE enabled=1 ORDER BY sort, name"
        ).fetchall()
    return [_row_to_catalog_connector(r) for r in rows]


# ---- catalog: 橱窗目录（WB-060）----------------------------------------
# catalog.ts 的静态商品卡入库；前端 catalogStore 消费 showcase_all()，替代静态 import。

def showcase_all() -> dict[str, Any]:
    """所有橱窗目录，按 export 名（kind）分组：数组类 → enabled 行按 sort 还原成列表；
    对象类（is_scalar）→ 该行整个对象。逐字对齐迁移前的 catalog.ts 各导出。"""
    rows = get_conn().execute(
        "SELECT kind, data, is_scalar FROM catalog_showcase WHERE enabled=1 ORDER BY kind, sort"
    ).fetchall()
    out: dict[str, Any] = {}
    scalar_kinds: set[str] = set()
    for r in rows:
        try:
            val = json.loads(r["data"])
        except (json.JSONDecodeError, TypeError):
            continue
        if r["is_scalar"]:
            out[r["kind"]] = val
            scalar_kinds.add(r["kind"])
        else:
            out.setdefault(r["kind"], []).append(val)
    # WB-066: Server 目录下发覆盖本地（仅数组类分类）；无下发/离线 → 本地兜底。scalar 分类 skeleton 不覆盖。
    for cat, items in downlink_by_category().items():
        if cat not in scalar_kinds:
            out[cat] = items
    # 推荐技能与分类由真定义表生成，彻底替代无 slug/category 的 SK_GRID/SK_CATS 静态快照。
    specs = skill_specs()
    out["SK_GRID"] = [
        {"slug": s["slug"], "name": s["name"], "icon": s["icon"],
         "description": s["description"], "category": s["category"], "source": s["source"]}
        for s in specs
    ]
    spec_by_slug = {s["slug"]: s for s in specs}
    downlink = downlink_by_category()
    raw_recommendations = downlink.get("SKILL_RECOMMENDATIONS")
    if raw_recommendations is None:
        # 未连接 Server / Server 尚未配置推荐位：保持 local-first 离线兜底。
        recommendations = [
            {"provider": "agentmate", "placement": "skills.recommended", **card}
            for card in out["SK_GRID"]
        ]
    else:
        now = time.time()
        recommendations = []
        for raw in raw_recommendations:
            if not isinstance(raw, dict) or raw.get("placement", "skills.recommended") != "skills.recommended":
                continue
            if raw.get("_enabled", True) is False:
                continue
            try:
                starts_at = float(raw.get("starts_at") or 0)
                ends_at = float(raw.get("ends_at") or 0)
            except (TypeError, ValueError):
                continue
            if (starts_at and now < starts_at) or (ends_at and now >= ends_at):
                continue
            provider = str(raw.get("provider", "")).lower()
            slug = str(raw.get("skill_slug", "")).strip()
            base = spec_by_slug.get(slug) if provider == "agentmate" else None
            if provider not in {"agentmate", "skillhub"} or (provider == "agentmate" and not base):
                continue
            recommendations.append({
                "provider": provider,
                "placement": "skills.recommended",
                "slug": slug,
                "name": str(raw.get("title") or (base or {}).get("name") or slug),
                "icon": str(raw.get("icon") or (base or {}).get("icon") or "🧩"),
                "description": str(raw.get("description") or (base or {}).get("description") or ""),
                "category": str(raw.get("category") or (base or {}).get("category") or "其他"),
                "source": "AgentMate" if provider == "agentmate" else "SkillHub",
            })
    out["SK_RECOMMENDATIONS"] = recommendations
    recommendation_categories = list(dict.fromkeys(
        str(skill["category"]) for skill in recommendations if skill.get("category")
    ))
    managed_skill_categories = downlink.get("SKILL_CATEGORIES")
    if managed_skill_categories is not None:
        managed_names = [
            str(category.get("name") or "") for category in managed_skill_categories
            if isinstance(category, dict) and category.get("name")
        ]
        ordered_categories = [name for name in managed_names if name in recommendation_categories]
        ordered_categories.extend(name for name in recommendation_categories if name not in ordered_categories)
    else:
        ordered_categories = recommendation_categories
    out["SK_CATS"] = ["全部", *ordered_categories]
    # WB-220：连接器定义进入本机真运行目录，推荐位只解析公开卡片；凭据/授权态仍由本机接口判定。
    connector_specs_public = connector_catalog_specs()
    connector_by_slug = {c["slug"]: c for c in connector_specs_public if c.get("slug")}
    raw_connector_recommendations = downlink.get("CONNECTOR_RECOMMENDATIONS")
    if raw_connector_recommendations is None:
        connector_recommendations = [
            {"placement": "connectors.recommended", **connector}
            for connector in connector_specs_public
        ]
    else:
        connector_recommendations = []
        now = time.time()
        for raw in raw_connector_recommendations:
            if not isinstance(raw, dict) or raw.get("placement", "connectors.recommended") != "connectors.recommended":
                continue
            if raw.get("_enabled", True) is False:
                continue
            try:
                starts_at = float(raw.get("starts_at") or 0)
                ends_at = float(raw.get("ends_at") or 0)
            except (TypeError, ValueError):
                continue
            if (starts_at and now < starts_at) or (ends_at and now >= ends_at):
                continue
            base = connector_by_slug.get(str(raw.get("connector_slug", "")).strip())
            if base:
                connector_recommendations.append({"placement": "connectors.recommended", **base})
    out["CONNECTOR_RECOMMENDATIONS"] = connector_recommendations
    # WB-221：专家推荐位解析 Server 真定义；无 Server 时沿用本地展示快照与 builtin persona。
    expert_specs_public = expert_catalog_specs()
    expert_by_slug = {expert["slug"]: expert for expert in expert_specs_public if expert.get("slug")}
    raw_expert_recommendations = downlink.get("EXPERT_RECOMMENDATIONS")
    if raw_expert_recommendations is None:
        expert_recommendations = []
        for raw in out.get("EXP_GRID", []):
            if not isinstance(raw, list) or len(raw) < 7:
                continue
            expert_recommendations.append({
                "slug": str(raw[1]), "avatar": str(raw[0]), "name": str(raw[1]),
                "subtitle": str(raw[2]), "badge": str(raw[3]), "intro": str(raw[4]),
                "tags": raw[5] if isinstance(raw[5], list) else [], "category": str(raw[6]),
                "placement": "experts.recommended", "scope": "builtin",
            })
    else:
        expert_recommendations = []
        now = time.time()
        for raw in raw_expert_recommendations:
            if not isinstance(raw, dict) or raw.get("placement", "experts.recommended") != "experts.recommended":
                continue
            if raw.get("_enabled", True) is False:
                continue
            try:
                starts_at = float(raw.get("starts_at") or 0)
                ends_at = float(raw.get("ends_at") or 0)
            except (TypeError, ValueError):
                continue
            if (starts_at and now < starts_at) or (ends_at and now >= ends_at):
                continue
            base = expert_by_slug.get(str(raw.get("expert_slug", "")).strip())
            if base:
                expert_recommendations.append({"placement": "experts.recommended", **base})
    out["EXPERT_RECOMMENDATIONS"] = expert_recommendations
    existing_expert_cats = out.get("EXP_CATS", []) if isinstance(out.get("EXP_CATS"), list) else []
    out["EXP_CATS"] = ["全部", *dict.fromkeys([
        *[str(cat) for cat in existing_expert_cats if cat and cat != "全部"],
        *[str(expert.get("category")) for expert in expert_recommendations if expert.get("category")],
    ])]
    return out


def replace_all_downlink(items: list[dict]) -> None:
    """幂等重置 Server 目录下发镜像：清空后按 Server 返回全量重建（Server 侧删除随之消失）。
    items = [{category, data, sort}, ...]（WB-066）。"""
    conn = get_conn()
    conn.execute("DELETE FROM catalog_downlink")
    now = time.time()
    conn.executemany(
        "INSERT INTO catalog_downlink (id,category,data,sort,updated_at) VALUES (?,?,?,?,?)",
        [(new_uuid(), str(it.get("category", "")), json.dumps(it.get("data"), ensure_ascii=False),
          int(it.get("sort", 0)), now) for it in items],
    )
    conn.commit()


def downlink_by_category() -> dict[str, list]:
    rows = get_conn().execute(
        "SELECT category, data FROM catalog_downlink ORDER BY category, sort"
    ).fetchall()
    out: dict[str, list] = {}
    for r in rows:
        try:
            out.setdefault(r["category"], []).append(json.loads(r["data"]))
        except (json.JSONDecodeError, TypeError):
            continue
    return out


# ---- project membership / roles (M7 C2) --------------------------------

def add_project_member(project_id: str, user_id: str, role: Role) -> None:
    """Add a member or change their role (upsert). The owner is never stored here."""
    conn = get_conn()
    now = time.time()
    project = conn.execute("SELECT origin FROM projects WHERE id=?", (project_id,)).fetchone()
    dirty = int(bool(project and project["origin"] == "server"))
    conn.execute(
        """INSERT INTO project_members
           (project_id,user_id,role,created_at,updated_at,server_updated_at,server_dirty)
           VALUES (?,?,?,?,?,0,?)
           ON CONFLICT(project_id,user_id) DO UPDATE SET
             role=excluded.role,updated_at=excluded.updated_at,
             server_dirty=CASE WHEN excluded.server_dirty=1 THEN 1 ELSE project_members.server_dirty END""",
        (project_id, user_id, role.value, now, now, dirty),
    )
    conn.execute("DELETE FROM server_member_tombstones WHERE project_id=? AND user_id=?", (project_id, user_id))
    conn.commit()


def remove_project_member(project_id: str, user_id: str) -> None:
    conn = get_conn()
    row = conn.execute(
        """SELECT m.server_updated_at,p.origin FROM project_members m
           JOIN projects p ON p.id=m.project_id WHERE m.project_id=? AND m.user_id=?""",
        (project_id, user_id),
    ).fetchone()
    if row and row["origin"] == "server":
        conn.execute(
            """INSERT INTO server_member_tombstones
               (project_id,user_id,local_deleted_at,server_updated_at) VALUES (?,?,?,?)
               ON CONFLICT(project_id,user_id) DO UPDATE SET
                 local_deleted_at=excluded.local_deleted_at,server_updated_at=excluded.server_updated_at""",
            (project_id, user_id, time.time(), float(row["server_updated_at"] or 0)),
        )
    conn.execute("DELETE FROM project_members WHERE project_id=? AND user_id=?", (project_id, user_id))
    conn.commit()


def project_member_role(project_id: str, user_id: str) -> Optional[Role]:
    """The user's explicit membership role (does NOT count ownership), or None."""
    row = get_conn().execute(
        "SELECT role FROM project_members WHERE project_id=? AND user_id=?",
        (project_id, user_id),
    ).fetchone()
    return Role(row["role"]) if row else None


def project_access_role(project_id: str, user_id: str) -> Optional[Role]:
    """Effective role for access checks: Owner if the user owns the project, else
    their membership role, else None (no access). This is the single gate C2 uses."""
    row = get_conn().execute("SELECT owner_id FROM projects WHERE id=?", (project_id,)).fetchone()
    if not row:
        return None
    if row["owner_id"] == user_id:
        return Role.OWNER
    return project_member_role(project_id, user_id)


def get_project_for(project_id: str, user_id: str) -> Optional[Project]:
    """Project if the user is owner OR a member, else None — drop-in access gate
    replacing the old owner-only `get_project(id, owner_id=...)`."""
    if project_access_role(project_id, user_id) is None:
        return None
    return get_project(project_id)


def list_projects_for(user_id: str) -> list[tuple[Project, Role]]:
    """Projects the user owns or is a member of, newest first, each with the
    caller's effective role."""
    rows = get_conn().execute(
        """
        SELECT p.*, 'Owner' AS _role FROM projects p WHERE p.owner_id=?
        UNION
        SELECT p.*, m.role AS _role FROM projects p
          JOIN project_members m ON m.project_id = p.id
          WHERE m.user_id=? AND p.owner_id<>?
        ORDER BY updated_at DESC
        """,
        (user_id, user_id, user_id),
    ).fetchall()
    return [(_row_to_project(r), Role(r["_role"])) for r in rows]


def list_project_members(project_id: str) -> list[dict]:
    """Members with names + roles, owner first. The owner is synthesised from
    projects.owner_id (they have no project_members row)."""
    proj = get_conn().execute("SELECT owner_id FROM projects WHERE id=?", (project_id,)).fetchone()
    if not proj:
        return []
    out: list[dict] = []
    owner = get_user(proj["owner_id"])
    if owner:
        out.append({"user_id": owner.id, "name": owner.name, "role": Role.OWNER.value, "is_owner": True})
    rows = get_conn().execute(
        "SELECT m.user_id, m.role, u.name FROM project_members m "
        "JOIN users u ON u.id = m.user_id WHERE m.project_id=? ORDER BY m.created_at",
        (project_id,),
    ).fetchall()
    for r in rows:
        out.append({"user_id": r["user_id"], "name": r["name"], "role": r["role"], "is_owner": False})
    return out


# ---- notifications / message center (M7 C4) -----------------------------

def create_notification(
    *,
    user_id: str,
    kind: str,
    title: str,
    body: str = "",
    project_id: Optional[str] = None,
    actor_name: Optional[str] = None,
) -> None:
    get_conn().execute(
        "INSERT INTO notifications (id,user_id,kind,title,body,project_id,actor_name,read,created_at) "
        "VALUES (?,?,?,?,?,?,?,0,?)",
        (new_uuid(), user_id, kind, title, body, project_id, actor_name, time.time()),
    )
    get_conn().commit()


def list_notifications(user_id: str, limit: int = 50) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def unread_notification_count(user_id: str) -> int:
    return get_conn().execute(
        "SELECT COUNT(*) FROM notifications WHERE user_id=? AND read=0", (user_id,)
    ).fetchone()[0]


def mark_notifications_read(user_id: str, ids: Optional[list[str]] = None) -> None:
    """Mark the user's notifications read — all of them when ids is None, or just
    `ids`. An empty list marks NONE (WB-160): the API contract is None=all, so `[]`
    must not fall through to marking everything read."""
    conn = get_conn()
    if ids is None:
        conn.execute("UPDATE notifications SET read=1 WHERE user_id=?", (user_id,))
    elif ids:
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"UPDATE notifications SET read=1 WHERE user_id=? AND id IN ({placeholders})",
            (user_id, *ids),
        )
    conn.commit()


# ---- work items (kanban / tasks, §11 阶段 B) ----------------------------

def _row_to_work_item(r: sqlite3.Row) -> WorkItem:
    keys = r.keys()
    try:
        attachments = json.loads(r["attachments"]) if "attachments" in keys and r["attachments"] else []
    except (json.JSONDecodeError, TypeError):
        attachments = []
    try:
        labels = json.loads(r["labels"]) if "labels" in keys and r["labels"] else []
    except (json.JSONDecodeError, TypeError):
        labels = []
    return WorkItem(
        id=r["id"], project_id=r["project_id"], owner_id=r["owner_id"], title=r["title"],
        status=r["status"], source=r["source"], assignee=r["assignee"],
        created_at=r["created_at"], updated_at=r["updated_at"],
        description=r["description"] if "description" in keys and r["description"] else "",
        due_date=r["due_date"] if "due_date" in keys else None,
        attachments=attachments if isinstance(attachments, list) else [],
        priority=r["priority"] if "priority" in keys and r["priority"] else "",
        start_date=r["start_date"] if "start_date" in keys else None,
        labels=labels if isinstance(labels, list) else [],
        parent_id=r["parent_id"] if "parent_id" in keys and r["parent_id"] else "",
        milestone_id=r["milestone_id"] if "milestone_id" in keys and r["milestone_id"] else "",
        estimate_h=float(r["estimate_h"]) if "estimate_h" in keys and r["estimate_h"] is not None else 0.0,
        spent_h=float(r["spent_h"]) if "spent_h" in keys and r["spent_h"] is not None else 0.0,
    )


def create_work_item(
    *, project_id: str, owner_id: str, title: str, status: str = "todo",
    source: str = "手动", assignee: str = "", description: str = "",
    due_date: Optional[str] = None, attachments: Optional[list] = None,
    priority: str = "", start_date: Optional[str] = None,
    labels: Optional[list] = None, parent_id: str = "", milestone_id: str = "",
    estimate_h: float = 0.0, spent_h: float = 0.0,
) -> WorkItem:
    now = time.time()
    wi = WorkItem(
        id=new_uuid(), project_id=project_id, owner_id=owner_id, title=title[:200],
        status=status, source=source, assignee=assignee or owner_id,
        created_at=now, updated_at=now,
        description=description[:4000], due_date=due_date, attachments=attachments or [],
        priority=priority, start_date=start_date, labels=labels or [],
        parent_id=parent_id, milestone_id=milestone_id,
        estimate_h=estimate_h or 0.0, spent_h=spent_h or 0.0,
    )
    get_conn().execute(
        """INSERT INTO work_items
           (id,project_id,owner_id,title,status,source,assignee,created_at,updated_at,description,due_date,attachments,
            priority,start_date,labels,parent_id,milestone_id,estimate_h,spent_h)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (wi.id, wi.project_id, wi.owner_id, wi.title, wi.status, wi.source, wi.assignee,
         wi.created_at, wi.updated_at, wi.description, wi.due_date, json.dumps(wi.attachments, ensure_ascii=False),
         wi.priority, wi.start_date, json.dumps(wi.labels, ensure_ascii=False), wi.parent_id, wi.milestone_id,
         wi.estimate_h, wi.spent_h),
    )
    get_conn().commit()
    return wi


def list_work_items(project_id: str) -> list[WorkItem]:
    rows = get_conn().execute(
        "SELECT * FROM work_items WHERE project_id=? ORDER BY created_at ASC", (project_id,)
    ).fetchall()
    return [_row_to_work_item(r) for r in rows]


def mirror_server_work_items(project_id: str, items: list[dict]) -> None:
    """按 work item ``id + updated_at`` 增量合并，保留附件等本机字段与离线分叉。"""
    conn = get_conn()
    remote_ids: set[str] = set()
    for it in items:
        item_id = str(it.get("id") or "")
        if not item_id:
            continue
        remote_ids.add(item_id)
        labels = it.get("labels") or []
        remote_ts = float(it.get("updated_at") or it.get("created_at") or time.time())
        remote = {
            "title": str(it.get("title") or "")[:200], "status": it.get("status", "todo"),
            "source": it.get("source", "手动"), "assignee": it.get("assignee", ""),
            "description": str(it.get("description") or "")[:4000], "due_date": it.get("due_date") or None,
            "priority": it.get("priority", ""), "start_date": it.get("start_date") or None,
            "labels": labels if isinstance(labels, list) else [], "parent_id": it.get("parent_id", ""),
            "milestone_id": it.get("milestone_id", ""), "estimate_h": float(it.get("estimate_h") or 0),
            "spent_h": float(it.get("spent_h") or 0),
        }
        local = conn.execute("SELECT * FROM work_items WHERE id=?", (item_id,)).fetchone()
        if local is None:
            conn.execute(
                """INSERT INTO work_items
                   (id,project_id,owner_id,title,status,source,assignee,created_at,updated_at,description,due_date,attachments,
                    priority,start_date,labels,parent_id,milestone_id,estimate_h,spent_h,server_updated_at,server_dirty)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)""",
                (item_id, project_id, "", remote["title"], remote["status"], remote["source"], remote["assignee"],
                 float(it.get("created_at") or remote_ts), remote_ts, remote["description"], remote["due_date"], "[]",
                 remote["priority"], remote["start_date"], json.dumps(remote["labels"], ensure_ascii=False),
                 remote["parent_id"], remote["milestone_id"], remote["estimate_h"], remote["spent_h"], remote_ts),
            )
            _clear_server_conflict("work_item", item_id, commit=False)
            continue
        local_payload = {
            "title": local["title"], "status": local["status"], "source": local["source"],
            "assignee": local["assignee"], "description": local["description"], "due_date": local["due_date"],
            "priority": local["priority"], "start_date": local["start_date"], "labels": _json_list(local["labels"]),
            "parent_id": local["parent_id"], "milestone_id": local["milestone_id"],
            "estimate_h": float(local["estimate_h"] or 0), "spent_h": float(local["spent_h"] or 0),
        }
        baseline = float(local["server_updated_at"] or 0)
        dirty = bool(local["server_dirty"])
        if baseline == 0 and local_payload != remote and float(local["updated_at"] or 0) > remote_ts:
            dirty = True
        if dirty and local_payload != remote:
            conn.execute("UPDATE work_items SET server_updated_at=?,server_dirty=1 WHERE id=?", (remote_ts, item_id))
            _record_server_conflict(
                "work_item", item_id, project_id,
                "concurrent_update" if remote_ts > baseline else "local_ahead",
                local["updated_at"], remote_ts, local_payload, remote, commit=False,
            )
        else:
            conn.execute(
                """UPDATE work_items SET title=?,status=?,source=?,assignee=?,updated_at=?,description=?,due_date=?,
                   priority=?,start_date=?,labels=?,parent_id=?,milestone_id=?,estimate_h=?,spent_h=?,
                   server_updated_at=?,server_dirty=0 WHERE id=?""",
                (remote["title"], remote["status"], remote["source"], remote["assignee"], remote_ts,
                 remote["description"], remote["due_date"], remote["priority"], remote["start_date"],
                 json.dumps(remote["labels"], ensure_ascii=False), remote["parent_id"], remote["milestone_id"],
                 remote["estimate_h"], remote["spent_h"], remote_ts, item_id),
            )
            _clear_server_conflict("work_item", item_id, commit=False)
    for local in conn.execute("SELECT * FROM work_items WHERE project_id=?", (project_id,)).fetchall():
        if local["id"] in remote_ids:
            continue
        local_payload = {"title": local["title"], "status": local["status"]}
        if bool(local["server_dirty"]) or not float(local["server_updated_at"] or 0):
            _record_server_conflict(
                "work_item", local["id"], project_id, "local_only", local["updated_at"], 0,
                local_payload, {"deleted": True}, commit=False,
            )
        else:
            conn.execute("DELETE FROM work_items WHERE id=?", (local["id"],))
            _clear_server_conflict("work_item", local["id"], commit=False)
    conn.commit()


def get_work_item(item_id: str, owner_id: Optional[str] = None) -> Optional[WorkItem]:
    if owner_id is not None:
        r = get_conn().execute(
            "SELECT * FROM work_items WHERE id=? AND owner_id=?", (item_id, owner_id)
        ).fetchone()
    else:
        r = get_conn().execute("SELECT * FROM work_items WHERE id=?", (item_id,)).fetchone()
    return _row_to_work_item(r) if r else None


def update_work_item(
    item_id: str, *, title: Optional[str] = None, status: Optional[str] = None,
    description: Optional[str] = None, due_date: Optional[str] = None,
    clear_due_date: bool = False, attachments: Optional[list] = None,
    priority: Optional[str] = None, start_date: Optional[str] = None,
    clear_start_date: bool = False, labels: Optional[list] = None,
    parent_id: Optional[str] = None, milestone_id: Optional[str] = None,
    estimate_h: Optional[float] = None, spent_h: Optional[float] = None,
) -> Optional[WorkItem]:
    sets, vals = [], []
    server_fields_changed = any(value is not None for value in (
        title, status, description, due_date, priority, start_date, labels,
        parent_id, milestone_id, estimate_h, spent_h,
    )) or clear_due_date or clear_start_date
    if title is not None:
        sets.append("title=?"); vals.append(title[:200])
    if status is not None:
        sets.append("status=?"); vals.append(status)
    if description is not None:
        sets.append("description=?"); vals.append(description[:4000])
    if clear_due_date:
        sets.append("due_date=?"); vals.append(None)
    elif due_date is not None:
        sets.append("due_date=?"); vals.append(due_date)
    if attachments is not None:
        sets.append("attachments=?"); vals.append(json.dumps(attachments, ensure_ascii=False))
    if priority is not None:
        sets.append("priority=?"); vals.append(priority)
    if clear_start_date:
        sets.append("start_date=?"); vals.append(None)
    elif start_date is not None:
        sets.append("start_date=?"); vals.append(start_date)
    if labels is not None:
        sets.append("labels=?"); vals.append(json.dumps(labels, ensure_ascii=False))
    if parent_id is not None:
        sets.append("parent_id=?"); vals.append(parent_id)
    if milestone_id is not None:
        sets.append("milestone_id=?"); vals.append(milestone_id)
    if estimate_h is not None:
        sets.append("estimate_h=?"); vals.append(float(estimate_h))
    if spent_h is not None:
        sets.append("spent_h=?"); vals.append(float(spent_h))
    if not sets:
        return get_work_item(item_id)
    if server_fields_changed:
        sets.append(
            "server_dirty=CASE WHEN EXISTS (SELECT 1 FROM projects p "
            "WHERE p.id=work_items.project_id AND p.origin='server') THEN 1 ELSE server_dirty END"
        )
    sets.append("updated_at=?"); vals.append(time.time())
    vals.append(item_id)
    get_conn().execute(f"UPDATE work_items SET {', '.join(sets)} WHERE id=?", vals)
    get_conn().commit()
    return get_work_item(item_id)


def delete_work_item(item_id: str) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM work_items WHERE parent_id=?", (item_id,))  # 连带子任务（本地项目）
    conn.execute("DELETE FROM work_items WHERE id=?", (item_id,))
    conn.commit()


# ---- milestones（WB-108；本地镜像 Server 权威 + 本地项目自管）--------------

def list_milestones(project_id: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM milestones WHERE project_id=? ORDER BY sort", (project_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_milestone(mid: str) -> Optional[dict]:
    r = get_conn().execute("SELECT * FROM milestones WHERE id=?", (mid,)).fetchone()
    return dict(r) if r else None


def create_milestone(*, project_id: str, name: str, description: str = "",
                     due_date: Optional[str] = None, status: str = "open") -> dict:
    mid = new_uuid(); now = time.time()
    mx = get_conn().execute(
        "SELECT COALESCE(MAX(sort),0) FROM milestones WHERE project_id=?", (project_id,)
    ).fetchone()[0]
    get_conn().execute(
        "INSERT INTO milestones (id,project_id,name,description,due_date,status,sort,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (mid, project_id, name[:200], description, due_date, status, mx + 1, now, now),
    )
    get_conn().commit()
    return get_milestone(mid)  # type: ignore[return-value]


def update_milestone(mid: str, **fields: Any) -> Optional[dict]:
    allowed = {"name", "description", "due_date", "status", "sort"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed and v is not None:
            sets.append(f"{k}=?"); vals.append(v)
    if not sets:
        return get_milestone(mid)
    sets.append(
        "server_dirty=CASE WHEN EXISTS (SELECT 1 FROM projects p "
        "WHERE p.id=milestones.project_id AND p.origin='server') THEN 1 ELSE server_dirty END"
    )
    sets.append("updated_at=?"); vals.append(time.time())
    vals.append(mid)
    get_conn().execute(f"UPDATE milestones SET {', '.join(sets)} WHERE id=?", vals)
    get_conn().commit()
    return get_milestone(mid)


def delete_milestone(mid: str) -> None:
    conn = get_conn()
    conn.execute("UPDATE work_items SET milestone_id='' WHERE milestone_id=?", (mid,))  # 解绑任务
    conn.execute("DELETE FROM milestones WHERE id=?", (mid,))
    conn.commit()


def mirror_server_milestones(project_id: str, items: list[dict]) -> None:
    """按 milestone ``id + updated_at`` 增量合并，不再整表删插。"""
    conn = get_conn()
    remote_ids: set[str] = set()
    for i, it in enumerate(items):
        mid = str(it.get("id") or "")
        if not mid:
            continue
        remote_ids.add(mid)
        remote_ts = float(it.get("updated_at") or it.get("created_at") or time.time())
        remote = {
            "name": str(it.get("name") or "")[:200], "description": str(it.get("description") or ""),
            "due_date": it.get("due_date") or None, "status": it.get("status", "open"),
            "sort": int(it.get("sort", i)),
        }
        local = conn.execute("SELECT * FROM milestones WHERE id=?", (mid,)).fetchone()
        if local is None:
            conn.execute(
                """INSERT INTO milestones
                   (id,project_id,name,description,due_date,status,sort,created_at,updated_at,server_updated_at,server_dirty)
                   VALUES (?,?,?,?,?,?,?,?,?,?,0)""",
                (mid, project_id, remote["name"], remote["description"], remote["due_date"], remote["status"],
                 remote["sort"], float(it.get("created_at") or remote_ts), remote_ts, remote_ts),
            )
            _clear_server_conflict("milestone", mid, commit=False)
            continue
        local_payload = {key: local[key] for key in ("name", "description", "due_date", "status", "sort")}
        baseline = float(local["server_updated_at"] or 0)
        dirty = bool(local["server_dirty"])
        if baseline == 0 and local_payload != remote and float(local["updated_at"] or 0) > remote_ts:
            dirty = True
        if dirty and local_payload != remote:
            conn.execute("UPDATE milestones SET server_updated_at=?,server_dirty=1 WHERE id=?", (remote_ts, mid))
            _record_server_conflict(
                "milestone", mid, project_id,
                "concurrent_update" if remote_ts > baseline else "local_ahead",
                local["updated_at"], remote_ts, local_payload, remote, commit=False,
            )
        else:
            conn.execute(
                """UPDATE milestones SET name=?,description=?,due_date=?,status=?,sort=?,updated_at=?,
                   server_updated_at=?,server_dirty=0 WHERE id=?""",
                (remote["name"], remote["description"], remote["due_date"], remote["status"], remote["sort"],
                 remote_ts, remote_ts, mid),
            )
            _clear_server_conflict("milestone", mid, commit=False)
    for local in conn.execute("SELECT * FROM milestones WHERE project_id=?", (project_id,)).fetchall():
        if local["id"] in remote_ids:
            continue
        if bool(local["server_dirty"]) or not float(local["server_updated_at"] or 0):
            _record_server_conflict(
                "milestone", local["id"], project_id, "local_only", local["updated_at"], 0,
                {"name": local["name"], "status": local["status"]}, {"deleted": True}, commit=False,
            )
        else:
            conn.execute("DELETE FROM milestones WHERE id=?", (local["id"],))
            _clear_server_conflict("milestone", local["id"], commit=False)
    conn.commit()


def list_messages(session_id: str) -> list[Message]:
    rows = get_conn().execute(
        "SELECT * FROM messages WHERE session_id=? ORDER BY created_at ASC",
        (session_id,),
    ).fetchall()

    out: list[Message] = []
    for row in rows:
        out.append(
            Message(
                id=row["id"],
                session_id=row["session_id"],
                role=row["role"],
                content=row["content"],
                actor=row["actor"],
                trace=json.loads(row["trace"]) if row["trace"] else [],
                usage=json.loads(row["usage"]) if row["usage"] else None,
                created_at=row["created_at"],
            )
        )
    return out


def create_work_item_launch(
    *, work_item_id: str, owner_id: str, idempotency_key: str,
) -> tuple[dict, bool]:
    item = get_work_item(work_item_id)
    if not item or project_access_role(item.project_id, owner_id) in {None, Role.VIEWER}:
        raise ValueError("work item launch scope mismatch")
    key = idempotency_key.strip()[:200]
    if not key:
        raise ValueError("idempotency_key is required")
    launch_id = new_uuid(); now = time.time()
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO work_item_launches
               (id,work_item_id,owner_id,idempotency_key,status,created_at,updated_at)
               VALUES (?,?,?,?,'queued',?,?)""",
            (launch_id, work_item_id, owner_id, key, now, now),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        row = conn.execute(
            "SELECT * FROM work_item_launches WHERE owner_id=? AND idempotency_key=?",
            (owner_id, key),
        ).fetchone()
        if row:
            return dict(row), False
        raise
    return get_work_item_launch(launch_id), True  # type: ignore[return-value]


def get_work_item_launch(launch_id: str, owner_id: Optional[str] = None) -> Optional[dict]:
    if owner_id is None:
        row = get_conn().execute(
            "SELECT * FROM work_item_launches WHERE id=?", (launch_id,)
        ).fetchone()
    else:
        row = get_conn().execute(
            "SELECT * FROM work_item_launches WHERE id=? AND owner_id=?", (launch_id, owner_id)
        ).fetchone()
    return dict(row) if row else None


def list_work_item_launches(work_item_id: str, user_id: str) -> list[dict]:
    item = get_work_item(work_item_id)
    if not item or project_access_role(item.project_id, user_id) is None:
        return []
    rows = get_conn().execute(
        "SELECT * FROM work_item_launches WHERE work_item_id=? ORDER BY created_at DESC LIMIT 100",
        (work_item_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def attach_work_item_launch_session(launch_id: str, session_id: str) -> dict:
    launch = get_work_item_launch(launch_id)
    session = get_session(session_id)
    if not launch or not session or session.owner_id != launch["owner_id"]:
        raise ValueError("work item launch session scope mismatch")
    get_conn().execute(
        "UPDATE work_item_launches SET session_id=?,status='running',updated_at=? WHERE id=?",
        (session_id, time.time(), launch_id),
    )
    get_conn().commit()
    return get_work_item_launch(launch_id)  # type: ignore[return-value]


def finish_work_item_launch(
    launch_id: str, *, status: str, run_id: Optional[str] = None,
    error_code: Optional[str] = None, error_message: Optional[str] = None,
) -> dict:
    if status not in {"completed", "failed", "cancelled"}:
        raise ValueError("invalid work item launch status")
    now = time.time()
    get_conn().execute(
        """UPDATE work_item_launches SET status=?,run_id=?,error_code=?,error_message=?,
           finished_at=?,updated_at=? WHERE id=?""",
        (status, run_id, error_code, (error_message or "")[:500] or None, now, now, launch_id),
    )
    get_conn().commit()
    launch = get_work_item_launch(launch_id)
    if not launch:
        raise KeyError(launch_id)
    return launch


def accept_work_item_delivery(
    work_item_id: str, run_id: str, actor_id: str,
) -> tuple[WorkItem, Run, list[Artifact]]:
    """Atomically accept every artifact, the Run and its WorkItem (local plane)."""
    conn = get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        item_row = conn.execute("SELECT * FROM work_items WHERE id=?", (work_item_id,)).fetchone()
        run_row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not item_row or not run_row:
            raise KeyError("work item or run not found")
        item = _row_to_work_item(item_row); run = _row_to_run(run_row)
        role = project_access_role(item.project_id, actor_id)
        if role in {None, Role.VIEWER} or run.project_id != item.project_id or run.work_item_id != item.id:
            raise PermissionError("work item delivery scope mismatch")
        if run.status not in {"completed", "accepted"}:
            raise ValueError("only completed runs can be accepted")
        rows = conn.execute("SELECT * FROM artifacts WHERE run_id=?", (run.id,)).fetchall()
        if not rows:
            raise ValueError("run has no artifacts")
        if any(row["validation_status"] != "passed" for row in rows):
            raise ValueError("run has invalid artifacts")
        now = time.time()
        conn.execute(
            """UPDATE artifacts SET acceptance_status='accepted',accepted_by=?,accepted_at=?,updated_at=?
               WHERE run_id=?""",
            (actor_id, now, now, run.id),
        )
        if run.status == "completed":
            conn.execute(
                "UPDATE runs SET status='accepted',ended_at=COALESCE(ended_at,?),updated_at=? WHERE id=?",
                (now, now, run.id),
            )
        conn.execute(
            "UPDATE work_items SET status='done',updated_at=? WHERE id=?", (now, item.id)
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    accepted_item = get_work_item(work_item_id)
    accepted_run = get_run(run_id)
    if not accepted_item or not accepted_run:
        raise RuntimeError("accepted delivery disappeared")
    return accepted_item, accepted_run, list_artifacts(run_id)


    out: list[Message] = []
    for r in rows:
        out.append(
            Message(
                id=r["id"],
                session_id=r["session_id"],
                role=r["role"],
                content=r["content"],
                actor=r["actor"],
                trace=json.loads(r["trace"]) if r["trace"] else [],
                usage=json.loads(r["usage"]) if r["usage"] else None,
                created_at=r["created_at"],
            )
        )
    return out


# ---- channels (WB-072) --------------------------------------------------

def get_channel_session(channel: str, chat_id: str) -> Optional[dict]:
    """某渠道某 chat 已绑定的会话行（含 session_id / owner_id），未绑定则 None。"""
    row = get_conn().execute(
        "SELECT * FROM channel_sessions WHERE channel=? AND chat_id=?",
        (channel, str(chat_id)),
    ).fetchone()
    return dict(row) if row else None


def first_channel_binding(channel: str) -> Optional[dict]:
    """该渠道最早的一条绑定（单主人策略下即「已配对的主人」），无则 None。"""
    row = get_conn().execute(
        "SELECT * FROM channel_sessions WHERE channel=? ORDER BY created_at ASC LIMIT 1",
        (channel,),
    ).fetchone()
    return dict(row) if row else None


def clear_channel_bindings(channel: str) -> None:
    """解绑某渠道的所有 chat 绑定（WB-077 解绑/重新配对）。会话本身不动。"""
    get_conn().execute("DELETE FROM channel_sessions WHERE channel=?", (channel,))
    get_conn().commit()


def bind_channel(channel: str, chat_id: str, session_id: str, owner_id: str) -> None:
    get_conn().execute(
        """INSERT OR REPLACE INTO channel_sessions (channel,chat_id,session_id,owner_id,created_at)
           VALUES (?,?,?,?,?)""",
        (channel, str(chat_id), session_id, owner_id, time.time()),
    )
    get_conn().commit()


def get_assistant_settings(owner_id: str) -> Optional[dict]:
    """助理设置行（WB-077），未设过则 None。含 bot_token（仅后端用，绝不回传前端）。"""
    row = get_conn().execute(
        "SELECT * FROM assistant_settings WHERE owner_id=?", (owner_id,)
    ).fetchone()
    return dict(row) if row else None


def upsert_assistant_settings(owner_id: str, **fields) -> dict:
    """部分字段合并写入（只覆盖显式传入的键；None 值也会被忽略以免抹掉已有配置）。
    合法字段：bot_token / name / persona / model / enabled。"""
    allowed = ("bot_token", "name", "persona", "model", "enabled")
    cur = get_assistant_settings(owner_id) or {}
    merged = {k: cur.get(k) for k in allowed}
    for k, v in fields.items():
        if k in allowed and v is not None:
            merged[k] = v
    get_conn().execute(
        """INSERT OR REPLACE INTO assistant_settings
           (owner_id, bot_token, name, persona, model, enabled, updated_at)
           VALUES (?,?,?,?,?,?,?)""",
        (owner_id, merged["bot_token"], merged["name"], merged["persona"],
         merged["model"], merged["enabled"], time.time()),
    )
    get_conn().commit()
    return get_assistant_settings(owner_id) or {}


def get_channel_offset(channel: str) -> Optional[int]:
    row = get_conn().execute(
        "SELECT update_offset FROM channel_state WHERE channel=?", (channel,)
    ).fetchone()
    return int(row["update_offset"]) if row else None


def set_channel_offset(channel: str, offset: int) -> None:
    get_conn().execute(
        "INSERT OR REPLACE INTO channel_state (channel,update_offset,updated_at) VALUES (?,?,?)",
        (channel, int(offset), time.time()),
    )
    get_conn().commit()


# ---- custom models (WB-124) --------------------------------------------

def _row_to_custom_model(row: sqlite3.Row, *, include_secrets: bool) -> dict:
    """DB 行 → dict。默认脱敏：剔除 api_key 明文，只暴露 has_key 布尔（铁律#4）。"""
    d = dict(row)
    key = d.pop("api_key", None)
    if include_secrets:
        d["api_key"] = key
    else:
        d["has_key"] = bool(key)
    d["group"] = "custom"
    return d


def list_custom_models(owner_id: str, *, include_secrets: bool = False) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM custom_models WHERE owner_id=? ORDER BY sort, created_at",
        (owner_id,),
    ).fetchall()
    return [_row_to_custom_model(r, include_secrets=include_secrets) for r in rows]


def get_custom_model(id: str, owner_id: str, *, include_secrets: bool = False) -> Optional[dict]:
    row = get_conn().execute(
        "SELECT * FROM custom_models WHERE id=? AND owner_id=?", (id, owner_id)
    ).fetchone()
    return _row_to_custom_model(row, include_secrets=include_secrets) if row else None


def get_custom_model_by_name(owner_id: str, name: str, *, include_secrets: bool = False) -> Optional[dict]:
    """按显示名查（picker 选择键即 name）——用于运行时把选择解析成真实 base/key/model。"""
    row = get_conn().execute(
        "SELECT * FROM custom_models WHERE owner_id=? AND name=?", (owner_id, name)
    ).fetchone()
    return _row_to_custom_model(row, include_secrets=include_secrets) if row else None


def create_custom_model(
    owner_id: str, *, name: str, model_id: str,
    api_base: str | None = None, api_key: str | None = None,
    icon: str = "🧩", color: str = "", mult: str = "",
) -> dict:
    cid = new_uuid()
    now = time.time()
    # sort = 追加到末尾
    row = get_conn().execute(
        "SELECT COALESCE(MAX(sort), -1) + 1 AS n FROM custom_models WHERE owner_id=?",
        (owner_id,),
    ).fetchone()
    sort = int(row["n"]) if row else 0
    get_conn().execute(
        """INSERT INTO custom_models
           (id, owner_id, name, model_id, api_base, api_key, icon, color, mult, sort, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (cid, owner_id, name, model_id, api_base or None, api_key or None,
         icon or "🧩", color or "", mult or "", sort, now, now),
    )
    get_conn().commit()
    return get_custom_model(cid, owner_id) or {}


def update_custom_model(id: str, owner_id: str, **fields) -> Optional[dict]:
    """部分字段更新。api_key 特殊：None/缺省 = 保持不变；空串 '' = 清空（切回默认凭据）。
    合法字段：name/model_id/api_base/icon/color/mult/api_key。"""
    cur = get_conn().execute(
        "SELECT * FROM custom_models WHERE id=? AND owner_id=?", (id, owner_id)
    ).fetchone()
    if not cur:
        return None
    merged = dict(cur)
    for k in ("name", "model_id", "api_base", "icon", "color", "mult"):
        if fields.get(k) is not None:
            merged[k] = fields[k]
    if "api_key" in fields and fields["api_key"] is not None:
        # 空串 = 显式清空；非空 = 覆盖。省略/None = 保持原 key（不覆盖）。
        merged["api_key"] = fields["api_key"] or None
    get_conn().execute(
        """UPDATE custom_models
           SET name=?, model_id=?, api_base=?, api_key=?, icon=?, color=?, mult=?, updated_at=?
           WHERE id=? AND owner_id=?""",
        (merged["name"], merged["model_id"], merged["api_base"], merged["api_key"],
         merged["icon"], merged["color"], merged["mult"], time.time(), id, owner_id),
    )
    get_conn().commit()
    return get_custom_model(id, owner_id)


def delete_custom_model(id: str, owner_id: str) -> bool:
    cur = get_conn().execute(
        "DELETE FROM custom_models WHERE id=? AND owner_id=?", (id, owner_id)
    )
    get_conn().commit()
    return cur.rowcount > 0


def list_hidden_builtins(owner_id: str) -> list[str]:
    rows = get_conn().execute(
        "SELECT name FROM hidden_builtin_models WHERE owner_id=?", (owner_id,)
    ).fetchall()
    return [r["name"] for r in rows]


def set_builtin_hidden(owner_id: str, name: str, hidden: bool) -> None:
    if hidden:
        get_conn().execute(
            "INSERT OR IGNORE INTO hidden_builtin_models (owner_id, name) VALUES (?,?)",
            (owner_id, name),
        )
    else:
        get_conn().execute(
            "DELETE FROM hidden_builtin_models WHERE owner_id=? AND name=?",
            (owner_id, name),
        )
    get_conn().commit()


# ---- per-owner settings KV (WB-136) ------------------------------------

def get_user_setting(owner_id: str, key: str) -> Optional[str]:
    row = get_conn().execute(
        "SELECT value FROM user_settings WHERE owner_id=? AND key=?", (owner_id, key)
    ).fetchone()
    return row["value"] if row else None


def set_user_setting(owner_id: str, key: str, value: Optional[str]) -> None:
    """写/覆盖一条设置；value 为 None/空串 = 删除该键（回到「未设置」）。"""
    if value:
        get_conn().execute(
            """INSERT OR REPLACE INTO user_settings (owner_id, key, value, updated_at)
               VALUES (?,?,?,?)""",
            (owner_id, key, value, time.time()),
        )
    else:
        get_conn().execute(
            "DELETE FROM user_settings WHERE owner_id=? AND key=?", (owner_id, key)
        )
    get_conn().commit()


_DEFAULT_MODEL_KEY = "default_model"


# ---- 安全审计日志（WB-152）----------------------------------------------

_AUDIT_MAX = 500  # 每个 owner 保留的审计条数（超出裁旧）


def add_audit(owner_id: str, tool: str, detail: str, action: str = "executed") -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO audit_log (id, owner_id, tool, detail, action, created_at) VALUES (?,?,?,?,?,?)",
        (new_uuid(), owner_id, tool, (detail or "")[:500], action, time.time()),
    )
    # 裁旧：只保留最近 _AUDIT_MAX 条
    conn.execute(
        """DELETE FROM audit_log WHERE owner_id=? AND id NOT IN (
               SELECT id FROM audit_log WHERE owner_id=? ORDER BY created_at DESC LIMIT ?
           )""",
        (owner_id, owner_id, _AUDIT_MAX),
    )
    conn.commit()


def list_audit(owner_id: str, limit: int = 100) -> list[dict]:
    rows = get_conn().execute(
        "SELECT id, tool, detail, action, created_at FROM audit_log WHERE owner_id=? ORDER BY created_at DESC LIMIT ?",
        (owner_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def clear_audit(owner_id: str) -> int:
    cur = get_conn().execute("DELETE FROM audit_log WHERE owner_id=?", (owner_id,))
    get_conn().commit()
    return cur.rowcount


# ---- 用户记忆（WB-148；认知记忆 WB-166：强度/衰减/软状态）------------------

_MEMORY_MAX = 200  # 单 owner 列举/注入默认上限（软上限；不再硬删最旧，弱记忆改由 decay_gc 软归档）
# 记忆标量列（不含 embedding BLOB），供列表/详情/注入读取。
_MEM_COLS = (
    "id, content, source, created_at, importance, usage_count, "
    "status, superseded_by, last_used_at"
)


def _mem_dict(r) -> dict:
    """sqlite Row → dict（标量字段，不含 embedding BLOB）。"""
    return {
        "id": r["id"], "content": r["content"], "source": r["source"],
        "created_at": r["created_at"], "importance": r["importance"],
        "usage_count": r["usage_count"], "status": r["status"],
        "superseded_by": r["superseded_by"], "last_used_at": r["last_used_at"],
    }


def list_memories(owner_id: str, limit: int = _MEMORY_MAX, status: Optional[str] = "active") -> list[dict]:
    """列记忆（默认仅 active；status=None 则不限状态）。按 created_at DESC。"""
    conn = get_conn()
    if status is None:
        rows = conn.execute(
            f"SELECT {_MEM_COLS} FROM user_memories WHERE owner_id=? ORDER BY created_at DESC LIMIT ?",
            (owner_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT {_MEM_COLS} FROM user_memories WHERE owner_id=? AND status=? "
            "ORDER BY created_at DESC LIMIT ?",
            (owner_id, status, limit),
        ).fetchall()
    return [_mem_dict(r) for r in rows]


def get_memory(owner_id: str, mem_id: str) -> Optional[dict]:
    r = get_conn().execute(
        f"SELECT {_MEM_COLS} FROM user_memories WHERE owner_id=? AND id=?",
        (owner_id, mem_id),
    ).fetchone()
    return _mem_dict(r) if r else None


def count_memories(owner_id: str, status: Optional[str] = "active") -> int:
    if status is None:
        return get_conn().execute(
            "SELECT COUNT(*) FROM user_memories WHERE owner_id=?", (owner_id,)
        ).fetchone()[0]
    return get_conn().execute(
        "SELECT COUNT(*) FROM user_memories WHERE owner_id=? AND status=?", (owner_id, status)
    ).fetchone()[0]


def owner_data_counts(owner_id: str) -> dict:
    """会话数 + 消息数，各一条 COUNT 查询（WB-149 数据摘要，避免 N+1 拉全部消息只为计数）。"""
    conn = get_conn()
    sessions = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE owner_id=?", (owner_id,)
    ).fetchone()[0]
    messages = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE session_id IN (SELECT id FROM sessions WHERE owner_id=?)",
        (owner_id,),
    ).fetchone()[0]
    return {"sessions": sessions, "messages": messages}


def add_memory(owner_id: str, content: str, source: str = "manual",
               importance: float = 0.5) -> Optional[dict]:
    """加一条 active 记忆；空内容、或与现有【active】记忆精确重复（忽略大小写/首尾空白）则跳过、返回 None。
    WB-166：不再硬删最旧（弱记忆改由 decay_gc 软归档）。语义去重/更替见 memory.store_memory（档二）。"""
    text = (content or "").strip()
    if not text:
        return None
    if find_active_memory_by_content(owner_id, text) is not None:
        return None
    return insert_memory(owner_id, text, source, importance)


def insert_memory(owner_id: str, content: str, source: str, importance: float = 0.5,
                  *, embedding: Optional[bytes] = None, embedding_model: Optional[str] = None,
                  now: Optional[float] = None) -> dict:
    """无条件插入一条 active 记忆（不去重；去重由调用方决定）。返回标量 dict。"""
    text = (content or "").strip()
    mem_id = new_uuid()
    ts = now if now is not None else time.time()
    get_conn().execute(
        "INSERT INTO user_memories (id, owner_id, content, source, created_at, "
        "importance, usage_count, status, superseded_by, last_used_at, embedding, embedding_model) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (mem_id, owner_id, text, source, ts, importance, 0, "active", None, ts, embedding, embedding_model),
    )
    get_conn().commit()
    return {"id": mem_id, "content": text, "source": source, "created_at": ts,
            "importance": importance, "usage_count": 0, "status": "active",
            "superseded_by": None, "last_used_at": ts}


def find_active_memory_by_content(owner_id: str, content: str) -> Optional[dict]:
    """在 active 记忆里按归一化内容找完全重复的一条（忽略大小写/首尾空白）；无则 None。"""
    norm = (content or "").strip().casefold()
    if not norm:
        return None
    rows = get_conn().execute(
        f"SELECT {_MEM_COLS} FROM user_memories WHERE owner_id=? AND status='active'",
        (owner_id,),
    ).fetchall()
    for r in rows:
        if (r["content"] or "").strip().casefold() == norm:
            return _mem_dict(r)
    return None


def reinforce_memory(owner_id: str, mem_id: str, now: Optional[float] = None) -> Optional[dict]:
    """命中强化：usage_count++、last_used_at=now。返回更新后标量 dict（不存在则 None）。"""
    ts = now if now is not None else time.time()
    cur = get_conn().execute(
        "UPDATE user_memories SET usage_count = usage_count + 1, last_used_at=? "
        "WHERE owner_id=? AND id=?",
        (ts, owner_id, mem_id),
    )
    get_conn().commit()
    return get_memory(owner_id, mem_id) if cur.rowcount else None


def supersede_memory(owner_id: str, old_id: str, new_id: str) -> bool:
    """把旧记忆置 superseded 并记取代它的新记忆 id（软状态，不硬删，可回滚）。"""
    cur = get_conn().execute(
        "UPDATE user_memories SET status='superseded', superseded_by=? "
        "WHERE owner_id=? AND id=? AND status='active'",
        (new_id, owner_id, old_id),
    )
    get_conn().commit()
    return cur.rowcount > 0


def find_superseded_by(owner_id: str, new_id: str) -> Optional[dict]:
    """找被 new_id 取代的那条旧记忆（superseded_by=new_id）；无则 None。溯源链用。"""
    r = get_conn().execute(
        f"SELECT {_MEM_COLS} FROM user_memories WHERE owner_id=? AND superseded_by=?",
        (owner_id, new_id),
    ).fetchone()
    return _mem_dict(r) if r else None


def set_memory_status(owner_id: str, mem_id: str, status: str) -> Optional[dict]:
    """改状态（archive: active→archived；rollback: archived/superseded→active，回滚时清 superseded_by 链）。"""
    conn = get_conn()
    if status == "active":
        conn.execute(
            "UPDATE user_memories SET status='active', superseded_by=NULL WHERE owner_id=? AND id=?",
            (owner_id, mem_id),
        )
    else:
        conn.execute(
            "UPDATE user_memories SET status=? WHERE owner_id=? AND id=?", (status, owner_id, mem_id),
        )
    conn.commit()
    return get_memory(owner_id, mem_id)


def set_memory_importance(owner_id: str, mem_id: str, importance: float) -> Optional[dict]:
    imp = min(1.0, max(0.0, float(importance)))
    cur = get_conn().execute(
        "UPDATE user_memories SET importance=? WHERE owner_id=? AND id=?", (imp, owner_id, mem_id),
    )
    get_conn().commit()
    return get_memory(owner_id, mem_id) if cur.rowcount else None


def list_active_with_embedding(owner_id: str) -> list[dict]:
    """内部用：active 记忆连 embedding 原始 bytes + embedding_model tag 一起返回（语义检索/去重）。"""
    rows = get_conn().execute(
        f"SELECT {_MEM_COLS}, embedding, embedding_model FROM user_memories "
        "WHERE owner_id=? AND status='active'",
        (owner_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = _mem_dict(r)
        d["embedding"] = r["embedding"]              # bytes | None
        d["embedding_model"] = r["embedding_model"]  # str | None
        out.append(d)
    return out


def set_memory_embedding(owner_id: str, mem_id: str, embedding: Optional[bytes],
                         embedding_model: Optional[str] = None) -> None:
    get_conn().execute(
        "UPDATE user_memories SET embedding=?, embedding_model=? WHERE owner_id=? AND id=?",
        (embedding, embedding_model, owner_id, mem_id),
    )
    get_conn().commit()


def update_memory(owner_id: str, mem_id: str, content: str) -> Optional[dict]:
    """原地更替一条记忆的内容（保留 id/source/created_at/强度等）。WB-162 手动编辑复用。
    空内容、记忆不存在、或更成与【其他 active 记忆】重复（忽略大小写/首尾空白）则不改、返回 None。"""
    text = (content or "").strip()
    if not text:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM user_memories WHERE owner_id=? AND id=?", (owner_id, mem_id),
    ).fetchone()
    if row is None:
        return None
    norm = text.casefold()
    others = conn.execute(
        "SELECT content FROM user_memories WHERE owner_id=? AND id<>? AND status='active'",
        (owner_id, mem_id),
    ).fetchall()
    if any((r["content"] or "").strip().casefold() == norm for r in others):
        return None
    conn.execute("UPDATE user_memories SET content=? WHERE owner_id=? AND id=?", (text, owner_id, mem_id))
    conn.commit()
    return get_memory(owner_id, mem_id)


def delete_memory(owner_id: str, mem_id: str) -> bool:
    cur = get_conn().execute(
        "DELETE FROM user_memories WHERE owner_id=? AND id=?", (owner_id, mem_id)
    )
    get_conn().commit()
    return cur.rowcount > 0


def clear_memories(owner_id: str) -> int:
    cur = get_conn().execute("DELETE FROM user_memories WHERE owner_id=?", (owner_id,))
    get_conn().commit()
    return cur.rowcount


def get_default_model(owner_id: str) -> str:
    """未显式选模型时跟随的默认模型 ref（WB-136）。'' = 未设置。取代 .env LLM_MODEL。"""
    return get_user_setting(owner_id, _DEFAULT_MODEL_KEY) or ""


def set_default_model(owner_id: str, model_ref: str) -> None:
    """设/清默认模型 ref（''=清除）。ref = 选择键：@provider:model 或自定义名。"""
    set_user_setting(owner_id, _DEFAULT_MODEL_KEY, (model_ref or "").strip() or None)


# ---- WeKnora 知识库连接配置（WB-188）------------------------------------
#
# 从「只能改 backend/.env + 重启」改为按 owner 入库，运行时 DB 优先、.env 兜底
# （解析在 agent/weknora.py，本层只管存取）。刻意复用既有两张表，不新建表：
# - api_key → provider_keys：项目指定的密钥存放处。set_provider_key 已有「空串=撤销」，
#   list_provider_keys 只回 id 集合 —— 天然满足「只写不回读」（同厂商 Key）。不放通用 KV
#   user_settings，免得将来有人加「KV 整表导出」把密钥带出去。
# - url / embedding_model_id（非密钥）→ user_settings KV。

WEKNORA_PROVIDER = "weknora"
_WEKNORA_URL_KEY = "weknora_url"
_WEKNORA_EMBED_KEY = "weknora_embedding_model_id"

# 「不传 = 不改」与「传空串 = 清除」的区分（照 WB-124 自定义模型 PATCH 的语义）。
_KEEP = object()


def get_weknora_conf(owner_id: str) -> dict[str, str]:
    """本 owner 存在 DB 里的 WeKnora 配置。未设过的字段 = ''（由调用方回退 .env）。
    含明文 api_key —— 仅后端用，绝不回前端。"""
    return {
        "url": get_user_setting(owner_id, _WEKNORA_URL_KEY) or "",
        "api_key": get_provider_key(owner_id, WEKNORA_PROVIDER) or "",
        "embedding_model_id": get_user_setting(owner_id, _WEKNORA_EMBED_KEY) or "",
    }


def set_weknora_conf(
    owner_id: str,
    url: Any = _KEEP,
    api_key: Any = _KEEP,
    embedding_model_id: Any = _KEEP,
) -> None:
    """写 WeKnora 配置。每个字段：不传 = 不改；'' = 清除该字段（回退 .env/默认）；非空 = 覆盖。"""
    if url is not _KEEP:
        set_user_setting(owner_id, _WEKNORA_URL_KEY, (url or "").strip().rstrip("/") or None)
    if api_key is not _KEEP:
        set_provider_key(owner_id, WEKNORA_PROVIDER, (api_key or "").strip())
    if embedding_model_id is not _KEEP:
        set_user_setting(owner_id, _WEKNORA_EMBED_KEY, (embedding_model_id or "").strip() or None)


# ---- provider keys + model overrides (WB-128) --------------------------

def get_provider_key(owner_id: str, provider_id: str) -> Optional[str]:
    """某厂商的 API key（仅后端用，绝不回前端）。未设过则 None。"""
    row = get_conn().execute(
        "SELECT api_key FROM provider_keys WHERE owner_id=? AND provider_id=?",
        (owner_id, provider_id),
    ).fetchone()
    return row["api_key"] if row else None


def list_provider_keys(owner_id: str) -> set[str]:
    """已配置 key 的厂商 id 集合（脱敏——只给「有没有」）。"""
    rows = get_conn().execute(
        "SELECT provider_id FROM provider_keys WHERE owner_id=?", (owner_id,)
    ).fetchall()
    return {r["provider_id"] for r in rows}


def set_provider_key(owner_id: str, provider_id: str, api_key: str) -> None:
    """写/覆盖厂商 key；空串 = 删除（撤销该厂商）。"""
    if api_key:
        get_conn().execute(
            """INSERT OR REPLACE INTO provider_keys (owner_id, provider_id, api_key, updated_at)
               VALUES (?,?,?,?)""",
            (owner_id, provider_id, api_key, time.time()),
        )
    else:
        get_conn().execute(
            "DELETE FROM provider_keys WHERE owner_id=? AND provider_id=?",
            (owner_id, provider_id),
        )
    get_conn().commit()


# ---- model meta: capabilities + cost (WB-132) --------------------------

def _row_to_model_meta(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["capabilities"] = json.loads(d.get("capabilities") or "[]")
    return d


_META_COLS = "capabilities, input_cost, input_cost_cached, output_cost, context_window, currency, note"


def get_model_meta(owner_id: str, model_ref: str) -> Optional[dict]:
    row = get_conn().execute(
        f"SELECT {_META_COLS} FROM model_meta WHERE owner_id=? AND model_ref=?",
        (owner_id, model_ref),
    ).fetchone()
    return _row_to_model_meta(row) if row else None


def list_model_meta(owner_id: str) -> dict[str, dict]:
    """本 owner 所有已存 meta，键为 model_ref（GET 批量附上用）。"""
    rows = get_conn().execute(
        f"SELECT model_ref, {_META_COLS} FROM model_meta WHERE owner_id=?",
        (owner_id,),
    ).fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        d = _row_to_model_meta(r)
        out[d.pop("model_ref")] = d
    return out


def set_model_meta(owner_id: str, model_ref: str, *, capabilities: list[str],
                   input_cost: float | None, input_cost_cached: float | None,
                   output_cost: float | None, context_window: int | None,
                   currency: str | None, note: str | None) -> dict:
    get_conn().execute(
        """INSERT OR REPLACE INTO model_meta
           (owner_id, model_ref, capabilities, input_cost, input_cost_cached, output_cost,
            context_window, currency, note, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (owner_id, model_ref, json.dumps(capabilities), input_cost, input_cost_cached,
         output_cost, context_window, currency, note, time.time()),
    )
    get_conn().commit()
    return get_model_meta(owner_id, model_ref) or {}


def delete_model_meta(owner_id: str, model_ref: str) -> None:
    """清除覆盖，回到启发式默认。"""
    get_conn().execute(
        "DELETE FROM model_meta WHERE owner_id=? AND model_ref=?", (owner_id, model_ref)
    )
    get_conn().commit()


def get_provider_config(owner_id: str, provider_id: str) -> Optional[dict]:
    """base_url/chat_path 覆盖（WB-129）。未设过则 None。"""
    row = get_conn().execute(
        "SELECT base_url, chat_path FROM provider_config WHERE owner_id=? AND provider_id=?",
        (owner_id, provider_id),
    ).fetchone()
    return {"base_url": row["base_url"], "chat_path": row["chat_path"]} if row else None


def set_provider_config(owner_id: str, provider_id: str, base_url: str | None, chat_path: str | None) -> None:
    """写/清 base_url·chat_path 覆盖。两者都空 = 删行（恢复预置默认）。空串按 None 存。"""
    base_url = (base_url or "").strip() or None
    chat_path = (chat_path or "").strip() or None
    if base_url is None and chat_path is None:
        get_conn().execute(
            "DELETE FROM provider_config WHERE owner_id=? AND provider_id=?",
            (owner_id, provider_id),
        )
    else:
        get_conn().execute(
            """INSERT OR REPLACE INTO provider_config (owner_id, provider_id, base_url, chat_path, updated_at)
               VALUES (?,?,?,?,?)""",
            (owner_id, provider_id, base_url, chat_path, time.time()),
        )
    get_conn().commit()


def list_provider_model_overrides(owner_id: str, provider_id: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT model_id, hidden FROM provider_models WHERE owner_id=? AND provider_id=?",
        (owner_id, provider_id),
    ).fetchall()
    return [{"model_id": r["model_id"], "hidden": bool(r["hidden"])} for r in rows]


def add_provider_model(owner_id: str, provider_id: str, model_id: str) -> None:
    """新增一个厂商模型名（hidden=0）；若同名已存在则取消其隐藏。"""
    get_conn().execute(
        """INSERT INTO provider_models (owner_id, provider_id, model_id, hidden, created_at)
           VALUES (?,?,?,0,?)
           ON CONFLICT(owner_id, provider_id, model_id) DO UPDATE SET hidden=0""",
        (owner_id, provider_id, model_id, time.time()),
    )
    get_conn().commit()


def set_provider_model_hidden(owner_id: str, provider_id: str, model_id: str, hidden: bool) -> None:
    """隐藏/恢复某厂商模型。恢复一个「用户新增」的模型即删除其行（回到无覆盖态由调用方决定，这里统一 upsert）。"""
    get_conn().execute(
        """INSERT INTO provider_models (owner_id, provider_id, model_id, hidden, created_at)
           VALUES (?,?,?,?,?)
           ON CONFLICT(owner_id, provider_id, model_id) DO UPDATE SET hidden=excluded.hidden""",
        (owner_id, provider_id, model_id, 1 if hidden else 0, time.time()),
    )
    get_conn().commit()


def remove_provider_model(owner_id: str, provider_id: str, model_id: str) -> None:
    """彻底删除一条模型覆盖行（用于删掉「用户新增」的模型名）。"""
    get_conn().execute(
        "DELETE FROM provider_models WHERE owner_id=? AND provider_id=? AND model_id=?",
        (owner_id, provider_id, model_id),
    )
    get_conn().commit()


# ---- assistants + channels (WB-086/087) --------------------------------

_ASSIST_LOADOUT = ("experts", "skills", "connectors")


def _row_to_assistant(row: sqlite3.Row) -> dict:
    d = dict(row)
    for k in _ASSIST_LOADOUT:
        d[k] = json.loads(d.get(k) or "[]")
    d["enabled"] = bool(d.get("enabled"))
    return d


def create_assistant(
    *, owner_id: str, name: str, avatar: Optional[str] = None, instruction: Optional[str] = None,
    model: Optional[str] = None, mode: str = "exec", workspace: str = "default",
    experts: Optional[list] = None, skills: Optional[list] = None, connectors: Optional[list] = None,
    enabled: bool = True, session_id: Optional[str] = None,
) -> dict:
    now = time.time()
    aid = new_uuid()
    get_conn().execute(
        """INSERT INTO assistants
           (id,owner_id,name,avatar,instruction,model,mode,workspace,experts,skills,connectors,enabled,session_id,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (aid, owner_id, name[:60], avatar, instruction, model, mode, workspace,
         json.dumps(experts or []), json.dumps(skills or []), json.dumps(connectors or []),
         1 if enabled else 0, session_id, now, now),
    )
    get_conn().commit()
    return get_assistant(aid)  # type: ignore[return-value]


def get_assistant(assistant_id: str) -> Optional[dict]:
    row = get_conn().execute("SELECT * FROM assistants WHERE id=?", (assistant_id,)).fetchone()
    return _row_to_assistant(row) if row else None


def list_assistants(owner_id: Optional[str] = None) -> list[dict]:
    if owner_id is not None:
        rows = get_conn().execute(
            "SELECT * FROM assistants WHERE owner_id=? ORDER BY created_at", (owner_id,)
        ).fetchall()
    else:
        rows = get_conn().execute("SELECT * FROM assistants ORDER BY created_at").fetchall()
    return [_row_to_assistant(r) for r in rows]


def update_assistant(assistant_id: str, **patch) -> Optional[dict]:
    allowed = ("name", "avatar", "instruction", "model", "mode", "workspace",
               "experts", "skills", "connectors", "enabled", "session_id")
    if get_assistant(assistant_id) is None:
        return None
    sets, vals = [], []
    for k, v in patch.items():
        if k not in allowed or v is None:
            continue
        if k in _ASSIST_LOADOUT:
            v = json.dumps(v)
        elif k == "enabled":
            v = 1 if v else 0
        sets.append(f"{k}=?")
        vals.append(v)
    if sets:
        sets.append("updated_at=?")
        vals.append(time.time())
        vals.append(assistant_id)
        get_conn().execute(f"UPDATE assistants SET {','.join(sets)} WHERE id=?", vals)
        get_conn().commit()
    return get_assistant(assistant_id)


def delete_assistant(assistant_id: str) -> None:
    # 连带删其渠道与 chat 绑定；会话/transcript 保留（便于回看历史）。
    conn = get_conn()
    for ch in list_channels(assistant_id):
        conn.execute("DELETE FROM channel_chat_sessions WHERE channel_id=?", (ch["id"],))
    conn.execute("DELETE FROM channels WHERE assistant_id=?", (assistant_id,))
    conn.execute("DELETE FROM assistants WHERE id=?", (assistant_id,))
    conn.commit()


def _row_to_channel(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["config"] = json.loads(d.get("config") or "{}")
    d["enabled"] = bool(d.get("enabled"))
    return d


def create_channel(*, assistant_id: str, type: str, config: Optional[dict] = None, enabled: bool = True) -> dict:
    cid = new_uuid()
    get_conn().execute(
        "INSERT INTO channels (id,assistant_id,type,config,enabled,update_offset,created_at) VALUES (?,?,?,?,?,0,?)",
        (cid, assistant_id, type, json.dumps(config or {}), 1 if enabled else 0, time.time()),
    )
    get_conn().commit()
    return get_channel(cid)  # type: ignore[return-value]


def get_channel(channel_id: str) -> Optional[dict]:
    row = get_conn().execute("SELECT * FROM channels WHERE id=?", (channel_id,)).fetchone()
    return _row_to_channel(row) if row else None


def list_channels(assistant_id: str) -> list[dict]:
    rows = get_conn().execute(
        "SELECT * FROM channels WHERE assistant_id=? ORDER BY created_at", (assistant_id,)
    ).fetchall()
    return [_row_to_channel(r) for r in rows]


def list_all_channels() -> list[dict]:
    return [_row_to_channel(r) for r in get_conn().execute("SELECT * FROM channels ORDER BY created_at").fetchall()]


def update_channel(channel_id: str, *, config: Optional[dict] = None, enabled: Optional[bool] = None) -> Optional[dict]:
    cur = get_channel(channel_id)
    if cur is None:
        return None
    sets, vals = [], []
    if config is not None:
        merged = {**cur["config"], **config}  # 合并，避免只改 enabled 时抹掉 token
        sets.append("config=?")
        vals.append(json.dumps(merged))
    if enabled is not None:
        sets.append("enabled=?")
        vals.append(1 if enabled else 0)
    if sets:
        vals.append(channel_id)
        get_conn().execute(f"UPDATE channels SET {','.join(sets)} WHERE id=?", vals)
        get_conn().commit()
    return get_channel(channel_id)


def delete_channel(channel_id: str) -> None:
    conn = get_conn()
    conn.execute("DELETE FROM channel_chat_sessions WHERE channel_id=?", (channel_id,))
    conn.execute("DELETE FROM channels WHERE id=?", (channel_id,))
    conn.commit()


def set_channel_update_offset(channel_id: str, offset: int) -> None:
    get_conn().execute("UPDATE channels SET update_offset=? WHERE id=?", (int(offset), channel_id))
    get_conn().commit()


def get_chat_session(channel_id: str, chat_id: str) -> Optional[dict]:
    row = get_conn().execute(
        "SELECT * FROM channel_chat_sessions WHERE channel_id=? AND chat_id=?", (channel_id, str(chat_id))
    ).fetchone()
    return dict(row) if row else None


def first_chat_binding(channel_id: str) -> Optional[dict]:
    row = get_conn().execute(
        "SELECT * FROM channel_chat_sessions WHERE channel_id=? ORDER BY created_at LIMIT 1", (channel_id,)
    ).fetchone()
    return dict(row) if row else None


def bind_chat(channel_id: str, chat_id: str, session_id: str, owner_id: str) -> None:
    get_conn().execute(
        "INSERT OR REPLACE INTO channel_chat_sessions (channel_id,chat_id,session_id,owner_id,created_at) VALUES (?,?,?,?,?)",
        (channel_id, str(chat_id), session_id, owner_id, time.time()),
    )
    get_conn().commit()


def clear_channel_chats(channel_id: str) -> None:
    get_conn().execute("DELETE FROM channel_chat_sessions WHERE channel_id=?", (channel_id,))
    get_conn().commit()


def _migrate_assistants() -> None:
    """WB-087 §6：把 WB-077 单助理（assistant_settings + channel_sessions）非破坏迁移为
    一条默认助理 + 一条 Telegram 渠道。仅当 assistants 为空且检测到旧配置/凭据时执行一次。"""
    conn = get_conn()
    if conn.execute("SELECT 1 FROM assistants LIMIT 1").fetchone():
        return  # 已有助理 → 迁移过或用户已新建，跳过
    old_row = conn.execute(
        "SELECT * FROM assistant_settings WHERE owner_id=?", (LOCAL_USER_ID,)
    ).fetchone()
    old = dict(old_row) if old_row else {}
    token = (old.get("bot_token") or "").strip() or settings.TELEGRAM_BOT_TOKEN
    if not token and not old:
        return  # 全新用户、无任何旧配置/凭据 → 不建默认助理（零变化，用户自己新建）
    sess = conn.execute(
        "SELECT id FROM sessions WHERE owner_id=? AND kind='assistant' ORDER BY created_at LIMIT 1",
        (LOCAL_USER_ID,),
    ).fetchone()
    enabled = old.get("enabled")
    enabled = bool(enabled) if enabled is not None else settings.TELEGRAM_ASSISTANT
    a = create_assistant(
        owner_id=LOCAL_USER_ID,
        name=(old.get("name") or "").strip() or "AgentMate 助理",
        instruction=(old.get("persona") or "").strip() or None,
        model=(old.get("model") or "").strip() or None,
        session_id=sess["id"] if sess else None,
    )
    ch = create_channel(
        assistant_id=a["id"], type="telegram",
        config={"bot_token": token, "chat_id": settings.TELEGRAM_CHAT_ID.strip()},
        enabled=bool(token) and enabled,
    )
    for r in conn.execute("SELECT * FROM channel_sessions WHERE channel='telegram'").fetchall():
        r = dict(r)
        conn.execute(
            "INSERT OR REPLACE INTO channel_chat_sessions (channel_id,chat_id,session_id,owner_id,created_at) VALUES (?,?,?,?,?)",
            (ch["id"], r["chat_id"], r["session_id"], r["owner_id"], r["created_at"]),
        )
    off = conn.execute("SELECT update_offset FROM channel_state WHERE channel='telegram'").fetchone()
    if off:
        conn.execute("UPDATE channels SET update_offset=? WHERE id=?", (int(off["update_offset"]), ch["id"]))
    conn.commit()


# ---- automations --------------------------------------------------------

def compute_next_run(kind: str, interval_min: int, at_time: str, now: float) -> float:
    """Next fire time (epoch seconds) for a trigger, relative to `now`.

    interval → now + N minutes. daily → the next local HH:MM strictly after now.
    """
    if kind == "daily":
        try:
            hh, mm = (int(x) for x in at_time.split(":", 1))
        except (ValueError, AttributeError):
            hh, mm = 9, 0
        base = _dt.datetime.fromtimestamp(now)
        target = base.replace(hour=hh % 24, minute=mm % 60, second=0, microsecond=0)
        if target.timestamp() <= now:
            target += _dt.timedelta(days=1)
        return target.timestamp()
    # interval (default)
    return now + max(1, int(interval_min)) * 60


def _row_to_automation(r) -> Automation:
    return Automation(
        id=r["id"], owner_id=r["owner_id"], name=r["name"], prompt=r["prompt"],
        trigger_kind=r["trigger_kind"], interval_min=r["interval_min"], at_time=r["at_time"],
        project_id=r["project_id"], model=r["model"], enabled=bool(r["enabled"]),
        created_at=r["created_at"], updated_at=r["updated_at"], next_run_at=r["next_run_at"],
        last_run_at=r["last_run_at"], last_session_id=r["last_session_id"], last_status=r["last_status"],
        timeout_sec=int(r["timeout_sec"]), max_attempts=int(r["max_attempts"]),
        retry_backoff_sec=int(r["retry_backoff_sec"]),
        max_total_tokens=int(r["max_total_tokens"]), notify_policy=r["notify_policy"],
        concurrency_policy=r["concurrency_policy"],
    )


def create_automation(
    *, owner_id: str, name: str, prompt: str, trigger_kind: str = "interval",
    interval_min: int = 60, at_time: str = "09:00",
    project_id: Optional[str] = None, model: Optional[str] = None, enabled: bool = True,
    timeout_sec: int = 300, max_attempts: int = 3, retry_backoff_sec: int = 30,
    max_total_tokens: int = 0, notify_policy: str = "failure,recovery",
    concurrency_policy: str = "skip",
) -> Automation:
    now = time.time()
    a = Automation(
        id=new_uuid(), owner_id=owner_id, name=name[:120], prompt=prompt,
        trigger_kind=trigger_kind, interval_min=interval_min, at_time=at_time,
        project_id=project_id, model=model, enabled=enabled,
        created_at=now, updated_at=now,
        next_run_at=compute_next_run(trigger_kind, interval_min, at_time, now),
        timeout_sec=timeout_sec, max_attempts=max_attempts,
        retry_backoff_sec=retry_backoff_sec, max_total_tokens=max_total_tokens,
        notify_policy=notify_policy, concurrency_policy=concurrency_policy,
    )
    get_conn().execute(
        """INSERT INTO automations
           (id,owner_id,name,prompt,trigger_kind,interval_min,at_time,project_id,model,
            enabled,timeout_sec,max_attempts,retry_backoff_sec,max_total_tokens,notify_policy,
            concurrency_policy,created_at,updated_at,next_run_at,last_run_at,last_session_id,last_status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (a.id, a.owner_id, a.name, a.prompt, a.trigger_kind, a.interval_min, a.at_time,
         a.project_id, a.model, int(a.enabled), a.timeout_sec, a.max_attempts,
         a.retry_backoff_sec, a.max_total_tokens, a.notify_policy, a.concurrency_policy,
         a.created_at, a.updated_at, a.next_run_at,
         a.last_run_at, a.last_session_id, a.last_status),
    )
    get_conn().commit()
    return a


def list_automations(owner_id: str) -> list[Automation]:
    rows = get_conn().execute(
        "SELECT * FROM automations WHERE owner_id=? ORDER BY created_at DESC", (owner_id,)
    ).fetchall()
    return [_row_to_automation(r) for r in rows]


def get_automation(auto_id: str, owner_id: Optional[str] = None) -> Optional[Automation]:
    if owner_id is not None:
        r = get_conn().execute(
            "SELECT * FROM automations WHERE id=? AND owner_id=?", (auto_id, owner_id)
        ).fetchone()
    else:
        r = get_conn().execute("SELECT * FROM automations WHERE id=?", (auto_id,)).fetchone()
    return _row_to_automation(r) if r else None


def list_due_automations(now: float) -> list[Automation]:
    rows = get_conn().execute(
        "SELECT * FROM automations WHERE enabled=1 AND next_run_at<=? ORDER BY next_run_at ASC",
        (now,),
    ).fetchall()
    return [_row_to_automation(r) for r in rows]


_AUTOMATION_FIELDS = {
    "name", "prompt", "trigger_kind", "interval_min", "at_time", "project_id", "model",
    "enabled", "timeout_sec", "max_attempts", "retry_backoff_sec", "max_total_tokens",
    "notify_policy", "concurrency_policy",
}
# Columns whose NULL is a real value ("clear it"), not "field not provided" — callers
# pass only fields the client set (exclude_unset), so None here means explicit clear
# (WB-037/038). The others must never be written NULL.
_AUTOMATION_NULLABLE = {"project_id", "model"}


def update_automation(auto_id: str, **fields: Any) -> Optional[Automation]:
    cur = get_automation(auto_id)
    if cur is None:
        return None
    sets, vals = [], []
    for k, v in fields.items():
        if k not in _AUTOMATION_FIELDS:
            continue
        if v is None and k not in _AUTOMATION_NULLABLE:
            continue
        sets.append(f"{k}=?")
        vals.append(int(v) if k == "enabled" else v)
    if not sets:
        return cur
    # Recompute next_run_at when the schedule changed or the task was re-enabled.
    merged = {**cur.to_dict(), **{k: v for k, v in fields.items() if v is not None}}
    trigger_touched = any(k in fields for k in ("trigger_kind", "interval_min", "at_time"))
    reenabled = fields.get("enabled") and not cur.enabled
    if trigger_touched or reenabled:
        nxt = compute_next_run(merged["trigger_kind"], merged["interval_min"], merged["at_time"], time.time())
        sets.append("next_run_at=?"); vals.append(nxt)
    sets.append("updated_at=?"); vals.append(time.time())
    vals.append(auto_id)
    get_conn().execute(f"UPDATE automations SET {', '.join(sets)} WHERE id=?", vals)
    get_conn().commit()
    return get_automation(auto_id)


def mark_automation_run(
    auto_id: str, *, next_run_at: Optional[float] = None, last_run_at: Optional[float] = None,
    last_session_id: Optional[str] = None, last_status: Optional[str] = None,
) -> None:
    sets, vals = [], []
    for col, val in (
        ("next_run_at", next_run_at), ("last_run_at", last_run_at),
        ("last_session_id", last_session_id), ("last_status", last_status),
    ):
        if val is not None:
            sets.append(f"{col}=?"); vals.append(val)
    if not sets:
        return
    vals.append(auto_id)
    get_conn().execute(f"UPDATE automations SET {', '.join(sets)} WHERE id=?", vals)
    get_conn().commit()


_FIRE_ACTIVE = {"queued", "running", "retry_wait"}
_FIRE_TERMINAL = {"succeeded", "dead_letter", "ignored"}


def _row_to_automation_fire(row: sqlite3.Row) -> AutomationFire:
    return AutomationFire(
        id=row["id"], automation_id=row["automation_id"], owner_id=row["owner_id"],
        fire_key=row["fire_key"], trigger_kind=row["trigger_kind"],
        planned_at=row["planned_at"], status=row["status"], attempt=int(row["attempt"]),
        max_attempts=int(row["max_attempts"]), session_id=row["session_id"],
        run_id=row["run_id"], retry_of_run_id=row["retry_of_run_id"],
        error_code=row["error_code"], error_message=row["error_message"],
        prompt_tokens=int(row["prompt_tokens"] or 0),
        completion_tokens=int(row["completion_tokens"] or 0),
        next_attempt_at=row["next_attempt_at"], notified=_load_json(row["notified"], []),
        created_at=row["created_at"], updated_at=row["updated_at"],
        finished_at=row["finished_at"],
    )


def create_automation_fire(
    *, automation_id: str, owner_id: str, fire_key: str, trigger_kind: str,
    planned_at: float, max_attempts: int, session_id: Optional[str] = None,
    retry_of_run_id: Optional[str] = None,
) -> tuple[AutomationFire, bool]:
    auto = get_automation(automation_id, owner_id)
    if auto is None:
        raise ValueError("automation scope mismatch")
    key = fire_key.strip()[:240]
    if not key:
        raise ValueError("fire_key is required")
    now = time.time()
    fire_id = new_uuid()
    try:
        get_conn().execute(
            """INSERT INTO automation_fires
               (id,automation_id,owner_id,fire_key,trigger_kind,planned_at,status,attempt,
                max_attempts,session_id,retry_of_run_id,next_attempt_at,created_at,updated_at)
               VALUES (?,?,?,?,?,?,'queued',0,?,?,?,?,?,?)""",
            (fire_id, automation_id, owner_id, key, trigger_kind, planned_at,
             max(1, int(max_attempts)), session_id, retry_of_run_id, planned_at, now, now),
        )
        get_conn().commit()
    except sqlite3.IntegrityError:
        row = get_conn().execute(
            "SELECT * FROM automation_fires WHERE automation_id=? AND fire_key=?",
            (automation_id, key),
        ).fetchone()
        if row:
            return _row_to_automation_fire(row), False
        raise
    return get_automation_fire(fire_id), True  # type: ignore[return-value]


def get_automation_fire(
    fire_id: str, owner_id: Optional[str] = None,
) -> Optional[AutomationFire]:
    if owner_id is None:
        row = get_conn().execute(
            "SELECT * FROM automation_fires WHERE id=?", (fire_id,)
        ).fetchone()
    else:
        row = get_conn().execute(
            "SELECT * FROM automation_fires WHERE id=? AND owner_id=?", (fire_id, owner_id)
        ).fetchone()
    return _row_to_automation_fire(row) if row else None


def list_automation_fires(
    owner_id: str, *, statuses: Optional[set[str]] = None,
    automation_id: Optional[str] = None, limit: int = 200,
) -> list[AutomationFire]:
    clauses = ["owner_id=?"]
    values: list[Any] = [owner_id]
    if statuses:
        allowed = sorted(statuses & (_FIRE_ACTIVE | _FIRE_TERMINAL))
        if not allowed:
            return []
        clauses.append(f"status IN ({','.join('?' * len(allowed))})")
        values.extend(allowed)
    if automation_id:
        clauses.append("automation_id=?")
        values.append(automation_id)
    values.append(max(1, min(int(limit), 500)))
    rows = get_conn().execute(
        f"SELECT * FROM automation_fires WHERE {' AND '.join(clauses)} "
        "ORDER BY created_at DESC LIMIT ?", values,
    ).fetchall()
    return [_row_to_automation_fire(row) for row in rows]


def list_due_automation_fires(now: float, limit: int = 100) -> list[AutomationFire]:
    rows = get_conn().execute(
        """SELECT * FROM automation_fires
           WHERE status IN ('queued','retry_wait') AND next_attempt_at<=?
           ORDER BY next_attempt_at ASC LIMIT ?""",
        (now, max(1, min(int(limit), 500))),
    ).fetchall()
    return [_row_to_automation_fire(row) for row in rows]


def recover_stale_automation_fires(now: float) -> list[AutomationFire]:
    """Turn process-crash leftovers into retry/DLQ instead of permanent `running`."""
    rows = get_conn().execute(
        """SELECT f.* FROM automation_fires f
           JOIN automations a ON a.id=f.automation_id
           WHERE f.status='running' AND f.updated_at + a.timeout_sec <= ?""",
        (now,),
    ).fetchall()
    recovered: list[AutomationFire] = []
    for row in rows:
        fire = _row_to_automation_fire(row)
        run = get_run(fire.run_id) if fire.run_id else get_run_by_idempotency(
            fire.owner_id, f"automation:{fire.id}:attempt:{fire.attempt}"
        )
        if run and run.status in {"planning", "waiting_approval", "running", "paused"}:
            run = set_run_status(
                run.id, "failed", error_code="scheduler_restarted",
                error_message="Automation worker stopped before the attempt finished",
            )
        terminal = fire.attempt >= fire.max_attempts
        get_conn().execute(
            """UPDATE automation_fires SET status=?,retry_of_run_id=COALESCE(?,retry_of_run_id),
               error_code='scheduler_restarted',error_message=?,next_attempt_at=?,
               finished_at=?,updated_at=? WHERE id=? AND status='running'""",
            (
                "dead_letter" if terminal else "retry_wait", run.id if run else None,
                "Automation worker stopped before the attempt finished",
                None if terminal else now, now if terminal else None, now, fire.id,
            ),
        )
        get_conn().commit()
        if fire.session_id:
            mark_session_run(
                fire.session_id, run_status="error", run_summary="Automation worker stopped"
            )
        mark_automation_run(
            fire.automation_id, last_run_at=now, last_session_id=fire.session_id,
            last_status="error" if terminal else "retrying",
        )
        current = get_automation_fire(fire.id)
        if current:
            recovered.append(current)
    return recovered


def has_active_automation_fire(automation_id: str) -> bool:
    return get_conn().execute(
        "SELECT 1 FROM automation_fires WHERE automation_id=? "
        "AND status IN ('queued','running','retry_wait') LIMIT 1", (automation_id,),
    ).fetchone() is not None


def get_active_automation_fire(automation_id: str) -> Optional[AutomationFire]:
    row = get_conn().execute(
        "SELECT * FROM automation_fires WHERE automation_id=? "
        "AND status IN ('queued','running','retry_wait') ORDER BY created_at DESC LIMIT 1",
        (automation_id,),
    ).fetchone()
    return _row_to_automation_fire(row) if row else None


def get_previous_terminal_automation_fire(
    automation_id: str, exclude_fire_id: str,
) -> Optional[AutomationFire]:
    row = get_conn().execute(
        """SELECT * FROM automation_fires WHERE automation_id=? AND id<>?
           AND status IN ('succeeded','dead_letter','ignored')
           ORDER BY finished_at DESC LIMIT 1""",
        (automation_id, exclude_fire_id),
    ).fetchone()
    return _row_to_automation_fire(row) if row else None


def claim_automation_fire(fire_id: str, now: float) -> Optional[AutomationFire]:
    cur = get_conn().execute(
        """UPDATE automation_fires SET status='running',attempt=attempt+1,updated_at=?
           WHERE id=? AND status IN ('queued','retry_wait') AND next_attempt_at<=?""",
        (now, fire_id, now),
    )
    get_conn().commit()
    return get_automation_fire(fire_id) if cur.rowcount == 1 else None


def attach_automation_fire_session(fire_id: str, session_id: str) -> AutomationFire:
    fire = get_automation_fire(fire_id)
    session = get_session(session_id)
    if not fire or not session or session.owner_id != fire.owner_id:
        raise ValueError("automation fire session scope mismatch")
    get_conn().execute(
        "UPDATE automation_fires SET session_id=?,updated_at=? WHERE id=?",
        (session_id, time.time(), fire_id),
    )
    get_conn().commit()
    return get_automation_fire(fire_id)  # type: ignore[return-value]


def schedule_automation_fire_retry(
    fire_id: str, *, run_id: Optional[str], error_code: Optional[str],
    error_message: Optional[str], prompt_tokens: int, completion_tokens: int,
    next_attempt_at: float,
) -> AutomationFire:
    cur = get_conn().execute(
        """UPDATE automation_fires SET status='retry_wait',run_id=?,retry_of_run_id=?,
           error_code=?,error_message=?,prompt_tokens=prompt_tokens+?,
           completion_tokens=completion_tokens+?,next_attempt_at=?,updated_at=?
           WHERE id=? AND status='running'""",
        (run_id, run_id, error_code, (error_message or "")[:500], max(0, prompt_tokens),
         max(0, completion_tokens), next_attempt_at, time.time(), fire_id),
    )
    get_conn().commit()
    if cur.rowcount != 1:
        raise ValueError("automation fire is not running")
    return get_automation_fire(fire_id)  # type: ignore[return-value]


def finish_automation_fire(
    fire_id: str, *, status: str, run_id: Optional[str] = None,
    retry_of_run_id: Optional[str] = None, error_code: Optional[str] = None,
    error_message: Optional[str] = None, prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> AutomationFire:
    if status not in _FIRE_TERMINAL:
        raise ValueError("invalid automation fire terminal status")
    now = time.time()
    cur = get_conn().execute(
        """UPDATE automation_fires SET status=?,run_id=COALESCE(?,run_id),
           retry_of_run_id=COALESCE(?,retry_of_run_id),error_code=?,error_message=?,
           prompt_tokens=prompt_tokens+?,completion_tokens=completion_tokens+?,
           next_attempt_at=NULL,finished_at=?,updated_at=?
           WHERE id=? AND status IN ('queued','running','retry_wait')""",
        (status, run_id, retry_of_run_id, error_code, (error_message or "")[:500] or None,
         max(0, prompt_tokens), max(0, completion_tokens), now, now, fire_id),
    )
    get_conn().commit()
    if cur.rowcount != 1:
        fire = get_automation_fire(fire_id)
        if fire and fire.status == status:
            return fire
        raise ValueError("automation fire is not active")
    return get_automation_fire(fire_id)  # type: ignore[return-value]


def mark_automation_fire_notified(fire_id: str, event: str) -> bool:
    conn = get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute("SELECT notified FROM automation_fires WHERE id=?", (fire_id,)).fetchone()
        if row is None:
            conn.rollback()
            return False
        notified = _load_json(row["notified"], [])
        if event in notified:
            conn.rollback()
            return False
        notified.append(event)
        conn.execute(
            "UPDATE automation_fires SET notified=?,updated_at=? WHERE id=?",
            (json.dumps(notified, ensure_ascii=False), time.time(), fire_id),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise


def ignore_automation_fire(fire_id: str, owner_id: str) -> Optional[AutomationFire]:
    fire = get_automation_fire(fire_id, owner_id)
    if fire is None:
        return None
    if fire.status != "dead_letter":
        raise ValueError("only dead-letter fires can be ignored")
    get_conn().execute(
        "UPDATE automation_fires SET status='ignored',updated_at=? WHERE id=?",
        (time.time(), fire_id),
    )
    get_conn().commit()
    return get_automation_fire(fire_id, owner_id)


def delete_automation(auto_id: str) -> None:
    get_conn().execute("DELETE FROM automations WHERE id=?", (auto_id,))
    get_conn().commit()
