"""Detailed functional tests — F. ask_user 多轮挂起/唤醒 (C-06).

这些用例验证真实的「挂起 / 唤醒」机制，而非模拟：
  agent 调 ask_user → runtime yield `ask_user` SSE 事件并在 asyncio.Event 上挂起
  (session.status="waiting", run="waiting_approval") →
  客户端在 *同一条* 打开的 SSE 流上 POST /chat/{sid}/answer (或 /stop) →
  submit_answers / request_stop 通过 ev.set() 唤醒 → 答案以 tool-result
  ("用户的选择：…") 回灌 LLM → 流继续直至 done。

覆盖：
  F0  answer 对不存在的 session 返回 404（确定性，不需 LLM）
  F1  ask_user 挂起 → owner 提交答案唤醒 → qa_summary 回灌答案 → 流 done（核心）
  F2  挂起期间跨用户 answer 被拒 404（WB-153 owner-scoped 门禁）
  F3  挂起真实生效：session 保持 waiting，不自动结束，owner 唤醒后才 done
  F4  stop 在挂起期间唤醒并把该轮标记为「跳过/取消」→ 流结束

运行（需后端 :8101 已起且已配置 LLM）：
  cd backend && python tests/functional/test_F_ask_user.py
未配置 LLM 时本套件以退出码 2 跳过（与 test_A 一致）。
"""
import sys, os, time, json, threading, urllib.error, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/../..")
from agentmate_testkit import (
    BASE, THROTTLE, call, health_llm, account, wipe_users, events_of, Checker,
)
from config import settings as _settings


# --------------------------------------------------------------------------- #
# Streaming helpers
# --------------------------------------------------------------------------- #
def _stream(tok, body, box, on_event=None, timeout=120):
    """Open the /chat SSE stream in the current thread.
    on_event(event, data, sid) is called per message and may itself issue
    /answer or /stop requests to wake a suspended run. Results land in `box`."""
    payload = {"model": f"test:{_settings.LLM_MODEL}", **body}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BASE + "/chat", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + tok)
    evs, cur, deadline = [], None, time.time() + timeout
    # Pace requests once, rather than delaying every SSE protocol line.  A
    # per-line sleep turns a healthy suspended stream into a client-side
    # timeout as event/data/blank lines accumulate.
    time.sleep(THROTTLE)
    try:
        r = urllib.request.urlopen(req, timeout=timeout + 10)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            response = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            response = raw
        box["evs"] = [{"event": "http_error", "data": {"code": exc.code, "response": response}}]
        return
    try:
        for raw in r:
            if time.time() > deadline:
                break
            line = raw.decode("utf-8", "replace").rstrip("\n")
            if line.startswith("event:"):
                cur = line[6:].strip()
            elif line.startswith("data:"):
                try:
                    d = json.loads(line[5:].strip())
                except Exception:
                    d = {}
                evs.append({"event": cur, "data": d})
                if box.get("sid") is None and cur == "session":
                    box["sid"] = d.get("id") or d.get("session_id")
                if on_event:
                    on_event(cur, d, box["sid"])
                if cur == "done":
                    break
    finally:
        try:
            r.close()
        except Exception:
            pass
        box["evs"] = evs


def open_chat(tok, body, on_event=None, timeout=120):
    """Run the stream on a background thread so the caller can poll / issue
    control requests (answer/stop) while the SSE stream stays open."""
    box = {}
    def _run():
        _stream(tok, body, box, on_event, timeout)
    th = threading.Thread(target=_run, daemon=True)
    th.start()
    return box, th


def stream_chat(tok, body, on_event=None, timeout=120):
    """Blocking variant: stream to completion (or timeout) and return (events, sid)."""
    box, th = open_chat(tok, body, on_event, timeout)
    th.join(timeout + 15)
    return box.get("evs", []), box.get("sid")


