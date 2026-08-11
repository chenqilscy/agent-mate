# AgentMate

AgentMate is a real, runnable Server Workspace backed by a control plane and one or more device-local Agent execution nodes.
The current build retains only a bounded local-first compatibility layer while obsolete storage/sync code is retired. It was initially informed by a high-fidelity
Tencent WorkBuddy reference prototype, now archived with official-source notes under
[`docs/WorkBuddy/`](docs/WorkBuddy/), and has evolved into an independent product.

**Nothing faked:** streaming output comes from a real LLM, state is persisted, tool traces come from actual calls,
and a catalog card is never treated as proof that a capability works.

## Current status

The working baseline includes:

- React 19 + Vite + TypeScript Server Workspace/Console and a transitional Desktop Companion UI;
- Local Agent execution service with SSE, device-local SQLite, project workspaces and a real tool loop;
- Server-backed projects, work items, Sessions, Runs, delivery acceptance and automation records;
- real Run pause/resume/cancel, ask-user, session-scoped authorization and durable trace replay;
- model, Skill, generic stdio/HTTP-SSE MCP connector management, encrypted local credentials and execution diagnostics;
- multi-assistant support with real Telegram and email channels;
- Tauri 2 shell, PyInstaller sidecar, tray and MSI/NSIS build scaffolding;
- AgentMate Server control plane and its same-origin AgentMate Console; pure-local business writes remain compatibility-only during migration.

The active issue ledger is [`docs/issues/`](docs/issues/README.md), with completed records compacted under its archive.
The Server-first migration is tracked by WB-431 and its child work packages. Two release milestones also remain deferred:
formal production desktop-update deployment needs deployment-owned HTTPS infrastructure, protected signing material and
a production rollout window; the V1 controlled-user pilot needs a fixed beta build, 3–5 target users and five working
days of real-use evidence.

## Architecture

Target architecture:

```text
AgentMate Server ──▶ API · Workspace · Console · business data · Run scheduler
       ▲                                                    ▲
       │ HTTPS / SSE                                        │ outbound lease · event · ACK
       │                                                    │
Web UI                                             Agent execution node
                                           Desktop Companion · Local Agent Core
                                           Runtime · MCP/tools · secrets · WAL
```

Server is the sole authority for persistent business data. Workspace is each user's work surface; Console manages the
system. Local Agent is the background execution node on a personal computer or dedicated worker, while Desktop Companion
is its trusted local control surface. Local Agent is not a second Server API. It owns device-bound secrets, OS permissions, runtime
processes, working copies, unacknowledged event WAL and disposable caches. The current `:8101` Local Agent compatibility
runtime still exposes some transitional App APIs, but its component name and deployment role are fixed. The legacy
`backend/` directory name is retained only as a temporary Python import/source compatibility path.

Workspace is the primary end-user surface. It reads the user's projects, tasks, chats and Runs from Server and exposes
the business actions needed to advance the current work. Console keeps organization policy, project governance, catalog
releases and fleet-wide audit. Desktop Companion keeps only device-bound execution, trusted approval, local files,
credentials, installed capabilities and runtime recovery. The former standalone App business UI is transitional and is
retired page by page only after the corresponding Workspace flow passes real acceptance.

Third-party SkillHub browsing and installation are performed directly by each Desktop Companion. Server may publish a recommendation
pointer and display copy, but does not mirror the marketplace, store SkillHub keys or host third-party skill packages.

Detailed boundaries:

- [documentation map and authority](docs/README.md)
- [current Server-first architecture](docs/agentmate-server-first-架构设计.md)
- [data ownership and transport rules](docs/agentmate-数据分层与同步规范.md)
- [Console architecture](docs/agentmate-console-管理门户设计.md)
- [desktop build and updater status](docs/desktop-build.md)

## Run locally

Prerequisites: Node.js 20+, pnpm and Python 3.11+.

```powershell
# Local Agent dependencies (backend/ is the temporary source compatibility path)
Set-Location backend
python -m venv .venv
./.venv/Scripts/pip.exe install -r requirements.txt
Set-Location ..

# Local Agent (new terminal after installation)
pnpm dev:local-agent                 # http://127.0.0.1:8101

# Desktop Companion UI (new terminal, repository root; transitional dev port)
pnpm install
pnpm dev:app                         # http://127.0.0.1:8102
```

Open Server Workspace at `http://127.0.0.1:8100`. Open `http://127.0.0.1:8102` only for the Desktop Companion and use
“模型管理” to configure a provider or custom model. LLM provider credentials,
API bases, and default model choices are stored in the local per-owner database; they are never placed in frontend
code or required in `backend/.env`.

Settings follow explicit ownership: Console manages platform-wide services and collaboration policy; Desktop Companion
Settings dialog manages this device's Langfuse, local ASR, model credentials, installed capabilities, MCP instances,
runtime behavior and execution diagnostics.
Runtime settings are persisted by their owning service,
take effect without a service restart, and keep secrets write-only. Only deployment/connector settings that explicitly
support environment variables use them as fallbacks.
Database paths, bind ports, cryptographic bootstrap material and release versions remain deployment-only.

### Current development stack

```powershell
./run-stack.ps1
```

This starts Server API + Workspace/Console `:8100`, Local Agent `:8101`, and Desktop Companion UI `:8102`. Pure-local operation remains
available only as a migration compatibility mode; the Server-first target requires Server for business reads and writes,
while Local Agent execution can continue an already leased Run during a bounded outage.

Reusable local Server test-account credentials, when provisioned, are recorded in
`docs/local-test-accounts.md`. That file is intentionally ignored by Git because it contains login passwords; use it
only against the local or explicitly designated controlled-test database.

## Repository layout

```text
src/                 transitional Desktop Companion UI, stores, platform abstraction and global styles
backend/             temporary Local Agent Python source/import compatibility path
server/              independent FastAPI control plane and hosted Console assets
console/             React + Ant Design Server Workspace and Console source
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

After Local Agent runtime changes, hard-restart `:8101` before live verification. Static checks are not a substitute for
real API/browser acceptance.

## SSE contract

One event type maps to one UI shape. The Local Agent contract is defined in `backend/agent/events.py` and consumed in
`src/stores/chatStore.ts`. Changes to events must update both sides and cover persisted-history replay.

## Security summary

- LLM credentials stay in the local owner-scoped DB; other Local Agent/connector secrets may use `backend/.env` where
  documented. Secrets are excluded from source control.
- Workspace paths are resolved inside the active project/assistant sandbox.
- `run_command` is constrained and audited but still runs with Local Agent OS permissions; it is not a VM sandbox.
- Server-origin resources enforce account/project roles; Viewer is read-only.
- During migration, legacy Server sync remains guarded; the target architecture replaces business mirrors with Server
  authority and limits local persistence to secrets, working state, WAL and disposable caches.
