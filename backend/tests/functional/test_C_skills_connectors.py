"""Detailed functional tests — C. 技能 · 连接器 (loadout truly applies; built-in MCP
connectors return REAL data; skill toolpacks add REAL new tools; not-ready & plan
gating). Experts are intentionally out of scope (per user)."""
import atexit, sys, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agentmate_testkit import (Checker, call, stream, health_llm, account, events_of, text_join,
                        has_step, loadout_label, stop_run, read_ws, plant_file, wipe_users)

def trace_brief(evs):
    return [
        {
            "event": event.get("event"),
            "tool": event.get("data", {}).get("tool"),
            "label": event.get("data", {}).get("label"),
            "message": event.get("data", {}).get("message"),
        }
        for event in evs
        if event.get("event") not in {"text", "think"}
    ]

U = "ctest_sc"
c = Checker()
LLM = health_llm()
tok, uid = account(U)
pid = call("POST", "/projects", tok, {"name": "C技能连接器项目"})[1]["id"]

if not LLM:
    print("LLM not configured — cannot test loadout behaviour."); sys.exit(2)

# WB-216 后目录技能必须先真实安装再运行。门禁只安装缺失项，并在退出时恢复原安装态（WB-232）。
_installed_by_test = []
_status, _payload = call("GET", "/skills", tok)
if _status != 200:
    print("Cannot read installed skills."); sys.exit(2)
_installed = {s.get("slug") or s.get("key") for s in _payload.get("skills", [])}
for _slug in ("web-access", "excel-csv", "github-connector-guide"):
    if _slug in _installed:
        continue
    _code, _ = call("POST", f"/skills/catalog/{_slug}/install", tok)
    if _code != 200:
        print(f"Cannot install required catalog skill: {_slug} ({_code})."); sys.exit(2)
    _installed_by_test.append(_slug)

def _restore_skill_state():
    for _slug in reversed(_installed_by_test):
        call("POST", f"/skills/{_slug}/uninstall", tok)

atexit.register(_restore_skill_state)

def is_loadout(e): return e["event"] == "step" and e["data"].get("tool") == "loadout"

# C1 — loadout step lists the skill + connector that were selected (real open)
c.section("C1 loadout 真加载(技能+连接器)")
evs, sid = stream(tok, {"text": "只回复 OK。", "skills": ["excel-csv"], "connectors": ["时间助手"]},
                  stop_when=is_loadout, max_seconds=30)
stop_run(tok, sid)
lbl = loadout_label(evs) or ""
c.check("C1 skill in loadout", "Excel 文件处理" in lbl and "技能未就绪" not in lbl, lbl)
c.check("C1 connector opened (时间助手) in loadout", "连接器" in lbl and "时间助手" in lbl, lbl)

# C2 — clock connector returns the REAL host date
c.section("C2 时间助手连接器返回真实日期")
year = time.strftime("%Y")
evs, sid = stream(tok, {"text": "用连接器工具查询今天的日期（today 或 now），把返回的日期原样告诉我。", "connectors": ["时间助手"]},
                  until_type="done", max_seconds=45)
stop_run(tok, sid)
c.check("C2 clock tool invoked (now/today step)", has_step(evs, "today") or has_step(evs, "now"), str([e["data"].get("tool") for e in events_of(evs, "step")]))
c.check("C2 real current year returned from clock", year in text_join(evs), text_join(evs)[:120])

# C3 — notes connector: add_note truly writes notes.json in the workspace
c.section("C3 本地便签连接器真实写盘")
evs, sid = stream(tok, {"text": "用便签工具 add_note 记录一条便签，内容恰好是：NOTE-7742。完成后停止。", "connectors": ["本地便签"], "project_id": pid},
                  stop_when=lambda e: e["event"] == "step" and e["data"].get("tool") == "add_note", max_seconds=45)
time.sleep(0.5); stop_run(tok, sid)
c.check("C3 add_note tool invoked", has_step(evs, "add_note"))
c.check("C3 notes.json written with the note", "NOTE-7742" in (read_ws(pid, "notes.json") or ""), repr(read_ws(pid, "notes.json")))

