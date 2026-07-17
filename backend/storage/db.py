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
import secrets
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from config import settings
from storage.catalog_seed import BUILTIN_CONNECTORS, BUILTIN_EXPERTS

# 橱窗目录种子源（WB-060）：由 catalog.ts 导出的静态商品卡，逐字迁进本文件同级 JSON，
# 首次启动 seed 进 catalog_showcase 表。放这里而非硬编码在 .py，正是「数据不写死在代码」。
_SHOWCASE_JSON = Path(__file__).resolve().parent / "catalog_showcase.json"
# SkillHub 商店浏览列表（SKILLHUB_*）不入库——WB-064 会改成实时 rankings/search，与本处重叠，
# 由那条 issue 负责其数据源；这里刻意跳过、留纯净面给它。前端仍从 catalog.ts 直取这几项。
# （SKILLHUB_KITS 已随「套件」功能整体删除，见 WB-182 —— JSON 里已无该键，无需再跳过。）
_SHOWCASE_SKIP = {"SKILLHUB_GRID", "SKILLHUB_FEATURED", "SKILLHUB_CATS"}
from storage.models import (
    LOCAL_USER_ID,
    LOCAL_USER_NAME,
    Automation,
    CatalogConnector,
    CatalogExpert,
    Expert,
    Message,
    Project,
    Role,
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


def init_db() -> None:
    conn = get_conn()
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

        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            instruction TEXT NOT NULL DEFAULT '',
            connectors TEXT NOT NULL DEFAULT '[]',
            experts TEXT NOT NULL DEFAULT '[]',
            skills TEXT NOT NULL DEFAULT '[]',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            origin TEXT NOT NULL DEFAULT 'local'
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
            spent_h REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_work_items_project
            ON work_items(project_id, created_at);

        CREATE TABLE IF NOT EXISTS milestones (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            due_date TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            sort INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
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
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            next_run_at REAL NOT NULL,
            last_run_at REAL,
            last_session_id TEXT,
            last_status TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_automations_owner
            ON automations(owner_id, created_at DESC);

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

        -- 上行同步 outbox（WB-062 Phase 3）：执行产出先落本地，再由后台 worker 推 Hub；
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

        -- 本地 user（= Hub account id）→ 其 Hub token，供后台 outbox worker 以本人身份推送。
        CREATE TABLE IF NOT EXISTS hub_identities (
            user_id TEXT PRIMARY KEY,
            hub_token TEXT NOT NULL,
            updated_at REAL NOT NULL
        );

        -- 存量导入映射（WB-063）：本地资源 → 其在 Hub 的 id，保证「重复导入不产生重复数据」。
        CREATE TABLE IF NOT EXISTS hub_imports (
            local_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            hub_id TEXT NOT NULL,
            hub_account_id TEXT NOT NULL,
            created_at REAL NOT NULL
        );

        -- LOCAL_USER_ID ↔ Hub 账号 的绑定（WB-063）：记住本机存量数据导入到了哪个 Hub 账号。
        CREATE TABLE IF NOT EXISTS hub_link (
            local_user_id TEXT PRIMARY KEY,
            hub_account_id TEXT NOT NULL,
            hub_account_name TEXT NOT NULL DEFAULT '',
            linked_at REAL NOT NULL
        );

        -- Hub 目录下发镜像（WB-066）：客户端从 Hub 拉的目录项，覆盖本地 showcase 分类；
        -- Hub 空/离线 → 本地 builtin 种子作兜底（架构 §5「Hub 下发 + 本地 override」）。
        CREATE TABLE IF NOT EXISTS catalog_downlink (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            data TEXT NOT NULL,
            sort INTEGER NOT NULL DEFAULT 0,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_catalog_downlink_cat ON catalog_downlink(category, sort);

        -- 外部渠道 ⇄ 会话映射（WB-072）：一个外部会话（如某个 Telegram chat）绑定到
        -- 一个长期 WorkBuddy 会话，续聊不断线。同时充当白名单：存在绑定 = 已授权。
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
    _migrate_assistants()


def _migrate_columns() -> None:
    """幂等补列：老库缺少后加的列时 ALTER TABLE 补上（CREATE TABLE IF NOT EXISTS 不会改已存在的表）。"""
    conn = get_conn()
    # WB-026: work_items 增 description / due_date / attachments。
    # WB-108: 专业 PM 字段 priority / start_date / labels / parent_id / milestone_id（与 Hub 对齐）。
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

    # WB-062 Phase 2: projects 增 origin（'local'|'hub'）——标记从 Hub 下行拉取的只读镜像项目。
    have_p = {r["name"] for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
    if "origin" not in have_p:
        conn.execute("ALTER TABLE projects ADD COLUMN origin TEXT NOT NULL DEFAULT 'local'")

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
            continue
        conn.execute(
            """INSERT INTO catalog_experts
               (id,scope,owner_id,slug,name,subtitle,avatar,intro,persona,tags,category,badge,source,
                functional,enabled,sort,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (new_uuid(), "builtin", None, name, name, "", "🧑", "", e["persona"],
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
               (id,scope,owner_id,name,icon,description,status,launch,enabled,sort,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (new_uuid(), "builtin", None, name, c.get("icon", ""), c.get("description", ""),
             c.get("status", "rdy"), json.dumps(c.get("launch", {}), ensure_ascii=False),
             1, i, now, now),
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
        if kind in _SHOWCASE_SKIP:
            continue  # SkillHub 商店列表交给 WB-064
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


# ---- Hub 账号镜像（WB-062）----------------------------------------------
# 本地 backend 把 Hub 校验过的账号镜像进 users（无本地口令），让所有 owner-scoped 代码
# 无改动地认它；已校验的 Hub token 缓存进 auth_tokens，后续请求走本地、不再打 Hub。

def upsert_external_user(user_id: str, name: str, plan: str = "体验版") -> None:
    """把 Hub 账号镜像进本地 users（幂等 upsert，无 password_hash）。id = Hub account id。"""
    get_conn().execute(
        "INSERT INTO users (id,name,role,plan) VALUES (?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, plan=excluded.plan",
        (user_id, ((name or "").strip()[:60] or user_id[:8]), Role.OWNER.value, plan),
    )
    get_conn().commit()


def cache_token(token: str, user_id: str) -> None:
    """缓存已校验的 Hub token → account 映射（后续请求本地命中，不再校验 Hub）。"""
    get_conn().execute(
        "INSERT OR IGNORE INTO auth_tokens (token,user_id,created_at) VALUES (?,?,?)",
        (token, user_id, time.time()),
    )
    get_conn().commit()


def mirror_hub_project(
    *, id: str, name: str, owner_id: str, instruction: str = "",
    connectors: Optional[list] = None, experts: Optional[list] = None, skills: Optional[list] = None,
) -> None:
    """幂等镜像一个 Hub 项目进本地 projects（origin='hub'，只读镜像；WB-062 Phase 2）。
    id/owner_id = Hub 侧 project/account id。WB-050 的 project_access_role 读同一批表，故镜像后
    本地访问控制「自动」认它——无需改访问校验。"""
    now = time.time()
    get_conn().execute(
        """INSERT INTO projects (id,name,owner_id,instruction,connectors,experts,skills,created_at,updated_at,origin)
           VALUES (?,?,?,?,?,?,?,?,?,'hub')
           ON CONFLICT(id) DO UPDATE SET name=excluded.name, owner_id=excluded.owner_id,
             instruction=excluded.instruction, connectors=excluded.connectors,
             experts=excluded.experts, skills=excluded.skills, updated_at=excluded.updated_at, origin='hub'""",
        (id, name[:120], owner_id, instruction,
         json.dumps(connectors or [], ensure_ascii=False),
         json.dumps(experts or [], ensure_ascii=False),
         json.dumps(skills or [], ensure_ascii=False), now, now),
    )
    get_conn().commit()


def replace_hub_project_members(project_id: str, members: list[dict]) -> None:
    """幂等重置一个镜像项目的成员表：清旧、按 Hub 返回重建（owner 不入表，由 owner_id 记）。
    同时把每个成员账号镜像进 users 以便显示名解析（WB-062 Phase 2）。"""
    conn = get_conn()
    conn.execute("DELETE FROM project_members WHERE project_id=?", (project_id,))
    for m in members:
        aid = m.get("account_id")
        if not aid:
            continue
        upsert_external_user(aid, m.get("name", ""))  # 成员/owner 账号镜像进 users
        if m.get("is_owner"):
            continue  # owner 由 projects.owner_id 记，不入 project_members
        try:
            role = Role(m.get("role", "Member"))
        except ValueError:
            role = Role.MEMBER
        conn.execute(
            "INSERT INTO project_members (project_id,user_id,role,created_at) VALUES (?,?,?,?) "
            "ON CONFLICT(project_id,user_id) DO UPDATE SET role=excluded.role",
            (project_id, aid, role.value, time.time()),
        )
    conn.commit()


# ---- Hub 上行 outbox + 身份（WB-062 Phase 3）----------------------------

def set_hub_identity(user_id: str, hub_token: str) -> None:
    """记住某账号的 Hub token，供后台 outbox worker 以本人身份推送。幂等 upsert。"""
    get_conn().execute(
        "INSERT INTO hub_identities (user_id,hub_token,updated_at) VALUES (?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET hub_token=excluded.hub_token, updated_at=excluded.updated_at",
        (user_id, hub_token, time.time()),
    )
    get_conn().commit()


def get_hub_identity(user_id: str) -> Optional[str]:
    r = get_conn().execute("SELECT hub_token FROM hub_identities WHERE user_id=?", (user_id,)).fetchone()
    return r["hub_token"] if r else None


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


# ---- 存量导入 + LOCAL↔Hub 绑定（WB-063）--------------------------------

def record_import(local_id: str, kind: str, hub_id: str, hub_account_id: str) -> None:
    get_conn().execute(
        "INSERT OR REPLACE INTO hub_imports (local_id,kind,hub_id,hub_account_id,created_at) "
        "VALUES (?,?,?,?,?)",
        (local_id, kind, hub_id, hub_account_id, time.time()),
    )
    get_conn().commit()


def get_import(local_id: str) -> Optional[dict]:
    r = get_conn().execute("SELECT * FROM hub_imports WHERE local_id=?", (local_id,)).fetchone()
    return dict(r) if r else None


def set_hub_link(local_user_id: str, hub_account_id: str, hub_account_name: str = "") -> None:
    get_conn().execute(
        "INSERT INTO hub_link (local_user_id,hub_account_id,hub_account_name,linked_at) VALUES (?,?,?,?) "
        "ON CONFLICT(local_user_id) DO UPDATE SET hub_account_id=excluded.hub_account_id, "
        "hub_account_name=excluded.hub_account_name, linked_at=excluded.linked_at",
        (local_user_id, hub_account_id, hub_account_name, time.time()),
    )
    get_conn().commit()


def get_hub_link(local_user_id: str) -> Optional[dict]:
    r = get_conn().execute("SELECT * FROM hub_link WHERE local_user_id=?", (local_user_id,)).fetchone()
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
        created_at=now,
        updated_at=now,
    )
    get_conn().execute(
        """INSERT INTO projects (id,name,owner_id,instruction,connectors,experts,skills,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            p.id, p.name, p.owner_id, p.instruction,
            json.dumps(p.connectors, ensure_ascii=False),
            json.dumps(p.experts, ensure_ascii=False),
            json.dumps(p.skills, ensure_ascii=False),
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
) -> Project:
    sets: list[str] = []
    vals: list[Any] = []
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


def builtin_persona(name: str) -> Optional[str]:
    """某个专家名对应的内置/目录人格（真注入用）。命中 enabled 且 functional 的目录专家，
    优先 builtin scope；无则 None（调用方回退通用人格）。替代原 EXPERTS 静态字典查表。"""
    row = get_conn().execute(
        "SELECT persona FROM catalog_experts "
        "WHERE name=? AND functional=1 AND enabled=1 AND persona<>'' "
        "ORDER BY (scope<>'builtin'), sort LIMIT 1",
        (name,),
    ).fetchone()
    return row["persona"] if row else None


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


def _row_to_catalog_connector(r: sqlite3.Row) -> CatalogConnector:
    try:
        launch = json.loads(r["launch"]) if r["launch"] else {}
    except (json.JSONDecodeError, TypeError):
        launch = {}
    return CatalogConnector(
        id=r["id"], scope=r["scope"], owner_id=r["owner_id"], name=r["name"], icon=r["icon"],
        description=r["description"], status=r["status"], launch=launch if isinstance(launch, dict) else {},
        enabled=bool(r["enabled"]), sort=r["sort"], created_at=r["created_at"], updated_at=r["updated_at"],
    )


def connector_specs() -> dict[str, dict[str, Any]]:
    """连接器名 → 启动 spec（enabled 行），替代 mcp_client 里原硬编码的 CONNECTORS 字典。
    同名多行时以 sort 靠前者为准（builtin 种子 sort 小、稳定生效）。"""
    rows = get_conn().execute(
        "SELECT name, launch FROM catalog_connectors WHERE enabled=1 ORDER BY sort"
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
    # WB-066: Hub 目录下发覆盖本地（仅数组类分类）；无下发/离线 → 本地兜底。scalar 分类 skeleton 不覆盖。
    for cat, items in downlink_by_category().items():
        if cat not in scalar_kinds:
            out[cat] = items
    return out


def replace_all_downlink(items: list[dict]) -> None:
    """幂等重置 Hub 目录下发镜像：清空后按 Hub 返回全量重建（Hub 侧删除随之消失）。
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
    get_conn().execute(
        "INSERT INTO project_members (project_id, user_id, role, created_at) VALUES (?,?,?,?) "
        "ON CONFLICT(project_id, user_id) DO UPDATE SET role=excluded.role",
        (project_id, user_id, role.value, time.time()),
    )
    get_conn().commit()


def remove_project_member(project_id: str, user_id: str) -> None:
    get_conn().execute(
        "DELETE FROM project_members WHERE project_id=? AND user_id=?", (project_id, user_id)
    )
    get_conn().commit()


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


def mirror_hub_work_items(project_id: str, items: list[dict]) -> None:
    """用 Hub 的 work_items 覆盖某 hub-origin 项目的本地 work_items（Hub 权威，WB-091）。
    本地行 = Hub 行镜像（Hub id 作本地 id，供 update/delete 定位 + 离线读兜底）；
    owner_id 空、attachments/due_date 取默认（Hub work_items 不带这些本地专有字段）。"""
    conn = get_conn()
    conn.execute("DELETE FROM work_items WHERE project_id=?", (project_id,))
    for it in items:
        labels = it.get("labels") or []
        conn.execute(
            """INSERT INTO work_items
               (id,project_id,owner_id,title,status,source,assignee,created_at,updated_at,description,due_date,attachments,
                priority,start_date,labels,parent_id,milestone_id,estimate_h,spent_h)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (it.get("id") or new_uuid(), project_id, "", str(it.get("title", ""))[:200],
             it.get("status", "todo"), it.get("source", "手动"), it.get("assignee", ""),
             it.get("created_at") or time.time(), it.get("updated_at") or time.time(),
             str(it.get("description", ""))[:4000], it.get("due_date") or None, "[]",
             it.get("priority", ""), it.get("start_date") or None,
             json.dumps(labels if isinstance(labels, list) else [], ensure_ascii=False),
             it.get("parent_id", ""), it.get("milestone_id", ""),
             float(it.get("estimate_h") or 0), float(it.get("spent_h") or 0)),
        )
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


# ---- milestones（WB-108；本地镜像 Hub 权威 + 本地项目自管）--------------

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


def mirror_hub_milestones(project_id: str, items: list[dict]) -> None:
    """用 Hub 里程碑覆盖某 hub-origin 项目的本地镜像（Hub 权威，WB-108）。"""
    conn = get_conn()
    conn.execute("DELETE FROM milestones WHERE project_id=?", (project_id,))
    for i, it in enumerate(items):
        conn.execute(
            "INSERT INTO milestones (id,project_id,name,description,due_date,status,sort,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (it.get("id") or new_uuid(), project_id, str(it.get("name", ""))[:200],
             str(it.get("description", "")), it.get("due_date") or None,
             it.get("status", "open"), it.get("sort", i),
             it.get("created_at") or time.time(), it.get("updated_at") or time.time()),
        )
    conn.commit()


def list_messages(session_id: str) -> list[Message]:
    rows = get_conn().execute(
        "SELECT * FROM messages WHERE session_id=? ORDER BY created_at ASC",
        (session_id,),
    ).fetchall()
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
        name=(old.get("name") or "").strip() or "WorkBuddy 助理",
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
    )


def create_automation(
    *, owner_id: str, name: str, prompt: str, trigger_kind: str = "interval",
    interval_min: int = 60, at_time: str = "09:00",
    project_id: Optional[str] = None, model: Optional[str] = None, enabled: bool = True,
) -> Automation:
    now = time.time()
    a = Automation(
        id=new_uuid(), owner_id=owner_id, name=name[:120], prompt=prompt,
        trigger_kind=trigger_kind, interval_min=interval_min, at_time=at_time,
        project_id=project_id, model=model, enabled=enabled,
        created_at=now, updated_at=now,
        next_run_at=compute_next_run(trigger_kind, interval_min, at_time, now),
    )
    get_conn().execute(
        """INSERT INTO automations
           (id,owner_id,name,prompt,trigger_kind,interval_min,at_time,project_id,model,
            enabled,created_at,updated_at,next_run_at,last_run_at,last_session_id,last_status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (a.id, a.owner_id, a.name, a.prompt, a.trigger_kind, a.interval_min, a.at_time,
         a.project_id, a.model, int(a.enabled), a.created_at, a.updated_at, a.next_run_at,
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


_AUTOMATION_FIELDS = {"name", "prompt", "trigger_kind", "interval_min", "at_time", "project_id", "model", "enabled"}
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


def delete_automation(auto_id: str) -> None:
    get_conn().execute("DELETE FROM automations WHERE id=?", (auto_id,))
    get_conn().commit()
