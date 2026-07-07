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
_SHOWCASE_SKIP = {"SKILLHUB_GRID", "SKILLHUB_FEATURED", "SKILLHUB_KITS", "SKILLHUB_CATS"}
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
            updated_at REAL NOT NULL
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
            attachments TEXT NOT NULL DEFAULT '[]'
        );
        CREATE INDEX IF NOT EXISTS idx_work_items_project
            ON work_items(project_id, created_at);

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
        """
    )
    conn.commit()
    _migrate_columns()
    _ensure_local_user()
    _seed_catalog()
    _seed_showcase()


def _migrate_columns() -> None:
    """幂等补列：老库缺少后加的列时 ALTER TABLE 补上（CREATE TABLE IF NOT EXISTS 不会改已存在的表）。"""
    conn = get_conn()
    # WB-026: work_items 增 description / due_date / attachments。
    have = {r["name"] for r in conn.execute("PRAGMA table_info(work_items)").fetchall()}
    for col, ddl in (
        ("description", "description TEXT NOT NULL DEFAULT ''"),
        ("due_date", "due_date TEXT"),
        ("attachments", "attachments TEXT NOT NULL DEFAULT '[]'"),
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
    for r in rows:
        try:
            val = json.loads(r["data"])
        except (json.JSONDecodeError, TypeError):
            continue
        if r["is_scalar"]:
            out[r["kind"]] = val
        else:
            out.setdefault(r["kind"], []).append(val)
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
    """Mark the user's notifications read — all of them, or just `ids`."""
    conn = get_conn()
    if ids:
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"UPDATE notifications SET read=1 WHERE user_id=? AND id IN ({placeholders})",
            (user_id, *ids),
        )
    else:
        conn.execute("UPDATE notifications SET read=1 WHERE user_id=?", (user_id,))
    conn.commit()


# ---- work items (kanban / tasks, §11 阶段 B) ----------------------------

def _row_to_work_item(r: sqlite3.Row) -> WorkItem:
    keys = r.keys()
    try:
        attachments = json.loads(r["attachments"]) if "attachments" in keys and r["attachments"] else []
    except (json.JSONDecodeError, TypeError):
        attachments = []
    return WorkItem(
        id=r["id"], project_id=r["project_id"], owner_id=r["owner_id"], title=r["title"],
        status=r["status"], source=r["source"], assignee=r["assignee"],
        created_at=r["created_at"], updated_at=r["updated_at"],
        description=r["description"] if "description" in keys and r["description"] else "",
        due_date=r["due_date"] if "due_date" in keys else None,
        attachments=attachments if isinstance(attachments, list) else [],
    )


def create_work_item(
    *, project_id: str, owner_id: str, title: str, status: str = "todo",
    source: str = "手动", assignee: str = "", description: str = "",
    due_date: Optional[str] = None, attachments: Optional[list] = None,
) -> WorkItem:
    now = time.time()
    wi = WorkItem(
        id=new_uuid(), project_id=project_id, owner_id=owner_id, title=title[:200],
        status=status, source=source, assignee=assignee or owner_id,
        created_at=now, updated_at=now,
        description=description[:4000], due_date=due_date, attachments=attachments or [],
    )
    get_conn().execute(
        """INSERT INTO work_items
           (id,project_id,owner_id,title,status,source,assignee,created_at,updated_at,description,due_date,attachments)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (wi.id, wi.project_id, wi.owner_id, wi.title, wi.status, wi.source, wi.assignee,
         wi.created_at, wi.updated_at, wi.description, wi.due_date, json.dumps(wi.attachments, ensure_ascii=False)),
    )
    get_conn().commit()
    return wi


def list_work_items(project_id: str) -> list[WorkItem]:
    rows = get_conn().execute(
        "SELECT * FROM work_items WHERE project_id=? ORDER BY created_at ASC", (project_id,)
    ).fetchall()
    return [_row_to_work_item(r) for r in rows]


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
    if not sets:
        return get_work_item(item_id)
    sets.append("updated_at=?"); vals.append(time.time())
    vals.append(item_id)
    get_conn().execute(f"UPDATE work_items SET {', '.join(sets)} WHERE id=?", vals)
    get_conn().commit()
    return get_work_item(item_id)


def delete_work_item(item_id: str) -> None:
    get_conn().execute("DELETE FROM work_items WHERE id=?", (item_id,))
    get_conn().commit()


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