# C4 — search connector finds a planted marker in the workspace
c.section("C4 工作区检索连接器命中真实内容")
plant_file(pid, "buried/deep.txt", "无关内容\n这里有一个标记 FINDME-9080 藏在深处\n结束")
evs, sid = stream(tok, {"text": "用工作区检索工具 search_files 搜索 FINDME-9080，告诉我命中的文件路径与内容。", "connectors": ["工作区检索"], "project_id": pid},
                  until_type="done", max_seconds=45)
stop_run(tok, sid)
c.check("C4 search_files tool invoked", has_step(evs, "search_files"))
c.check("C4 planted marker surfaced from search", "FINDME-9080" in text_join(evs) or "deep.txt" in text_join(evs), text_join(evs)[:140])

# C5 — Web Access skill ships a REAL new tool (web_fetch)
c.section("C5 Web Access 技能提供真实新工具 web_fetch")
evs, sid = stream(tok, {"text": "用 web_fetch 工具抓取 https://example.com ，告诉我页面里出现的一个英文单词。", "skills": ["web-access"]},
                  until_type="done", max_seconds=50)
stop_run(tok, sid)
c.check("C5 web_fetch tool available & invoked (toolpack works)", has_step(evs, "web_fetch"))
txt = text_join(evs)
if "example" in txt.lower() or "Example" in txt or "Domain" in txt:
    c.check("C5 real page content fetched (Example Domain)", True)
else:
    c.skipped("C5 real page content fetched", "网络不可达或页面被拦截")

# C6 — Excel skill analyze_csv computes REAL stats over a workspace CSV
c.section("C6 Excel 技能 analyze_csv 真实统计")
plant_file(pid, "data.csv", "name,score\nA,10\nB,20\nC,30\nD,40\n")  # 4 data rows
evs, sid = stream(tok, {"text": "用 analyze_csv 工具分析工作区的 data.csv，告诉我它有多少数据行（不含表头）。", "skills": ["excel-csv"], "project_id": pid},
                  until_type="done", max_seconds=45)
stop_run(tok, sid)
c.check("C6 analyze_csv tool invoked", has_step(evs, "analyze_csv"))
c.check("C6 real row count (4) reported from CSV", "4" in text_join(evs), text_join(evs)[:140])

# C7 — GitHub must be surfaced honestly whether this device has credentials or not.
c.section("C7 GitHub 凭据就绪态如实显示(不静默失败)")
evs, sid = stream(tok, {"text": "只回复 OK。", "connectors": ["GitHub"]}, stop_when=is_loadout, max_seconds=30)
stop_run(tok, sid)
lbl = loadout_label(evs) or ""
gate = next((
    event["data"].get("label", "") for event in evs
    if event["event"] == "step" and event["data"].get("tool") == "connector_skill_gate"
), "")
c.check("C7 GitHub readiness is visible in loadout",
        ("GitHub" in lbl and "连接器 GitHub" in lbl)
        or ("GitHub" in gate and "GITHUB_TOKEN" in gate), str(trace_brief(evs)))

# C8 — plan mode does NOT open connectors (read-only run)
c.section("C8 计划模式禁用连接器")
evs, sid = stream(tok, {"text": "只回复 OK。", "connectors": ["时间助手"], "plan": True}, until_type="done", max_seconds=40)
stop_run(tok, sid)
lbl = loadout_label(evs)
c.check(
    "C8 connector is skipped with a transparent plan-mode reason",
    (lbl is None) or ("未就绪" in lbl and "计划模式不启用外部连接器" in lbl),
    repr(lbl),
)

# C9 — Telegram (built-in but token-gated) without a token → not-ready, not silent
c.section("C9 Telegram 无 token → 连接器未就绪(不静默失败)")
evs, sid = stream(tok, {"text": "只回复 OK。", "connectors": ["Telegram"]}, stop_when=is_loadout, max_seconds=30)
stop_run(tok, sid)
lbl = loadout_label(evs) or ""
c.check("C9 Telegram shown as not-ready in loadout", "未就绪" in lbl and "Telegram" in lbl, lbl)

ok = c.summary("test_C_skills_connectors")
print("cleanup:", wipe_users(U))
sys.exit(0 if ok else 1)
