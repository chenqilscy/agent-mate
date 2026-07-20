# AgentMate

A real, runnable local-first AI work companion. AgentMate was initially built
from a high-fidelity reference prototype of Tencent WorkBuddy in
[`docs/tencent-workbuddy-reference.html`](docs/tencent-workbuddy-reference.html), following the plan in
[`docs/agentmate-实现方案.md`](docs/agentmate-实现方案.md), and is now an independent product.

**Principle: nothing faked.** All streaming output comes from a real LLM, all
state is persisted, all sidebar tasks are real sessions.

## Status: M0–M7 + Server + Console 全部落地（活台账见 `docs/issues/`）

> 里程碑 M0–M4 的原始说明在下方保留（对这些阶段仍准确）。此后已落地：M5（专家/技能/真 MCP 连接器）、
> M6（对话内搜索/响应式）、M7 协作（真账户鉴权 + 项目成员·角色·邀请 + 队友只读可见 + 消息中心）、
> Tauri 2 桌面外壳（路线 A）、自动化/连接器补全（路线 B）、**AgentMate Server**（云端控制平面，独立 `server/`
> 服务 :8100）、**AgentMate Console**（Web 管理门户 + 专业 PM）、统一设置中心、GLM 知识库 RAG、模型管理、
> 多助理·多渠道（Telegram/邮件）、语音输入 ASR、金山文档面板等。逐条进度以 `docs/issues/` 台账为准。

### M0–M4（历史说明，仍准确）

- **M0 — scaffold**: all 8 views switchable; styling migrated verbatim from the
  prototype (design tokens + component CSS); Windows menubar, sidebar, view routing.
- **M1 — chat MVP**: real streaming chat over SSE from an OpenAI-compatible LLM;
  Markdown rendering (marked → highlight.js → DOMPurify); stop button; session
  persistence (SQLite); real sidebar task add; composer with model picker /
  permission / context-usage ring; multi-user data model pre-embedded
  (UUID / owner_id / project_id / Role enum) behind an auth-stub middleware.
- **M2 — trace system**: the agent runtime is a real tool-use loop. The LLM calls
  sandbox tools (list_dir / read_file / write_file / run_command / update_plan);
  each call emits a typed trace event (think / step / file_read / diff / todo) that
  the UI renders as a koda-style execution log — collapsible, with the outline
  (概览) listing chapters from the answer's headings. Reasoning (when the model
  exposes it) streams as `think`. Trace + token usage are persisted and replay from
  history. Context-usage breakdown is real (system prompt / tool schemas / messages).
- **M3 — files & artifacts**: the overview panel's 工作空间文件 tab shows the real
  recursive workspace tree; the 产物 section lists files the agent wrote (derived
  from the diff trace). A file viewer renders Markdown through the pipeline and code
  with a line-number gutter. The file tree, artifact cards, and trace blue-links all
  open the same real file (`/api/files/content`).
- **M4 — project flow + ask_user + Plan mode**:
  - *ask_user*: the agent can call `ask_user`; the runtime suspends the coroutine on
    an `asyncio.Event` and resumes when the user answers via `POST /api/chat/{id}/answer`
    — on the *same* open SSE stream, across multiple rounds. The AskUserCard
    (paging / options / other / skip) drives it and the answered Q&A persists as a
    trace card.
  - *Plan mode*: composer toggle → plan-only system prompt + read-only tools, so the
    agent plans without executing.
  - *Projects*: the new-project modal (name / instruction + template presets /
    connector·expert·skill pickers) persists via `POST /api/projects`. Opening a
    project starts a project-scoped execution view whose agent runs with the
    project's instruction injected as background; its side panel has 产物 /
    工作空间文件 / 变更 tabs (变更 = the real diff list).

M5+（MCP 连接器 / Tauri 外壳 / 协作 / Server / Console / 知识库 / 多助理 …）均已落地——见上方状态段与 `docs/issues/` 台账。

## Architecture (Local-first)