def _wait_for_sid(box, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if box.get("sid"):
            return box["sid"]
        time.sleep(0.3)
    return None


def _wait_for_session_status(tok, sid, expected, timeout=30):
    """Poll until the persisted session reaches the expected lifecycle state."""
    deadline = time.time() + timeout
    last_status = None
    while time.time() < deadline:
        st, body = call("GET", f"/sessions/{sid}/messages", tok)
        if st == 200:
            last_status = body["session"].get("status")
            if last_status == expected:
                return last_status
        time.sleep(0.2)
    return last_status


# --------------------------------------------------------------------------- #
# Shared fixtures
# --------------------------------------------------------------------------- #
U = "ftest_F"
CHOICE = "狗"
PROMPT_ASK = (
    "请只调用 ask_user 工具：向我提一个二选一的问题——你喜欢猫还是狗？"
    "把两个选项写成『猫』和『狗』。不要输出任何正文，也不要调用其他工具，"
    "调用 ask_user 之后停下，等待我的回答。"
)

c = Checker()
LLM = health_llm()
tok, uid = account(U)
tok_other, uid_other = account(U + "_other")

if not LLM:
    print("LLM not configured — ask_user behaviour tests cannot run.")
    sys.exit(2)


# --------------------------------------------------------------------------- #
# F0 — answer on an unknown session → 404 (deterministic, no LLM)
# --------------------------------------------------------------------------- #
def test_answer_unknown_session_404():
    st, _ = call("POST", "/chat/does-not-exist/answer", tok, {"answers": ["x"]})
    c.check("F0 answer on unknown session → 404", st == 404)


# --------------------------------------------------------------------------- #
# F1 + F2 — ask_user suspend, owner resume, qa injection, cross-user rejection
# --------------------------------------------------------------------------- #
def test_ask_user_resume_and_owner_scope():
    state = {}

    def on(ev, d, sid):
        if ev == "ask_user" and "asked" not in state:
            state["asked"] = True
            state["sid"] = sid
            # F2: a *different* user's answer on this suspended session must be 404.
            st_x, _ = call("POST", f"/chat/{sid}/answer", tok_other, {"answers": [CHOICE]})
            c.check("F2 cross-user answer rejected (404)", st_x == 404)
            # F1: the owner's answer wakes the suspended run on the same stream.
            st_o, _ = call("POST", f"/chat/{sid}/answer", tok, {"answers": [CHOICE]})
            c.check("F1 owner answer accepted (200)", st_o == 200)

    evs, sid = stream_chat(tok, {"text": PROMPT_ASK}, on_event=on, timeout=120)
    c.check("ask_user event emitted", state.get("asked") is True)
    ask = events_of(evs, "ask_user")
    c.check("ask_user payload has ≥1 question",
            bool(ask) and len(ask[0]["data"].get("questions", [])) >= 1)
    qa = events_of(evs, "qa_summary")
    c.check("qa_summary emitted after answer", len(qa) >= 1)
    if qa:
        got = qa[0]["data"].get("qa", [])
        c.check("answer injected into qa card", bool(got) and got[0].get("a") == CHOICE)
    c.check("stream completed with done", any(e["event"] == "done" for e in evs))


# --------------------------------------------------------------------------- #
# F3 — suspend really pauses: session stays 'waiting', does not auto-finish
# --------------------------------------------------------------------------- #
def test_suspend_no_auto_finish():
    box, th = open_chat(tok, {"text": PROMPT_ASK}, timeout=120)
    sid = _wait_for_sid(box)
    c.check("ask_user session started", sid is not None)
    if sid is None:
        th.join(timeout=10)
        return

    # The session event is emitted before the LLM calls ask_user.  Synchronize
    # on the persisted lifecycle state instead of racing that first event.
    status = _wait_for_session_status(tok, sid, "waiting", timeout=30)
    c.check("session status == waiting on suspend", status == "waiting")

    # It must remain waiting (not auto-finish) for several seconds.
    time.sleep(5)
    _, b2 = call("GET", f"/sessions/{sid}/messages", tok)
    c.check("still waiting after delay (no auto-finish)", b2["session"].get("status") == "waiting")

    # Owner resumes → the run unwinds and the stream reaches done.
    st, _ = call("POST", f"/chat/{sid}/answer", tok, {"answers": [CHOICE]})
    c.check("owner answer accepted on resume", st == 200)
    th.join(timeout=120)
    evs = box.get("evs", [])
    c.check("stream completed with done after resume", any(e["event"] == "done" for e in evs))


# --------------------------------------------------------------------------- #
# F4 — stop wakes a suspended run and marks the turn cancelled
# --------------------------------------------------------------------------- #
def test_stop_wakes_suspended_run():
    state = {}

    def on(ev, d, sid):
        if ev == "ask_user" and "sid" not in state:
            state["sid"] = sid
            st, _ = call("POST", f"/chat/{sid}/stop", tok, {})
            state["stop_st"] = st

    evs, sid = stream_chat(tok, {"text": PROMPT_ASK}, on_event=on, timeout=120)
    c.check("ask_user event emitted", "sid" in state)
    c.check("stop accepted (200)", state.get("stop_st") == 200)
    c.check("stream ended with done after stop", any(e["event"] == "done" for e in evs))
    _, body = call("GET", f"/sessions/{sid}/messages", tok)
    c.check("session no longer waiting after stop", body["session"].get("status") != "waiting")


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    test_answer_unknown_session_404()
    test_ask_user_resume_and_owner_scope()
    test_suspend_no_auto_finish()
    test_stop_wakes_suspended_run()
    ok = c.summary("test_F_ask_user")
    print("cleanup:", wipe_users(U, U + "_other"))
    sys.exit(0 if ok else 1)
