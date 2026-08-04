"""Detailed functional tests — B. 项目 (project config, sandbox isolation,
instruction injection, plan-item write-back, access isolation)."""
import sys, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agentmate_testkit import (Checker, call, stream, health_llm, account, events_of, text_join,
                        has_step, stop_run, read_ws, ws_exists, BASE, WS, wipe_users)

def trace_brief(evs):
    return [
        {
            "event": event.get("event"),
            "tool": event.get("data", {}).get("tool"),
            "status": event.get("data", {}).get("status"),
            "label": event.get("data", {}).get("label"),
            "error": event.get("data", {}).get("message") or event.get("data", {}).get("response"),
        }
        for event in evs
        if event.get("event") not in {"text", "think"}
    ]

OWN, MATE = "btest_own", "btest_mate"
c = Checker()
LLM = health_llm()
tok, uid = account(OWN)
mtok, mid = account(MATE)

# ── B1 CRUD + config round-trip (deterministic) ──
c.section("B1 项目 CRUD + 配置回环")
cfg = {"name": "B项目", "instruction": "# 指令\n简洁作答。", "experts": ["创业伙伴"], "skills": ["Excel 文件处理"], "connectors": ["工作区检索"]}
st, p = call("POST", "/projects", tok, cfg); pid = p["id"]
c.check("create -> role=Owner", st == 200 and p.get("role") == "Owner")
got = call("GET", f"/projects/{pid}", tok)[1]
c.check("instruction/experts/skills/connectors round-trip",
        got["instruction"] == cfg["instruction"] and got["experts"] == cfg["experts"] and got["skills"] == ["excel-csv"] and got["connectors"] == cfg["connectors"])
upd = call("PATCH", f"/projects/{pid}", tok, {"experts": ["创业伙伴", "数据分析报告师"]})[1]
c.check("PATCH updates experts", "数据分析报告师" in upd["experts"])
# B1 only verifies persistence/normalization. The following project-runtime cases
# intentionally exercise project tools without optional loadout prerequisites;
# leaving an uninstalled required Skill here would correctly trip fail-closed
# skill_preload_gate before any sandbox/work-item tool can run.
call("PATCH", f"/projects/{pid}", tok, {"skills": [], "connectors": []})

# ── B7 access isolation (deterministic, no LLM) ──
c.section("B7 访问隔离(非成员/只读/成员写闸)")
c.check("non-member GET project -> 404", call("GET", f"/projects/{pid}", mtok)[0] == 404)
c.check("non-member POST work-item -> 404", call("POST", "/work-items", mtok, {"project_id": pid, "title": "x"})[0] == 404)
call("POST", f"/projects/{pid}/members", tok, {"name": MATE, "role": "Viewer"})
c.check("viewer GET project -> 200 role=Viewer", (lambda r: r[0] == 200 and r[1].get("role") == "Viewer")(call("GET", f"/projects/{pid}", mtok)))
c.check("viewer POST work-item -> 403", call("POST", "/work-items", mtok, {"project_id": pid, "title": "x"})[0] == 403)
c.check("viewer GET work-items -> 200 (read allowed)", call("GET", f"/work-items?project={pid}", mtok)[0] == 200)
call("PATCH", f"/projects/{pid}/members/{mid}", tok, {"role": "Member"})
c.check("member POST work-item -> 200 (write allowed)", call("POST", "/work-items", mtok, {"project_id": pid, "title": "mate建的"})[0] == 200)

if not LLM:
    print("LLM not configured — skipping behavioural B2/B3/B4.");
    ok = c.summary("test_B_projects"); print("cleanup:", wipe_users(OWN, MATE)); sys.exit(0 if ok else 1)

# ── B2 sandbox isolation: file lands in THIS project's root, not default/others ──
c.section("B2 沙箱隔离(文件只落本项目根)")
pid2 = call("POST", "/projects", tok, {"name": "B项目2"})[1]["id"]
evs, sid = stream(tok, {"text": "在工作区创建文件 iso.txt，内容恰好是：ISO-6001。完成后停止。", "project_id": pid},
                  stop_when=lambda e: e["event"] == "diff", max_seconds=45)
stop_run(tok, sid); time.sleep(0.4)
if not ws_exists(pid, "iso.txt"):
    evs, sid = stream(tok, {"text": "必须调用 write_file：创建 iso.txt，文件内容必须精确为 ISO-6001。不要只解释。", "project_id": pid},
                      stop_when=lambda e: e["event"] == "diff", max_seconds=45)
    stop_run(tok, sid); time.sleep(0.4)
