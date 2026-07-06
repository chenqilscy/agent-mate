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
from typing import Any, Optional

from config import settings
from storage.models import (
    LOCAL_USER_ID,
    LOCAL_USER_NAME,
    Automation,
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
            automation_id TEXT
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
        """
    )
    conn.commit()
    _migrate_columns()
    _ensure_local_user()


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
) -> Session:
    # automation_id links a run back to the automation that produced it (WB-035);
    # None for ordinary chat/project sessions. It's a table column only, not carried
    # on the Session dataclass — callers that need runs use list_automation_runs.
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
    )
    get_conn().execute(
        """INSERT INTO sessions (id,title,owner_id,project_id,space,kind,status,created_at,updated_at,automation_id)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (s.id, s.title, s.owner_id, s.project_id, s.space, s.kind, s.status, s.created_at, s.updated_at, automation_id),
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
    )


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
