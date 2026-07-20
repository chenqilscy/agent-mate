"""Shared kit for WorkBuddy detailed functional tests against a LIVE backend.

These are INTEGRATION / end-to-end tests: they need the backend running on
:8000 (real LLM configured in backend/.env) and hit the real SQLite DB. Run them
from a scratch state or accept that each suite creates a throwaway account and
deletes ALL of its data at the end.

Design principle: assert REAL side effects (files on disk, rows in SQLite, typed
SSE tool events) — the ground truth — not the LLM's prose. A directive prompt
induces an action; we stream until the decisive event (diff/step/work_item),
then STOP the run (the side effect is already committed) and verify it on disk/DB.
That makes LLM-driven tests rigorous instead of flaky.

Overrides via env: WB_TEST_BASE, WORKBUDDY_DB, WORKBUDDY_WORKSPACE.
"""
import json, time, os, sqlite3, shutil, sys, urllib.request, urllib.error
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]   # backend/tests/functional/ -> backend/
sys.path.insert(0, str(_BACKEND))
from config import settings as _settings
BASE = os.environ.get("WB_TEST_BASE", "http://127.0.0.1:8000/api")
DB = os.environ.get("WORKBUDDY_DB", str(_BACKEND / "workbuddy.db"))
WS = Path(os.environ.get("WORKBUDDY_WORKSPACE", str(_BACKEND / "workspace")))
PW = "pw1234"
THROTTLE = 2.0  # seconds paced before each real /chat run (rate-limit friendly)


class Checker:
    def __init__(self):
        self.ok = self.fail = self.skip = 0
        self.failures = []
    def section(self, title):
        print(f"\n== {title} ==")
    def check(self, label, cond, detail=""):
        if cond:
            self.ok += 1; print(f"  PASS  {label}")
        else:
            self.fail += 1; self.failures.append(label)
            print(f"  FAIL  {label}" + (f"   [{detail}]" if detail else ""))
        return bool(cond)
    def skipped(self, label, why):
        self.skip += 1; print(f"  SKIP  {label}   [{why}]")
    def summary(self, name):
        print(f"\n=== {name}: {self.ok} passed, {self.fail} failed, {self.skip} skipped ===")
        if self.failures:
            print("  failed: " + " | ".join(self.failures))
        return self.fail == 0


def call(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if body is not None: req.add_header("Content-Type", "application/json")
    if token: req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw.decode()) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, None


def health_llm():
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=5) as h:
            return json.loads(h.read().decode()).get("llm_configured", False)
    except Exception:
        return False


def stream(token, body, stop_when=None, until_type=None, max_seconds=45):
    """POST /chat, parse SSE events, return (events, session_id). Stops early when
    `stop_when(event)` is truthy OR an event of type `until_type` arrives OR the
    time budget elapses. Never raises on HTTP error — returns an http_error event.

    Paces itself (THROTTLE s) so a long suite of back-to-back real runs doesn't
    trip the LLM endpoint's rate limit (which would surface as a transient error
    run and confuse a per-behaviour assertion)."""
    time.sleep(THROTTLE)
    # WB-136 后新账号没有默认模型是正常产品行为；E2E 明确选择 backend/.env 的测试模型，
    # 避免把“未配置默认模型”误报成技能/连接器失效。`test:<id>` 走 runtime 的 legacy 显式模型分支。
    body = {"model": f"test:{_settings.LLM_MODEL}", **body}
    data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + "/chat", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + token)
    evs, cur, deadline = [], None, time.time() + max_seconds
    try:
        r = urllib.request.urlopen(req, timeout=max_seconds)
    except urllib.error.HTTPError as e:
        return [{"event": "http_error", "data": {"code": e.code}}], None
    try:
        for raw in r:
            line = raw.decode("utf-8", "replace").rstrip("\n")
            if line.startswith("event: "):
                cur = line[7:]
            elif line.startswith("data: "):
                try: payload = json.loads(line[6:])
                except Exception: payload = {}
                ev = {"event": cur, "data": payload}
                evs.append(ev)
                if until_type and cur == until_type: break
                if stop_when and stop_when(ev): break
            if time.time() > deadline: break
    except (TimeoutError, OSError):
        # A slow/stalled run hit the socket timeout — return what we collected so a
        # single laggy LLM turn degrades to a normal (possibly failing) assertion
        # instead of crashing the whole suite with an unhandled exception.
        pass
    finally:
        r.close()
    return evs, session_id(evs)


def session_id(evs):
    for e in evs:
        if e["event"] == "session":
            return e["data"].get("id")
    return None

def events_of(evs, etype):
    return [e for e in evs if e["event"] == etype]

def text_join(evs):
    return "".join(e["data"].get("md", "") for e in evs if e["event"] == "text")

def has_step(evs, tool):
    return any(e["event"] == "step" and e["data"].get("tool") == tool for e in evs)

def loadout_label(evs):
    e = next((x for x in evs if x["event"] == "step" and x["data"].get("tool") == "loadout"), None)
    return e["data"].get("label", "") if e else None

def stop_run(token, sid):
    if sid: call("POST", f"/chat/{sid}/stop", token=token)


# ---- workspace ground truth --------------------------------------------------

def proj_root(pid):
    return WS / "projects" / pid

def read_ws(pid, rel):
    p = proj_root(pid) / rel
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else None

def ws_exists(pid, rel):
    return (proj_root(pid) / rel).exists()

def plant_file(pid, rel, content):
    p = proj_root(pid) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ---- account + cleanup -------------------------------------------------------

def account(name):
    st, r = call("POST", "/auth/register", body={"name": name, "password": PW})
    if st != 200:
        st, r = call("POST", "/auth/login", body={"name": name, "password": PW})
    tok = r["token"]
    uid = call("GET", "/me", token=tok)[1]["id"]
    return tok, uid

def db_get(sql, params=()):
    c = sqlite3.connect(DB, timeout=15)
    try:
        return c.execute(sql, params).fetchall()
    finally:
        c.close()

def wipe_users(*names):
    """Delete the named test accounts and everything they own (idempotent)."""
    time.sleep(1.0)  # let in-flight bg runs settle
    c = sqlite3.connect(DB, timeout=20)
    mcols = [r[1] for r in c.execute("PRAGMA table_info(messages)")]
    scol = "session_id" if "session_id" in mcols else ("session" if "session" in mcols else None)
    ph = ",".join("?" * len(names))
    uids = [r[0] for r in c.execute(f"SELECT id FROM users WHERE name IN ({ph})", names).fetchall()]
    pids = []
    if uids:
        q = ",".join("?" * len(uids))
        pids = [r[0] for r in c.execute(f"SELECT id FROM projects WHERE owner_id IN ({q})", uids).fetchall()]
        sids = [r[0] for r in c.execute(f"SELECT id FROM sessions WHERE owner_id IN ({q})", uids).fetchall()]
        if scol and sids:
            qs = ",".join("?" * len(sids))
            c.execute(f"DELETE FROM messages WHERE {scol} IN ({qs})", sids)
    for u in uids:
        for t, col in (("automations","owner_id"),("work_items","owner_id"),("sessions","owner_id"),
                       ("projects","owner_id"),("project_members","user_id"),("notifications","user_id"),
                       ("auth_tokens","user_id"),("user_settings","owner_id")):
            c.execute(f"DELETE FROM {t} WHERE {col}=?", (u,))
        c.execute("DELETE FROM users WHERE id=?", (u,))
    c.commit(); c.close()
    for p in pids:
        shutil.rmtree(WS / "projects" / p, ignore_errors=True)
    return len(uids), len(pids)