```
Browser (Vite :8102)  ──/api proxy──▶  FastAPI backend (:8101)  ──▶  OpenAI-compatible LLM
  React 19 + TS + Zustand                Agent runtime (thin loop)      (LLM_API_BASE)
  marked/DOMPurify/hljs                  SQLite persistence
                                         sandbox workspace/
```

The backend runs on the user's own machine — the browser is just the display.
In M5 a Tauri 2 shell wraps it (the backend ships as a PyInstaller sidecar); the
UI never imports Tauri directly — it goes through `src/platform/`.

## Run locally

Prereqs: Node 20+, pnpm, Python 3.11+.

```bash
# 1. Backend — configure the LLM key (backend only; the frontend never sees it)
cd backend
cp .env.example .env          # fill in LLM_API_KEY and LLM_API_BASE
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # Windows
# .venv/bin/pip install -r requirements.txt        # macOS/Linux

# 2. Start the backend
.venv/Scripts/python main.py                       # → http://localhost:8101

# 3. Frontend (new terminal, from repo root)
pnpm install
pnpm dev                                            # → http://localhost:8102
```

Open http://localhost:8102. Without a key, chat streams a friendly "LLM not
configured" error (the full SSE pipeline still runs); with a key you get real
token-by-token streaming.

### With AgentMate Server (optional 3-tier)

The two commands above run AgentMate **local-first** (no cloud). To also run the
control plane — [`server/`](server/), the authoritative source for accounts / orgs /
projects / members and the shared catalog (including the periodic SkillHub mirror,
WB-069) — start all three tiers:

```
Browser (:8102) ──/api──▶ backend (:8101) ──AGENTMATE_SERVER_URL──▶ Server (:8100)
```

```powershell
./run-stack.ps1     # Server :8100 + backend :8101 (Server-connected) + frontend :8102
```

`run-stack.ps1` launches each tier in its own window and skips any port already
listening. It points the backend at the Server via `AGENTMATE_SERVER_URL=http://127.0.0.1:8100`
(also settable in `backend/.env`). Remove that line for pure-local: every feature
still works offline — the skills page just serves its static/local catalog instead
of the Server mirror.

### Example `.env` (DeepSeek)

```
LLM_API_KEY=sk-...
LLM_API_BASE=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

Any OpenAI-compatible endpoint works (GLM / Kimi / MiniMax / OpenAI / …).

可选的 Langfuse LLM trace、token、TTFT 与工具链路观测见
[`docs/langfuse-observability.md`](docs/langfuse-observability.md)。该能力默认关闭且默认不上传正文。

## Layout

```
src/                 # React frontend
  views/             # 8 views (Home·Chat·Assistant·Projects·Experts·Automation·Inspire·MyFiles)
  components/        # composer/ chat/ panel/ layout/ ui/
  stores/            # zustand: chat·ui·settings·toast·auth
  lib/               # api·sse·markdown·types·icons
  platform/          # window/tray/notify abstraction (web no-op; Tauri in M5)
  styles/            # tokens.css + app.css (migrated from prototype)
backend/             # FastAPI + SSE
  agent/             # runtime (tool loop) · events (SSE protocol) · llm · tools · sandbox
  routers/           # me · models · sessions · chat · files
  storage/           # SQLite models + DAO (multi-user pre-embedded)
  auth/              # M1 local-user stub → M7 real accounts
docs/                # implementation plan + prototype (visual spec)
```

## SSE event protocol

One event type ⇄ one UI shape. Defined in `backend/agent/events.py` and consumed
in `src/stores/chatStore.ts`: `session · status · text · think · step · file_read ·
diff · todo · ask_user · qa_summary · work_item · usage · error · done`. M2 emits the
full trace path (think/step/file_read/diff/todo) from real tool calls; `ask_user` +
`qa_summary` drive the project ask/answer flow (M4); `work_item` live-syncs the kanban
when the agent changes a plan item (WB-031). (`artifact` has a builder reserved for a
future 产物 push but isn't yielded yet.)
