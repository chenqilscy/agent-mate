"""Deterministic live API coverage for WB-198/WB-199 (no LLM calls)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wb_testkit import Checker, account, call, db_get, wipe_users

OWN, VIEWER = "etest_owner", "etest_viewer"
c = Checker()
tok, uid = account(OWN)
vtok, vid = account(VIEWER)

c.section("E1 项目知识库配置持久化")
st, project = call("POST", "/projects", tok, {
    "name": "E知识库项目",
    "knowledge_ids": ["kb-local-a", "kb-local-a", "kb-local-b"],
})
pid = project["id"]
c.check("create de-duplicates knowledge_ids", st == 200 and project.get("knowledge_ids") == ["kb-local-a", "kb-local-b"])
got = call("GET", f"/projects/{pid}", tok)[1]
c.check("GET round-trips knowledge_ids", got.get("knowledge_ids") == ["kb-local-a", "kb-local-b"])
patched = call("PATCH", f"/projects/{pid}", tok, {"knowledge_ids": ["kb-local-c"]})[1]
c.check("PATCH persists knowledge_ids", patched.get("knowledge_ids") == ["kb-local-c"])
raw = db_get("SELECT knowledge_ids FROM projects WHERE id=?", (pid,))
c.check("SQLite ground truth contains local KB id", raw and "kb-local-c" in raw[0][0])

call("POST", f"/projects/{pid}/members", tok, {"name": VIEWER, "role": "Viewer"})
c.check("Viewer cannot edit project KB config", call("PATCH", f"/projects/{pid}", vtok, {"knowledge_ids": []})[0] == 403)

c.section("E2 系统设置按 owner 持久化并校验")
defaults = call("GET", "/settings/system", tok)[1]
c.check("GET has complete defaults", defaults == {
    "interface_scale": 100,
    "reduce_motion": False,
    "default_permission": "default",
    "startup_page": "home",
})
saved = call("PUT", "/settings/system", tok, {
    "interface_scale": 105,
    "reduce_motion": True,
    "default_permission": "full",
    "startup_page": "knowledge",
})[1]
c.check("PUT returns saved system settings", saved == {
    "interface_scale": 105,
    "reduce_motion": True,
    "default_permission": "full",
    "startup_page": "knowledge",
})
c.check("GET round-trips system settings", call("GET", "/settings/system", tok)[1] == saved)
c.check("invalid scale rejected", call("PUT", "/settings/system", tok, {"interface_scale": 123})[0] == 422)
c.check("owner isolation", call("GET", "/settings/system", vtok)[1]["interface_scale"] == 100)

ok = c.summary("test_E_project_kb_system_settings")
print("cleanup:", wipe_users(OWN, VIEWER))
sys.exit(0 if ok else 1)
