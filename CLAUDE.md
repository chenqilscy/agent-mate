# CLAUDE.md

面向 Claude Code 会话的项目工作指南。设置与里程碑背景见 [`README.md`](README.md)，
本文件聚焦**在本仓库怎么干活**：铁律、架构要点、约定、验证方式、issue 流程。

## 这是什么

WorkBuddy —— 从高保真原型 [`docs/workbuddy-v2.html`](docs/workbuddy-v2.html) 按方案
[`docs/workbuddy-实现方案.md`](docs/workbuddy-实现方案.md) 落地的**可真实运行**的桌面 AI-agent 应用。
前端 React 19 + Vite + TS + Zustand（`src/`），后端 Python FastAPI + SSE + 自研 agent 工具循环 + SQLite（`backend/`）。
Local-first：后端跑在用户本机 localhost，浏览器（`:5173` 代理 `/api` 到 `:8000`）只是显示器。

进度：M0–M5 + §11 项目工作台 A/B/C 已完成并验证；近期完成 ＋菜单 loadout、⌘F 对话内搜索、900px 响应式抽屉。
未做：Tauri 2 外壳打包（需 Rust）、M7 协作。

## 铁律（不可妥协）

1. **不硬编码、不模拟**。所有流式输出来自真实 LLM；所有状态真持久化（SQLite）；所有 trace 来自真实工具事件。不要为了「看起来能跑」而造假数据。
2. **视觉零重设计**。CSS class 名与设计 token 逐字沿用原型；样式在 `src/styles/{tokens,app}.css`。新组件要**复用既有 class 与 token**，不要引入不协调的硬编码间距/圆角/颜色。
3. **暗色主题 = `body.dark` 上的变量覆盖**。切忌用 `var(--ink)` 之类会在暗色翻转成浅色的 token 当深色背景、或写死浅底深字 —— 这类「白底白字/深底深字」是本项目反复出现的坑（见 WB-004、WB-008）。加了会随主题翻转的组件后，务必在**明暗双主题**下都看一眼。
4. **API Key 只存后端 `backend/.env`**（`LLM_API_KEY`/`LLM_API_BASE`/`LLM_MODEL`）。绝不进前端、不提交、不透传给子进程环境（见 WB-011）。
5. **SSE 协议是前后端契约**。一种事件类型 ⇄ 一种 UI 形态。定义在 `backend/agent/events.py`，消费在 `src/stores/chatStore.ts`。加新事件要两端同步。
6. **先登记 issue，再处理**。见下方「Issue 流程」。

## 架构速览

```
浏览器 :5173 ──/api 代理──▶ FastAPI :8000 ──▶ OpenAI 兼容 LLM
 React/Zustand              自研 agent 工具循环
 marked/DOMPurify/hljs      SQLite 持久化 · 每项目沙箱工作区
```

- **agent 工具循环**：`backend/agent/runtime.py` 的 `run_chat` 是异步生成器，OpenAI function-calling 多轮循环，逐事件 `yield` SSE。工具在 `tools.py`（list_dir/read_file/write_file/run_command/update_plan），技能工具在 `skills.py`，MCP 连接器工具经 `mcp_client.py`（官方 mcp SDK stdio 客户端）。
- **沙箱**：`sandbox.py` 用 contextvar 按 project 切工作区根（`workspace/projects/<id>/` 或 `default/`）；路径穿越防护（`resolve()`+`parents` 判定）是可靠的，别绕过它。
- **loadout**：会话级 experts/skills/connectors 由前端 `loadoutStore` 提供，后端 `run_chat` 与项目自身 loadout 合并；ask 模式无任何工具；refs（引用文件）只注入本轮 LLM 输入、不进持久化的 user 消息。
- **ask_user**：agent 调 `ask_user` → runtime 在 `asyncio.Event` 上挂起 → `POST /api/chat/{id}/answer` 在同一条 SSE 流上唤醒，多轮。
- **多用户预埋**：UUID/owner_id/project_id/Role 已进数据模型，但当前 auth 是桩（`backend/auth/`），**路由尚未按 owner 过滤**（见 WB-013）。
- **平台抽象**：UI 不直接 import Tauri，走 `src/platform/`（web 空实现，Tauri 待接）。

## 目录

```
src/{views,components,stores,lib,platform,styles}     # 前端
backend/{agent,routers,storage,auth,mcp_servers}     # 后端
docs/                 # 方案 + 原型 + issues/ 台账
.claude/skills/       # 项目内 skill（issue-tracker）
```

## 验证（改完必做）

```bash
npx tsc --noEmit          # 前端类型检查，必须过
npx vite build            # 需要时验证生产构建
cd backend && ./.venv/Scripts/python.exe -m py_compile <改动的 .py>
```

- **改后端运行时逻辑**：手动跑一次相关请求确认（后端 `main.py` 用 `reload=True`，但历史上出现过「serving stale code」，改动没生效时先**硬重启后端**）。
- **改 UI**：尽量用 Playwright 在浏览器实测，**明暗双主题**、必要时窄宽（≤900px 抽屉）都看。
- **临时文件与截图**：放 scratchpad 或仓库根后**提交前删除**；`.gitignore` 已排除 `.env`/`workspace/`/`*.db*`/根 `*.png`/`.playwright-mcp` 等。

## Git

- 在 `master` 上开发。仅当用户要求时提交。
- 提交前敏感文件自检应为空：
  `git diff --cached --name-only | grep -iE "\.env$|node_modules|\.venv|\.db|/workspace/|\.png$|\.playwright"`
- commit 信息结尾：`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

## Issue 流程

问题台账在 [`docs/issues/`](docs/issues/)（索引 `docs/issues/README.md`）。**所有发现的问题先登记成一条 issue（`WB-###`），再处理**。
登记/处理的完整规范由 skill **`issue-tracker`** 定义（`.claude/skills/issue-tracker/SKILL.md`），会话中用 `/issue-tracker` 调起。

- 处理某条时：把该 issue 与台账状态改 `in-progress`/🟡 → 按其「建议修法」改 → 按「验证」核对 → 改 `fixed`/✅ 并在文件末尾追加「处理记录」。
- 一条 commit 对应一个（或一组同源）issue，标题带 `WB-###`。
- 顺手发现的新问题**另开 issue**，不夹带进当前修复。

## 已知易踩的坑

- 后端 `reload=True` 有时不生效 → 改动没反应就硬重启 `:8000` 进程。
- Windows 终端 GBK 会把中文 JSON 显示成乱码，但底层数据是对的 UTF-8；curl 传中文 body 要写成 UTF-8 文件再 `--data-binary @file`。
- MCP 工具名必须 ASCII；spawn 的 MCP 服务器要强制 `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8`。
- Playwright 触发不了原生 HTML5 拖拽（需派发带共享 DataTransfer 的 DragEvent）；也读不到仓库根以外的上传文件。
