# WorkBuddy

A real, runnable implementation of the WorkBuddy desktop app — built from the
high-fidelity prototype in [`docs/workbuddy-v2.html`](docs/workbuddy-v2.html)
following the plan in [`docs/workbuddy-实现方案.md`](docs/workbuddy-实现方案.md).

**Principle: nothing faked.** All streaming output comes from a real LLM, all
state is persisted, all sidebar tasks are real sessions.

## Status: M0 + M1 complete

- **M0 — scaffold**: all 8 views switchable; styling migrated verbatim from the
  prototype (design tokens + component CSS); Windows menubar, sidebar, view routing.
- **M1 — chat MVP**: real streaming chat over SSE from an OpenAI-compatible LLM;
  Markdown rendering (marked → highlight.js → DOMPurify); stop button; session
  persistence (SQLite); real sidebar task add; composer with model picker /
  permission / context-usage ring; multi-user data model pre-embedded
  (UUID / owner_id / project_id / Role enum) behind an auth-stub middleware.

Later milestones (trace events, files & artifacts, project flow, MCP connectors,
Tauri shell, collaboration) are scoped in the plan doc.

## Architecture (Local-first)

```
Browser (Vite :5173)  ──/api proxy──▶  FastAPI backend (:8000)  ──▶  OpenAI-compatible LLM
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
.venv/Scripts/python main.py                       # → http://localhost:8000

# 3. Frontend (new terminal, from repo root)
pnpm install
pnpm dev                                            # → http://localhost:5173
```

Open http://localhost:5173. Without a key, chat streams a friendly "LLM not
configured" error (the full SSE pipeline still runs); with a key you get real
token-by-token streaming.

### Example `.env` (DeepSeek)

```
LLM_API_KEY=sk-...
LLM_API_BASE=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

Any OpenAI-compatible endpoint works (GLM / Kimi / MiniMax / OpenAI / …).

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
  agent/             # runtime (thin loop) · events (SSE protocol) · llm · sandbox
  routers/           # me · models · sessions · chat · files
  storage/           # SQLite models + DAO (multi-user pre-embedded)
  auth/              # M1 local-user stub → M7 real accounts
docs/                # implementation plan + prototype (visual spec)
```

## SSE event protocol

One event type ⇄ one UI shape. Defined in `backend/agent/events.py` and consumed
in `src/stores/chatStore.ts`: `session · status · text · think · step · file_read ·
diff · todo · usage · artifact · ask_user · error · done`. M1 emits the text /
status / usage / error / done path; the trace events are wired for M2.
