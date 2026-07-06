"""Detailed functional tests — A. 新建任务 / 会话 (the agent runtime & tool loop).

Every tool behaviour is verified by its REAL side effect (file on disk / persisted
trace / SSE tool event), not the model's wording. Runs stop as soon as the
decisive event fires — the effect is already committed."""
import sys, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wb_testkit import (Checker, call, stream, health_llm, account, session_id, events_of, text_join,
                        has_step, stop_run, read_ws, ws_exists, plant_file, wipe_users)

U = "atest_A"
c = Checker()
LLM = health_llm()
tok, uid = account(U)
pid = call("POST", "/projects", tok, {"name": "A文件项目"})[1]["id"]

if not LLM:
    print("LLM not configured — agent behaviour tests cannot run."); sys.exit(2)

# A1 — write_file: real file appears on disk with exact content
c.section("A1 write_file → diff event + file on disk")
evs, sid = stream(tok, {"text": "在工作区创建文件 note_a.txt，内容恰好是一行：ALPHA-7788。完成后立即停止，不要再调用其它工具。", "project_id": pid},
                  stop_when=lambda e: e["event"] == "diff", max_seconds=45)
stop_run(tok, sid)
diff = events_of(evs, "diff")
c.check("A1 diff event emitted (op/file)", bool(diff) and diff[0]["data"].get("file") == "note_a.txt", str(diff[:1]))
time.sleep(0.3)
c.check("A1 file written to project sandbox with exact content", (read_ws(pid, "note_a.txt") or "").find("ALPHA-7788") >= 0, repr(read_ws(pid, "note_a.txt")))

# A2 — read_file: agent reads a planted file and echoes its secret
c.section("A2 read_file → file_read event + content flows back")
plant_file(pid, "seed.txt", "验证码：BETA-3344\n仅此一行。")
evs, sid = stream(tok, {"text": "读取工作区文件 seed.txt，把其中的验证码原样告诉我（只回验证码）。", "project_id": pid},
                  until_type="done", max_seconds=45)
stop_run(tok, sid)
c.check("A2 file_read event for seed.txt", any(e["event"] == "file_read" and e["data"].get("path") == "seed.txt" for e in evs))
c.check("A2 secret from file present in answer", "BETA-3344" in text_join(evs), text_join(evs)[:120])

# A3 — run_command: real subprocess runs, side effect lands in the sandbox
c.section("A3 run_command → real subprocess writes a file in the sandbox")
evs, sid = stream(tok, {"text": "只用 run_command 工具运行一条 shell 命令，把文本 WBRUN-5150 写入工作区文件 cmdout.txt（用 echo 重定向即可）。完成后停止。", "project_id": pid},
                  stop_when=lambda e: e["event"] == "step" and e["data"].get("tool") == "run_command", max_seconds=45)
time.sleep(0.5); stop_run(tok, sid)
c.check("A3 run_command step emitted", has_step(evs, "run_command"))
c.check("A3 real command wrote file in sandbox", "WBRUN-5150" in (read_ws(pid, "cmdout.txt") or ""), repr(read_ws(pid, "cmdout.txt")))

# A4 — list_dir
c.section("A4 list_dir → step event")
evs, sid = stream(tok, {"text": "用 list_dir 列出工作区根目录，告诉我是否存在 seed.txt。", "project_id": pid},
                  until_type="done", max_seconds=40)
stop_run(tok, sid)
c.check("A4 list_dir step emitted", has_step(evs, "list_dir"))

# A5 — update_plan → todo events
c.section("A5 update_plan → todo trace events")
evs, sid = stream(tok, {"text": "把「做一杯手冲咖啡」拆成 3 个步骤，用 update_plan 工具登记这份待办清单。", "project_id": pid},
                  stop_when=lambda e: e["event"] == "todo", max_seconds=40)
stop_run(tok, sid)
c.check("A5 at least one todo event", len(events_of(evs, "todo")) >= 1)

# A6 — plan mode is read-only: no write_file, file must NOT appear
c.section("A6 plan mode read-only (no write tools)")
evs, sid = stream(tok, {"text": "在工作区创建文件 forbidden.txt，内容为 SHOULD_NOT_EXIST。", "project_id": pid, "plan": True},
                  until_type="done", max_seconds=45)
