"""Hub SQLite 持久化（WB-061）—— 中心权威源的 DAO。

沿用 backend/storage/db.py 的成熟做法：thread-local 连接（WB-009）、WAL + busy_timeout、
无 ORM。承载账号/组织/项目/成员/邀请，以及目录（catalog_*）的 Hub 侧同构表（预埋，供 P3 下发）。
"""
from __future__ import annotations

import hashlib
import json
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


def init_db() -> None:
    get_conn().executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL DEFAULT '',
            plan TEXT NOT NULL DEFAULT '体验版',
            password_hash TEXT NOT NULL,
            created_at REAL NOT NULL
        );

        -- Hub 签发的 Bearer token（本地 backend 作为客户端持有并回传）。
        CREATE TABLE IF NOT EXISTS hub_tokens (
            token TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_hub_tokens_account ON hub_tokens(account_id);

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

        -- 目录 Hub 侧同构表（预埋，供 P3 下发）。scope ∈ builtin/org；org 级由 org_id 归属。
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
        """
    )
    get_conn().commit()


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
        "INSERT INTO hub_tokens (token, account_id, created_at) VALUES (?,?,?)",
        (token, account_id, time.time()),
    )
    get_conn().commit()
    return token


def account_id_for_token(token: str) -> Optional[str]:
    row = get_conn().execute("SELECT account_id FROM hub_tokens WHERE token=?", (token,)).fetchone()
    return row["account_id"] if row else None


def delete_token(token: str) -> None:
    get_conn().execute("DELETE FROM hub_tokens WHERE token=?", (token,))
    get_conn().commit()


# ---- accounts -----------------------------------------------------------

def _row_to_account(r: sqlite3.Row) -> Account:
    return Account(id=r["id"], name=r["name"], email=r["email"], plan=r["plan"], created_at=r["created_at"])


def create_account(*, name: str, password: str, email: str = "", plan: str = "体验版") -> Account:
    a = Account(id=new_uuid(), name=name[:60], email=email[:120], plan=plan, created_at=time.time())
    get_conn().execute(
        "INSERT INTO accounts (id,name,email,plan,password_hash,created_at) VALUES (?,?,?,?,?,?)",
        (a.id, a.name, a.email, a.plan, hash_password(password), a.created_at),
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
# Hub 侧目录同构表：builtin 由运营下发、org 由团队管理员维护。WB-061 只建表 + 最小读写，
# 完整下发/同步是 P3（WB-063）。

def list_catalog_items(category: str, scope: Optional[str] = None) -> list[dict]:
    if scope:
        rows = get_conn().execute(
            "SELECT * FROM catalog_items WHERE category=? AND scope=? AND enabled=1 ORDER BY sort",
            (category, scope),
        ).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT * FROM catalog_items WHERE category=? AND enabled=1 ORDER BY sort", (category,)
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
        })
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
