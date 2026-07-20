"""Detailed functional tests — D. 自动化 (validation, real run-now to completion,
in-flight dedup, the REAL scheduler firing a due automation, project binding,
disabled-never-fires)."""
import sys, time, sqlite3, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agentmate_testkit import Checker, call, health_llm, account, DB, wipe_users

U = "dtest_auto"
c = Checker()
LLM = health_llm()
tok, uid = account(U)
pid = call("POST", "/projects", tok, {"name": "D自动化项目"})[1]["id"]
TINY = "只回复 OK 两个字，不要调用任何工具。"

def force_due(auto_id):
    """Push next_run_at into the past so the scheduler treats it as due now."""
    cx = sqlite3.connect(DB, timeout=10)
    cx.execute("UPDATE automations SET next_run_at=? WHERE id=?", (1.0, auto_id)); cx.commit(); cx.close()

def runs_of(aid):
    return call("GET", f"/automations/{aid}/runs", tok)[1]["runs"]

# ── D1 validation + CRUD (deterministic) ──
c.section("D1 校验 + CRUD")
c.check("bad trigger_kind -> 400", call("POST", "/automations", tok, {"name": "x", "prompt": "y", "trigger_kind": "weekly"})[0] == 400)
c.check("interval_min < 1 -> 400", call("POST", "/automations", tok, {"name": "x", "prompt": "y", "interval_min": 0})[0] == 400)
c.check("daily bad at_time -> 400", call("POST", "/automations", tok, {"name": "x", "prompt": "y", "trigger_kind": "daily", "at_time": "26:00"})[0] == 400)
c.check("empty name/prompt -> 400", call("POST", "/automations", tok, {"name": "", "prompt": ""})[0] == 400)
a = call("POST", "/automations", tok, {"name": "自测", "prompt": TINY, "trigger_kind": "interval", "interval_min": 120, "enabled": False})[1]
aid = a["id"]
c.check("create disabled ok", a["enabled"] is False and bool(aid))
c.check("PATCH enable+rename+interval", (lambda r: r["enabled"] and r["name"] == "改名" and r["interval_min"] == 90)(call("PATCH", f"/automations/{aid}", tok, {"enabled": True, "name": "改名", "interval_min": 90})[1]))
c.check("PATCH bind then clear project (null)", call("PATCH", f"/automations/{aid}", tok, {"project_id": pid})[1]["project_id"] == pid and call("PATCH", f"/automations/{aid}", tok, {"project_id": None})[1]["project_id"] in (None, ""))
c.check("runs initially empty", runs_of(aid) == [])

if not LLM:
    print("LLM not configured — skipping real-run D2..D6.")
    call("DELETE", f"/automations/{aid}", tok)
    ok = c.summary("test_D_automation"); print("cleanup:", wipe_users(U)); sys.exit(0 if ok else 1)

# ── D2 run-now really runs to completion and persists messages ──
c.section("D2 run-now 真跑到完成并持久化消息")
st, rn = call("POST", f"/automations/{aid}/run", tok)
run_sid = rn.get("session_id")
c.check("run-now returns session synchronously", st == 200 and rn.get("ok") and bool(run_sid))
final = None
for _ in range(40):  # poll up to ~40s for the bg run to finish
    time.sleep(1.0)
    r = next((x for x in runs_of(aid) if x["id"] == run_sid), None)
    if r and r.get("run_status") in ("ok", "error"): final = r; break
c.check("run reaches terminal status ok", bool(final) and final.get("run_status") == "ok", str(final and final.get("run_status")))
c.check("run carries workspace path (WB-043 detail)", bool(final) and bool(final.get("workspace")))
msgs = call("GET", f"/sessions/{run_sid}/messages", tok)[1]["messages"]
c.check("run persisted a real assistant message", any(m["role"] == "assistant" and m["content"].strip() for m in msgs), str([m["role"] for m in msgs]))
c.check("run appears in cross-automation feed", any(x["id"] == run_sid for x in call("GET", "/automation-runs", tok)[1]["runs"]))

# ── D3 in-flight dedup: two rapid run-now share one session (WB-040) ──
c.section("D3 在飞去重(连点不重复跑)")
along = call("POST", "/automations", tok, {"name": "去重测试", "prompt": "写一段 300 字的自我介绍，尽量详细。", "enabled": False})[1]
alid = along["id"]
s1 = call("POST", f"/automations/{alid}/run", tok)[1].get("session_id")
s2 = call("POST", f"/automations/{alid}/run", tok)[1].get("session_id")  # while first still in flight
c.check("second run-now dedups to the same in-flight session", bool(s1) and s1 == s2, f"{s1} vs {s2}")
if s1: call("POST", f"/chat/{s1}/stop", tok)

# ── D4 & D6: the REAL scheduler fires a due ENABLED automation, not a disabled one ──
c.section("D4/D6 调度器到点真触发(启用触发 / 停用不触发)")
aen = call("POST", "/automations", tok, {"name": "到点触发", "prompt": TINY, "trigger_kind": "interval", "interval_min": 60, "enabled": True})[1]["id"]
adis = call("POST", "/automations", tok, {"name": "停用不触发", "prompt": TINY, "trigger_kind": "interval", "interval_min": 60, "enabled": False})[1]["id"]
force_due(aen); force_due(adis)  # both "due" now; only the enabled one is eligible
fired = None
for _ in range(50):  # scheduler scans every 20s; allow ~50s
    time.sleep(2.0)
    rs = runs_of(aen)
    sched = [x for x in rs if x.get("run_kind") == "scheduled"]
    if sched: fired = sched[0]; break
c.check("D4 scheduler fired the due enabled automation (run_kind=scheduled)", bool(fired), "无 scheduled 运行(可能超时)")
c.check("D6 disabled automation did NOT fire", len(runs_of(adis)) == 0, str(len(runs_of(adis))))

# ── D5 bound automation: its run belongs to the bound project ──
c.section("D5 绑定工作空间的自动化运行归入该项目")
abnd = call("POST", "/automations", tok, {"name": "绑定项目", "prompt": TINY, "project_id": pid, "enabled": False})[1]["id"]
bsid = call("POST", f"/automations/{abnd}/run", tok)[1].get("session_id")
time.sleep(1.0)
brun = next((x for x in runs_of(abnd) if x["id"] == bsid), None)
c.check("D5 bound run carries the project_id", bool(brun) and brun.get("project_id") == pid, str(brun and brun.get("project_id")))
c.check("D5 bound run appears in the project's session feed", any(s["id"] == bsid for s in call("GET", f"/projects/{pid}/sessions", tok)[1]["sessions"]))

# cleanup: disable everything before wipe so nothing fires again
for x in (aid, alid, aen, adis, abnd):
    call("DELETE", f"/automations/{x}", tok)

ok = c.summary("test_D_automation")
print("cleanup:", wipe_users(U))
sys.exit(0 if ok else 1)
