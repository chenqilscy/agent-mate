# AgentMate

AgentMate is a real, runnable local-first AI work companion. It was initially informed by a high-fidelity
Tencent WorkBuddy reference prototype, now archived with official-source notes under
[`docs/WorkBuddy/`](docs/WorkBuddy/), and has evolved into an independent product.

**Nothing faked:** streaming output comes from a real LLM, state is persisted, tool traces come from actual calls,
and a catalog card is never treated as proof that a capability works.

## Current status

The working baseline includes:

- React 19 + Vite + TypeScript + Zustand App UI;
- FastAPI local backend with SSE, SQLite, project workspaces and a real tool loop;
- projects, work items, automations, experts, Skills, MCP connectors, knowledge bases and model management;
- multi-assistant support with real Telegram and email channels;
- Tauri 2 shell, PyInstaller sidecar, tray and MSI/NSIS build scaffolding;
- optional AgentMate Server control plane and its same-origin AgentMate Console.

The active issue ledger is [`docs/issues/`](docs/issues/README.md), with completed records compacted under its archive.
The product/code roadmap is closed. Two release milestones remain deferred: formal production desktop-update deployment
needs deployment-owned HTTPS infrastructure, protected signing material and a production rollout window; the V1
controlled-user pilot needs a fixed beta build, 3–5 target users and five working days of real-use evidence.

## Architecture

```text
Tauri 2 or Browser (Vite :8102)
              │ REST + SSE (/api in development)
              ▼
FastAPI App backend (:8101) ──▶ OpenAI-compatible LLM
  agent runtime · MCP · SQLite · workspace/
              │ optional AGENTMATE_SERVER_URL
              ▼
AgentMate Server (:8100) ──▶ same-origin AgentMate Console
  accounts · orgs · projects · collaboration · AgentMate catalog
```

The App backend runs on the user's machine. It owns LLM/tool execution, credentials, installed Skills, sessions and
workspace files. The optional Server owns shared control-plane data; it does not execute agents or receive secrets,
workspace files or conversation bodies.

Third-party SkillHub browsing and installation are performed directly by each App. Server may publish a recommendation
pointer and display copy, but does not mirror the marketplace, store SkillHub keys or host third-party skill packages.

Detailed boundaries:

- [current implementation](docs/agentmate-实现方案.md)
- [App/Server data and sync rules](docs/agentmate-数据分层与同步规范.md)
- [Server architecture and capability-release target](docs/agentmate-server-架构设计.md)
- [Console architecture](docs/agentmate-console-管理门户设计.md)
- [desktop build and updater status](docs/desktop-build.md)

## Run locally

Prerequisites: Node.js 20+, pnpm and Python 3.11+.

```powershell
# App backend
Set-Location backend
python -m venv .venv
./.venv/Scripts/pip.exe install -r requirements.txt
Copy-Item .env.example .env          # configure backend-only LLM settings
./.venv/Scripts/python.exe main.py   # http://127.0.0.1:8101

# App frontend (new terminal, repository root)
pnpm install
pnpm dev                             # http://127.0.0.1:8102
```

Open `http://127.0.0.1:8102`. LLM provider credentials may be supplied through `backend/.env` or the local per-owner
model settings stored by the backend; they are never placed in frontend code.

Settings follow explicit ownership: Console manages platform-wide WeKnora and collaboration policy; the App's
Settings dialog manages device-wide Langfuse, local ASR and Server/timeline behavior; existing model, connector,
assistant, user and project settings keep their narrower scopes. Runtime settings are persisted by the owning backend,
take effect without a service restart, keep secrets write-only, and fall back to environment variables when cleared.
Database paths, bind ports, cryptographic bootstrap material and release versions remain deployment-only.

### Optional Server and Console

```powershell
./run-stack.ps1
```

This starts Server `:8100`, App backend `:8101` with `AGENTMATE_SERVER_URL`, and App frontend `:8102`. Remove the
Server URL for pure-local operation; local execution remains available when Server is absent or unreachable.

Reusable local Server test-account credentials, when provisioned, are recorded in
`docs/local-test-accounts.md`. That file is intentionally ignored by Git because it contains login passwords; use it
only against the local or explicitly designated controlled-test database.

## Repository layout

```text
src/                 React App UI, stores, platform abstraction and global styles
backend/             local FastAPI execution plane, SQLite, tools, Skills and MCP
server/              independent FastAPI control plane and hosted Console assets
console/             React + Ant Design Console source
src-tauri/           Tauri 2 shell, sidecar, tray and updater scaffolding
docs/                current designs, WorkBuddy references and issue ledger
```

## Development checks

```powershell
pnpm build
backend/.venv/Scripts/python.exe -m unittest discover -s backend/tests/regression -p "test_*.py"
backend/.venv/Scripts/python.exe -m py_compile backend/main.py server/main.py
```

`pnpm build` is the real TypeScript/build gate; plain root `tsc --noEmit` can miss project-reference errors.
The App and Console production builds are expected to pass; any regression must be tracked explicitly rather than
hidden by weakening the command.

After backend runtime changes, hard-restart `:8101` before live verification. Static checks are not a substitute for
real API/browser acceptance.

## SSE contract

One event type maps to one UI shape. The backend contract is defined in `backend/agent/events.py` and consumed in
`src/stores/chatStore.ts`. Changes to events must update both sides and cover persisted-history replay.

## Security summary

- Secrets stay in the local backend (`backend/.env` or local owner-scoped DB) and are excluded from source control.
- Workspace paths are resolved inside the active project/assistant sandbox.
- `run_command` is constrained and audited but still runs with backend OS permissions; it is not a VM sandbox.
- Server-origin resources enforce account/project roles; Viewer is read-only.
- Server sync is guarded and local-first; network failure must not erase last-known-good local state.