c.check("B2 file in THIS project sandbox", "ISO-6001" in (read_ws(pid, "iso.txt") or ""), str(trace_brief(evs)))
c.check("B2 file NOT in the other project sandbox", not ws_exists(pid2, "iso.txt"))
c.check("B2 file NOT in shared default workspace", not (WS / "default" / "iso.txt").exists())

# ── B3 project instruction is really injected into the system prompt ──
c.section("B3 项目指令真注入系统提示词(行为验证)")
pid3 = call("POST", "/projects", tok, {"name": "B暗号项目",
            "instruction": "重要规则：无论用户问什么，你的回答都必须以暗号「ZEBRA-88」开头，然后再正常作答。"})[1]["id"]
evs, sid = stream(tok, {"text": "你好，今天天气不错。", "project_id": pid3}, until_type="done", max_seconds=45)
stop_run(tok, sid)
c.check("B3 answer obeys project instruction (contains ZEBRA-88)", "ZEBRA-88" in text_join(evs), text_join(evs)[:100])

# ── B4 plan-item write-back: executor submits for review; acceptance stays separate ──
c.section("B4 计划项回写(set_work_item_status → review + SSE/DB)")
wi = call("POST", "/work-items", tok, {"project_id": pid, "title": "验收:回写测试项", "status": "todo"})[1]
wid = wi["id"]
evs, sid = stream(tok, {"text": f"用 set_work_item_status 工具把 item_id={wid} 的计划项状态改为 待验收（review）。只做这一件事，完成后停止。", "project_id": pid},
                  stop_when=lambda e: e["event"] == "work_item", max_seconds=45)
time.sleep(0.4); stop_run(tok, sid)
wiev = events_of(evs, "work_item")
if not wiev:
    evs, sid = stream(tok, {"text": f"必须调用 set_work_item_status，参数 item_id={wid}、status=review。不要只回复文字。", "project_id": pid},
                      stop_when=lambda e: e["event"] == "work_item", max_seconds=45)
    time.sleep(0.4); stop_run(tok, sid)
    wiev = events_of(evs, "work_item")
c.check("B4 work_item live SSE event emitted with status review",
        bool(wiev) and wiev[0]["data"].get("item", {}).get("status") == "review", str(trace_brief(evs)))
db_status = call("GET", f"/work-items?project={pid}", tok)[1]["items"]
this = next((x for x in db_status if x["id"] == wid), {})
c.check("B4 work item persisted as review in DB", this.get("status") == "review", str(this.get("status")))

# ── B5 list_work_items tool ──
c.section("B5 list_work_items 工具")
evs, sid = stream(tok, {"text": "用 list_work_items 工具列出本项目所有计划项。", "project_id": pid},
                  stop_when=lambda e: e["event"] == "step" and e["data"].get("tool") == "list_work_items", max_seconds=40)
stop_run(tok, sid)
if not has_step(evs, "list_work_items"):
    evs, sid = stream(tok, {"text": "必须调用 list_work_items 工具读取当前项目计划项，不要直接回答。", "project_id": pid},
                      stop_when=lambda e: e["event"] == "step" and e["data"].get("tool") == "list_work_items", max_seconds=40)
    stop_run(tok, sid)
c.check("B5 list_work_items step emitted", has_step(evs, "list_work_items"), str(trace_brief(evs)))

# ── B6 project activity feed attributes runs to their owner ──
c.section("B6 项目动态流署名")
feed = call("GET", f"/projects/{pid}/sessions", tok)[1]["sessions"]
c.check("B6 feed lists runs with owner_name", len(feed) >= 1 and all("owner_name" in s for s in feed))
c.check("B6 owner runs attributed to owner", any(s.get("owner_name") == OWN for s in feed))

# ── B8 probe: does a NON-member's /chat into a foreign project get blocked? ──
# Status-only probe: open the request, read the HTTP status, close immediately
# (never consume the SSE stream / never let the run proceed).
c.section("B8 探测:非成员能否把 /chat 指向他人项目(隔离)")
import urllib.request as _u, urllib.error as _e, json as _j
stranger, sid_g = account("btest_stranger")
def _chat_status(token, body):
    req = _u.Request(BASE + "/chat", data=_j.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json"); req.add_header("Authorization", "Bearer " + token)
    try:
        r = _u.urlopen(req, timeout=15); code = r.status; r.close(); return code
    except _e.HTTPError as ex:
        return ex.code
st_code = _chat_status(stranger, {"text": "只回复 OK。", "project_id": pid})
blocked = st_code in (403, 404)
c.check("B8 non-member /chat into foreign project is blocked", blocked, f"http={st_code} (200=未拦截,潜在越权,应开 issue)")
wipe_users("btest_stranger")

ok = c.summary("test_B_projects")
print("cleanup:", wipe_users(OWN, MATE))
sys.exit(0 if ok else 1)