stop_run(tok, sid); time.sleep(0.3)
c.check("A6 no diff event in plan mode", len(events_of(evs, "diff")) == 0)
c.check("A6 forbidden.txt NOT created", not ws_exists(pid, "forbidden.txt"))

# A7 — ask mode has zero tools
c.section("A7 ask mode (pure Q&A, no tools)")
evs, sid = stream(tok, {"text": "在工作区创建文件 ask.txt。", "project_id": pid, "ask": True},
                  until_type="done", max_seconds=40)
stop_run(tok, sid); time.sleep(0.3)
tool_evs = [e for e in evs if e["event"] in ("diff", "file_read", "step") and e["data"].get("tool") != "loadout"]
c.check("A7 no tool events in ask mode", len(tool_evs) == 0, str(tool_evs[:2]))
c.check("A7 ask.txt NOT created", not ws_exists(pid, "ask.txt"))

# A8 — stop mid-run resets session status
c.section("A8 stop mid-run → status reset to idle")
holder = {"sid": None, "stopped": False}
def _stopper(e):
    if e["event"] == "session": holder["sid"] = e["data"].get("id")
    if e["event"] == "text" and holder["sid"] and not holder["stopped"]:
        call("POST", f"/chat/{holder['sid']}/stop", token=tok); holder["stopped"] = True
        return True
    return False
evs, sid = stream(tok, {"text": "写一篇 800 字、结构完整的关于时间管理的长文，逐段展开。", "project_id": pid},
                  stop_when=_stopper, max_seconds=45)
c.check("A8 stop endpoint acknowledged", holder["stopped"])
st = "running"
for _ in range(12):  # poll up to ~6s for the run to finalize to idle
    time.sleep(0.5)
    st = call("GET", f"/sessions/{holder['sid']}/messages", tok)[1]["session"]["status"]
    if st != "running": break
c.check("A8 session status reset (not stuck at running)", st != "running", f"status={st}")

# A9 — refs are injected this turn only, NOT persisted into the user message
c.section("A9 refs used this turn but not persisted")
evs, sid = stream(tok, {"text": "根据我给你的资料回答：暗号是什么？只回答暗号本身。",
                        "refs": [{"name": "secret.txt", "content": "本次任务暗号是 QING-4521，请严格保密。"}]},
                  until_type="done", max_seconds=40)
stop_run(tok, sid)
c.check("A9 agent used the ref content", "QING-4521" in text_join(evs), text_join(evs)[:120])
msgs = call("GET", f"/sessions/{sid}/messages", tok)[1]["messages"]
umsg = next((m for m in msgs if m["role"] == "user"), {})
c.check("A9 ref body NOT persisted in user message", "QING-4521" not in umsg.get("content", ""), umsg.get("content", "")[:80])

# A10 — multi-turn context carries across turns in one session
c.section("A10 multi-turn context memory")
evs, S = stream(tok, {"text": "请记住我的幸运数字是 73。只回复 OK。"}, until_type="done", max_seconds=40)
c.check("A10 turn-1 created a session", bool(S))
c.check("A10 usage event emitted (context accounting)", len(events_of(evs, "usage")) >= 1)
evs2, _ = stream(tok, {"text": "我刚让你记住的幸运数字是多少？只回复数字。", "session_id": S}, until_type="done", max_seconds=40)
c.check("A10 turn-2 recalls the number from history", "73" in text_join(evs2), text_join(evs2)[:80])

# A11 — persistence & replay
c.section("A11 messages persisted & replayable")
msgs = call("GET", f"/sessions/{S}/messages", tok)[1]["messages"]
roles = [m["role"] for m in msgs]
c.check("A11 >=4 messages persisted (2 user + 2 assistant)", len(msgs) >= 4 and roles.count("user") >= 2 and roles.count("assistant") >= 2, str(roles))
c.check("A11 assistant recall answer persisted", any(m["role"] == "assistant" and "73" in m["content"] for m in msgs))

ok = c.summary("test_A_chat")
n, p = wipe_users(U)
print(f"cleanup: removed {n} user, {p} project(s)")
sys.exit(0 if ok else 1)
