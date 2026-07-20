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
from models import Account, Invite, Org, Project, Role

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
            last_seen REAL NOT NULL DEFAULT 0
        );

        -- Server 签发的 Bearer token（本地 backend 作为客户端持有并回传）。
        CREATE TABLE IF NOT EXISTS server_tokens (
            token TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_server_tokens_account ON server_tokens(account_id);

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
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects(owner_id, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_projects_org ON projects(org_id);

        -- 项目成员（owner 不在此表）。access = owner OR 此表一行。
        CREATE TABLE IF NOT EXISTS project_members (
            project_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at REAL NOT NULL,
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
            read INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_server_notifs_account ON server_notifications(account_id, created_at DESC);

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
            sort INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_work_items_project ON work_items(project_id, status, sort);

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

        -- 真·知识库 + 文档（WB-171）：项目级团队知识库。Console 只管理元数据+文档字节，
        -- 绝不算向量（向量化是执行面的事）。embedding_dim 服务端由 embedding_id 派生。
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
        """
    )
    conn.commit()
    # 幂等补列（老库）：accounts.is_platform_admin（WB-066）、last_seen（WB-065 在线状态）。
    have_acct = {r["name"] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()}
    if "is_platform_admin" not in have_acct:
        conn.execute("ALTER TABLE accounts ADD COLUMN is_platform_admin INTEGER NOT NULL DEFAULT 0")
    if "last_seen" not in have_acct:
        conn.execute("ALTER TABLE accounts ADD COLUMN last_seen REAL NOT NULL DEFAULT 0")
    # 幂等补列（老库）：work_items 专业化字段（WB-104）。
    have_wi = {r["name"] for r in conn.execute("PRAGMA table_info(work_items)").fetchall()}
    for _col, _ddl in (
        ("priority", "priority TEXT NOT NULL DEFAULT ''"),
        ("due_date", "due_date TEXT NOT NULL DEFAULT ''"),
        ("start_date", "start_date TEXT NOT NULL DEFAULT ''"),
        ("labels", "labels TEXT NOT NULL DEFAULT '[]'"),
        ("parent_id", "parent_id TEXT NOT NULL DEFAULT ''"),
        ("milestone_id", "milestone_id TEXT NOT NULL DEFAULT ''"),
        ("estimate_h", "estimate_h REAL NOT NULL DEFAULT 0"),   # 工时预估/投入（WB-116）
        ("spent_h", "spent_h REAL NOT NULL DEFAULT 0"),
    ):
        if _col not in have_wi:
            conn.execute(f"ALTER TABLE work_items ADD COLUMN {_ddl}")
    # 幂等补列（老库）：comments.work_item_id —— 任务级评论（WB-115），'' = 项目级。
    have_cm = {r["name"] for r in conn.execute("PRAGMA table_info(comments)").fetchall()}
    if "work_item_id" not in have_cm:
        conn.execute("ALTER TABLE comments ADD COLUMN work_item_id TEXT NOT NULL DEFAULT ''")
    if _table_exists(conn, "catalog_skills"):
        conn.execute("UPDATE catalog_skills SET source='Server' WHERE source='Hub'")
    conn.commit()
    # 一次性：存量 work_items.assignee 自由文本 → account_id 强映射（WB-112c-B）。
    if get_setting("assignee_norm_v1") != "1":
        migrate_assignees_to_account_id()
        set_setting("assignee_norm_v1", "1")


# ---- password / tokens --------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), settings.PBKDF2_ITERS)
    return f"pbkdf2${settings.PBKDF2_ITERS}${salt}${dk.hex()}"


def verify_password(password: str, stored: Optional[str]) -> bool:
    if not stored:
        return False
    try:
        _algo, iters, salt, hexdk = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iters))
        return secrets.compare_digest(dk.hex(), hexdk)
    except Exception:  # noqa: BLE001
        return False


def create_token(account_id: str) -> str:
    token = secrets.token_hex(32)
    get_conn().execute(
        "INSERT INTO server_tokens (token, account_id, created_at) VALUES (?,?,?)",
        (token, account_id, time.time()),
    )
    get_conn().commit()
    return token


def account_id_for_token(token: str) -> Optional[str]:
    row = get_conn().execute("SELECT account_id FROM server_tokens WHERE token=?", (token,)).fetchone()
    return row["account_id"] if row else None


def delete_token(token: str) -> None:
    get_conn().execute("DELETE FROM server_tokens WHERE token=?", (token,))
    get_conn().commit()


# ---- accounts -----------------------------------------------------------

def _row_to_account(r: sqlite3.Row) -> Account:
    keys = r.keys()
    return Account(
        id=r["id"], name=r["name"], email=r["email"], plan=r["plan"], created_at=r["created_at"],
        is_platform_admin=bool(r["is_platform_admin"]) if "is_platform_admin" in keys else False,
    )


def create_account(*, name: str, password: str, email: str = "", plan: str = "体验版") -> Account:
    # 首个注册账号自举为平台管理员（WB-066：可维护 builtin 目录下发）。
    first = get_conn().execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 0
    a = Account(id=new_uuid(), name=name[:60], email=email[:120], plan=plan, created_at=time.time(),
                is_platform_admin=first)
    get_conn().execute(
        "INSERT INTO accounts (id,name,email,plan,password_hash,created_at,is_platform_admin) VALUES (?,?,?,?,?,?,?)",
        (a.id, a.name, a.email, a.plan, hash_password(password), a.created_at, int(a.is_platform_admin)),
    )
    get_conn().commit()
    return a


def get_account(account_id: str) -> Optional[Account]:
    r = get_conn().execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    return _row_to_account(r) if r else None


def get_account_by_name(name: str) -> Optional[tuple[Account, str]]:
    """(account, password_hash) for login, or None."""
    r = get_conn().execute("SELECT * FROM accounts WHERE name=?", (name,)).fetchone()
    return (_row_to_account(r), r["password_hash"]) if r else None


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
    return get_conn().execute("SELECT COUNT(*) FROM accounts WHERE is_platform_admin=1").fetchone()[0]


def _account_admin_view(a: Account, last_seen: float) -> dict:
    """账号 + 在线状态 + 项目数（owner + 成员），供管理台账。绝不含 password_hash。"""
    d = a.to_dict()
    d["last_seen"] = last_seen
    d["online"] = bool(last_seen) and (time.time() - last_seen) < _ONLINE_WINDOW
    d["owned_projects"] = owned_projects_count(a.id)
    d["member_projects"] = member_projects_count(a.id)
    return d


def list_accounts() -> list[dict]:
    """全部平台账号（按创建时间），含在线/项目数的富视图。"""
    rows = get_conn().execute("SELECT * FROM accounts ORDER BY created_at").fetchall()
    return [_account_admin_view(_row_to_account(r), (r["last_seen"] if "last_seen" in r.keys() else 0) or 0) for r in rows]


def get_account_admin_view(account_id: str) -> Optional[dict]:
    r = get_conn().execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    return _account_admin_view(_row_to_account(r), (r["last_seen"] if "last_seen" in r.keys() else 0) or 0) if r else None


def update_account(account_id: str, *, name: Optional[str] = None, email: Optional[str] = None,
                   plan: Optional[str] = None, is_platform_admin: Optional[bool] = None) -> Optional[Account]:
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
        vals.append(account_id)
        get_conn().execute(f"UPDATE accounts SET {','.join(sets)} WHERE id=?", vals)
        get_conn().commit()
    return get_account(account_id)


def set_account_password(account_id: str, password: str) -> None:
    get_conn().execute("UPDATE accounts SET password_hash=? WHERE id=?", (hash_password(password), account_id))
    get_conn().commit()


def delete_account(account_id: str) -> None:
    """删账号并级联清其 token / 项目成员行。调用方须已守卫（非自己/非最后管理员/不拥有项目）。"""
    c = get_conn()
    c.execute("DELETE FROM server_tokens WHERE account_id=?", (account_id,))
    c.execute("DELETE FROM project_members WHERE account_id=?", (account_id,))
    c.execute("DELETE FROM accounts WHERE id=?", (account_id,))
    c.commit()


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
        created_at=now, updated_at=now,
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


def update_project(project_id: str, **fields: Any) -> Optional[Project]:
    cols = {"name", "instruction", "connectors", "experts", "skills"}
    sets, vals = [], []
    for k, v in fields.items():
        if k not in cols or v is None:
            continue
        if k in ("connectors", "experts", "skills"):
            sets.append(f"{k}=?"); vals.append(json.dumps(v, ensure_ascii=False))
        else:
            sets.append(f"{k}=?"); vals.append(v[:120] if k == "name" else v)
    if not sets:
        return get_project(project_id)
    sets.append("updated_at=?"); vals.append(time.time())
    vals.append(project_id)
    get_conn().execute(f"UPDATE projects SET {', '.join(sets)} WHERE id=?", vals)
    get_conn().commit()
    return get_project(project_id)


def list_projects_for(account_id: str) -> list[tuple[Project, Role]]:
    rows = get_conn().execute(
        """
        SELECT p.*, 'Owner' AS _role FROM projects p WHERE p.owner_id=?
        UNION
        SELECT p.*, m.role AS _role FROM projects p
          JOIN project_members m ON m.project_id=p.id
          WHERE m.account_id=? AND p.owner_id<>?
        ORDER BY updated_at DESC
        """,
        (account_id, account_id, account_id),
    ).fetchall()
    return [(_row_to_project(r), Role(r["_role"])) for r in rows]


def add_project_member(project_id: str, account_id: str, role: Role) -> None:
    get_conn().execute(
        "INSERT INTO project_members (project_id, account_id, role, created_at) VALUES (?,?,?,?) "
        "ON CONFLICT(project_id, account_id) DO UPDATE SET role=excluded.role",
        (project_id, account_id, role.value, time.time()),
    )
    get_conn().commit()


def remove_project_member(project_id: str, account_id: str) -> None:
    get_conn().execute(
        "DELETE FROM project_members WHERE project_id=? AND account_id=?", (project_id, account_id)
    )
    get_conn().commit()


def list_project_members(project_id: str) -> list[dict]:
    p = get_conn().execute("SELECT owner_id FROM projects WHERE id=?", (project_id,)).fetchone()
    if not p:
        return []
    out: list[dict] = []
    owner = get_account(p["owner_id"])
    if owner:
        out.append({"account_id": owner.id, "name": owner.name, "role": Role.OWNER.value, "is_owner": True})
    rows = get_conn().execute(
        "SELECT m.account_id, m.role, a.name FROM project_members m JOIN accounts a ON a.id=m.account_id "
        "WHERE m.project_id=? ORDER BY m.created_at",
        (project_id,),
    ).fetchall()
    for r in rows:
        out.append({"account_id": r["account_id"], "name": r["name"], "role": r["role"], "is_owner": False})
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


def mark_invite_accepted(invite_id: str, account_id: str) -> None:
    get_conn().execute("UPDATE invites SET accepted_by=? WHERE id=?", (account_id, invite_id))
    get_conn().commit()


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
    if sort is not None:
        sets.append("sort=?"); vals.append(sort)
    if enabled is not None:
        sets.append("enabled=?"); vals.append(1 if enabled else 0)
    if not sets:
        return False
    sets.append("version=version+1")
    sets.append("updated_at=?"); vals.append(time.time())
    vals.append(item_id)
    cur = get_conn().execute(f"UPDATE catalog_items SET {', '.join(sets)} WHERE id=?", vals)
    get_conn().commit()
    return cur.rowcount > 0


def delete_catalog_item(item_id: str) -> bool:
    cur = get_conn().execute("DELETE FROM catalog_items WHERE id=?", (item_id,))
    get_conn().commit()
    return cur.rowcount > 0


def replace_skillhub_mirror(rows: list[dict]) -> dict:
    """原子替换 SkillHub 镜像目录（WB-069）：先删本来源 builtin 行，再插新的。

    只动 `scope=builtin` 且 `kind IN (skillhub, skillhub-taxonomy)` 的行——不碰人工运营项
    （[[WB-066]]，kind 为空/其它）或 org 覆盖（scope=org）。整段单事务，抓取失败时上层不调用本函数，
    故不会出现「删了但没插」的空窗。rows: [{category, kind, data, sort}]。返回 {deleted, inserted}。
    """
    conn = get_conn()
    now = time.time()
    cur = conn.execute(
        "DELETE FROM catalog_items WHERE scope='builtin' AND kind IN ('skillhub','skillhub-taxonomy')"
    )
    deleted = cur.rowcount
    inserted = 0
    for r in rows:
        conn.execute(
            "INSERT INTO catalog_items (id,category,scope,org_id,kind,data,enabled,sort,version,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,1,?,1,?,?)",
            (new_uuid(), r["category"], "builtin", None, r["kind"],
             json.dumps(r["data"], ensure_ascii=False), r.get("sort", 0), now, now),
        )
        inserted += 1
    conn.commit()
    return {"deleted": deleted, "inserted": inserted}


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


# ---- 团队计划/任务 work_items（WB-081；专业化字段 WB-104）-----------------

def _row_to_work_item(r: sqlite3.Row) -> dict:
    d = dict(r)
    try:
        d["labels"] = json.loads(d.get("labels") or "[]")
    except (json.JSONDecodeError, TypeError):
        d["labels"] = []
    return d


def create_work_item(*, project_id: str, title: str, status: str = "todo",
                     source: str = "手动", assignee: str = "", description: str = "",
                     priority: str = "", due_date: str = "", start_date: str = "",
                     labels: Optional[list[str]] = None, parent_id: str = "",
                     milestone_id: str = "", estimate_h: float = 0.0, spent_h: float = 0.0) -> dict:
    wid = new_uuid(); now = time.time()
    mx = get_conn().execute(
        "SELECT COALESCE(MAX(sort),0) FROM work_items WHERE project_id=? AND status=?",
        (project_id, status),
    ).fetchone()[0]
    get_conn().execute(
        "INSERT INTO work_items (id,project_id,title,status,source,assignee,description,"
        "priority,due_date,start_date,labels,parent_id,milestone_id,estimate_h,spent_h,sort,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (wid, project_id, title, status, source, assignee, description,
         priority, due_date, start_date, json.dumps(labels or [], ensure_ascii=False),
         parent_id, milestone_id, float(estimate_h or 0), float(spent_h or 0), mx + 1, now, now),
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
               "estimate_h", "spent_h"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed and v is not None:
            if k == "labels":
                v = json.dumps(v, ensure_ascii=False)
            sets.append(f"{k}=?"); vals.append(v)
    if not sets:
        return get_work_item(wid)
    sets.append("updated_at=?"); vals.append(time.time())
    vals.append(wid)
    cur = get_conn().execute(f"UPDATE work_items SET {', '.join(sets)} WHERE id=?", vals)
    get_conn().commit()
    return get_work_item(wid) if cur.rowcount else None


def delete_work_item(wid: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT project_id FROM work_items WHERE id=?", (wid,)).fetchone()
    if row is not None:
        # 只在同项目内连带子任务，绝不跨项目级联（WB-157）。
        conn.execute("DELETE FROM work_items WHERE parent_id=? AND project_id=?", (wid, row["project_id"]))
    conn.execute("DELETE FROM work_item_activity WHERE work_item_id=?", (wid,))
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
              contextual: int = 0, tags: Optional[list[str]] = None) -> dict:
    kid = new_uuid(); now = time.time()
    mx = get_conn().execute(
        "SELECT COALESCE(MAX(sort),0) FROM knowledge_bases WHERE project_id=?", (project_id,)
    ).fetchone()[0]
    get_conn().execute(
        "INSERT INTO knowledge_bases (id,project_id,name,description,icon,embedding_id,embedding_dim,"
        "knowledge_type,sentence_size,contextual,tags,sort,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (kid, project_id, name, description, icon, int(embedding_id), kb_embedding_dim(embedding_id),
         int(knowledge_type), int(sentence_size), 1 if contextual else 0,
         json.dumps(tags or [], ensure_ascii=False), mx + 1, now, now),
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


def get_kb(kid: str) -> Optional[dict]:
    r = get_conn().execute("SELECT * FROM knowledge_bases WHERE id=?", (kid,)).fetchone()
    if not r:
        return None
    kb = _row_to_kb(r)
    kb["doc_count"] = count_kb_documents(kid)
    return kb


def update_kb(kid: str, **fields: Any) -> Optional[dict]:
    allowed = {"name", "description", "icon", "embedding_id", "knowledge_type",
               "sentence_size", "contextual", "tags", "sort"}
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
                       doc_id: Optional[str] = None) -> dict:
    did = doc_id or new_uuid(); now = time.time()
    get_conn().execute(
        "INSERT INTO kb_documents (id,kb_id,project_id,filename,size,content_type,doc_type,"
        "storage_path,vector_status,fail_msg,created_at) VALUES (?,?,?,?,?,?,?,?,0,'',?)",
        (did, kb_id, project_id, filename, int(size), content_type, doc_type, storage_path, now),
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
        conn.execute("UPDATE work_items SET milestone_id='' WHERE milestone_id=? AND project_id=?",
                     (mid, row["project_id"]))
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
                     project_id: Optional[str] = None, actor_name: Optional[str] = None) -> None:
    get_conn().execute(
        "INSERT INTO server_notifications (id,account_id,kind,title,body,project_id,actor_name,read,created_at) "
        "VALUES (?,?,?,?,?,?,?,0,?)",
        (new_uuid(), account_id, kind, title, body, project_id, actor_name, time.time()),
    )
    get_conn().commit()


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
