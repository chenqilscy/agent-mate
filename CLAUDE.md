# CLAUDE.md

面向 Claude Code 会话的项目工作指南。设置与里程碑背景见 [`README.md`](README.md)，
本文件聚焦**在本仓库怎么干活**：铁律、架构要点、约定、验证方式、issue 流程。

## 这是什么

AgentMate —— 从腾讯 WorkBuddy 的高保真参考原型 [`docs/WorkBuddy/tencent-workbuddy-reference.html`](docs/WorkBuddy/tencent-workbuddy-reference.html) 按方案
[`docs/agentmate-实现方案.md`](docs/agentmate-实现方案.md) 落地的**可真实运行**的桌面 AI-agent 应用。
前端 React 19 + Vite + TS + Zustand（`src/`），后端 Python FastAPI + SSE + 自研 agent 工具循环 + SQLite（`backend/`）。
Local-first：后端跑在用户本机 localhost，浏览器（`:8102` 代理 `/api` 到 `:8101`）只是显示器。

进度：对话/轨迹/项目工作台、自动化、专家/技能/连接器、多助理多渠道、知识库、模型管理与
Tauri 2 桌面外壳均已有真实实现；M7 协作包含真账户鉴权、项目成员·角色·邀请、队友只读可见、
评论/@提及/在线状态、通知和团队时间线。逐项状态以 `docs/issues/` 台账为准。
**AgentMate Server 重构（local-first 执行 + 云端控制平面，epic WB-058，见 [`docs/agentmate-server-架构设计.md`](docs/agentmate-server-架构设计.md)）已完成并验证**：
WB-059 目录真定义入库（内置人格/连接器注册表 → DB，运行时读库）、WB-060 橱窗目录入库（`catalog.ts` → DB + API + 前端 `catalogStore`）、
WB-061 Server 服务骨架（独立同仓 [`server/`](server/)：账号/组织/项目/成员·角色/邀请权威源 + 鉴权签发，FastAPI + SQLite，可单独启动 :8100）、
WB-062 本地⇄Server 同步三期（鉴权桥 / 下行 pull 项目·成员镜像 / 上行 outbox 回传团队时间线）、
WB-063 迁移与 local-first 回退（存量导入 Server、LOCAL_USER↔Server 映射、离线/未登录纯本地全功能）——**全部落地**。
本地 backend 作 Server 客户端：`AGENTMATE_SERVER_URL` 空 = 纯本地零变化，Server 不可达一律回退本地；LLM 凭据/沙箱文件绝不上云、时间线上报默认关。
当前未完成：执行流实时围观、真实多 Agent 专家团、生产能力发布/兼容/灰度闭环、Console 其余页面
React + Ant Design 迁移、正式 Tauri 签名更新服务及 SaaS 生产基建。

## 铁律（不可妥协）

1. **不硬编码、不模拟**。所有流式输出来自真实 LLM；所有状态真持久化（SQLite）；所有 trace 来自真实工具事件。不要为了「看起来能跑」而造假数据。
2. **视觉零重设计**。CSS class 名与设计 token 逐字沿用原型；样式在 `src/styles/{tokens,app}.css`。新组件要**复用既有 class 与 token**，不要引入不协调的硬编码间距/圆角/颜色。
3. **暗色主题 = `body.dark` 上的变量覆盖**。切忌用 `var(--ink)` 之类会在暗色翻转成浅色的 token 当深色背景、或写死浅底深字 —— 这类「白底白字/深底深字」是本项目反复出现的坑（见 WB-004、WB-008）。加了会随主题翻转的组件后，务必在**明暗双主题**下都看一眼。
4. **密钥只存后端、绝不提交**。LLM API Key 只存**后端**——`backend/.env`（`LLM_API_KEY` 等）**或按 owner 存本机 DB**（模型管理 WB-124/128/136：各厂商 base/key 按用户入库，运行时按 owner 解析；`backend/storage/db.py` `get_provider_key`/`set_provider_key`），两者都**绝不进前端**、不透传给子进程环境（见 WB-011）。连接器 / 机器人 token（如 Telegram bot token）存后端 **DB**（已 `.gitignore`、绝不提交）；作为 local-first 本机应用（后端只绑 `127.0.0.1`、token 不出本机），它在**本机设置 UI 内可见可改**（用户显式选择，见 WB-077/093）。
5. **SSE 协议是前后端契约**。一种事件类型 ⇄ 一种 UI 形态。定义在 `backend/agent/events.py`，消费在 `src/stores/chatStore.ts`。加新事件要两端同步。
6. **先登记 issue，再处理**。见下方「Issue 流程」。

## 架构速览

```
浏览器 :8102 ──/api 代理──▶ FastAPI :8101 ──▶ OpenAI 兼容 LLM
 React/Zustand              自研 agent 工具循环
 marked/DOMPurify/hljs      SQLite 持久化 · 每项目沙箱工作区
```

- **agent 工具循环**：`backend/agent/runtime.py` 的 `run_chat` 是异步生成器，OpenAI function-calling 多轮循环，逐事件 `yield` SSE。工具在 `tools.py`（list_dir/read_file/write_file/run_command/update_plan），技能工具在 `skills.py`，MCP 连接器工具经 `mcp_client.py`（官方 mcp SDK stdio 客户端）。
- **沙箱**：`sandbox.py` 用 contextvar 按 project 切工作区根（`workspace/projects/<id>/` 或 `default/`）；路径穿越防护（`resolve()`+`parents` 判定）是可靠的，别绕过它。
- **loadout**：会话级 experts/skills/connectors 由前端 `loadoutStore` 提供，后端 `run_chat` 与项目自身 loadout 合并；ask 模式无任何工具；refs（引用文件）只注入本轮 LLM 输入、不进持久化的 user 消息。
- **ask_user**：agent 调 `ask_user` → runtime 在 `asyncio.Event` 上挂起 → `POST /api/chat/{id}/answer` 在同一条 SSE 流上唤醒，多轮。
- **多用户**：UUID/owner_id/project_id/Role 已进数据模型；M7 起 auth 是**真 Bearer 鉴权**（`backend/auth/`），路由**已按 owner/成员过滤**（WB-013 fixed）——项目/文件/会话按访问权与角色（Owner/Admin/Member/Viewer，Viewer 只读）门禁；本地 backend 多用户隔离加固见 WB-153。纯单机默认注入 `LOCAL_USER`。
- **平台抽象**：UI 不直接 import Tauri，走 `src/platform/`（web 空实现 + 完整 `tauriPlatform` 已接：窗口控制/更新检查，见 `src/platform/index.ts`）。

## 目录

```
src/{views,components,stores,lib,platform,styles}     # 前端
backend/{agent,routers,storage,auth,mcp_servers}     # 后端
docs/                 # 方案 + 原型 + issues/ 台账
.agents/skills/       # 项目内 skill（issue-tracker）
```

## 验证（改完必做）

```bash
npx tsc --noEmit          # 前端类型检查，必须过
npx vite build            # 需要时验证生产构建
cd backend && ./.venv/Scripts/python.exe -m py_compile <改动的 .py>
```

- **改后端运行时逻辑**：手动跑一次相关请求确认。Windows 下 `backend/main.py` 明确使用
  `reload=False`（保证 Proactor 可拉起 MCP 子进程），所以改动后必须**硬重启后端**。
- **改 UI**：尽量用 Playwright 在浏览器实测，**明暗双主题**、必要时窄宽（≤900px 抽屉）都看。
- **临时文件与截图**：放 scratchpad 或仓库根后**提交前删除**；`.gitignore` 已排除 `.env`/`workspace/`/`*.db*`/根 `*.png`/`.playwright-mcp` 等。

## Git

- 在 `master` 上开发。仅当用户要求时提交。
- **共享工作区默认有并发会话**：提交前先看 `git status --short`，不要覆盖、回退或代交不属于当前 issue 的改动。
- **热点共享文件只按 hunk 暂存**：`docs/issues/README.md`、`CLAUDE.md`、注册表、配置、公共类型/API、
  `backend/storage/db.py`、`backend/agent/runtime.py` 等不得直接 `git add <file>`；禁止 `git add .` / `git add -A`。
  非交互环境用精确 patch 配合 `git apply --cached`，它只更新 index，不改工作区；新文件才可按精确路径 `git add`。
- `docs/issues/README.md` 只暂存当前 issue 自己的行；不得删除、改写或代交其他会话的台账行。
- 新建 issue 取号后、提交前都要复核文件名与 README 中的 `WB-###` 是否唯一；撞号时顺延重编并同步两处。
- 提交前必须逐 hunk 阅读 `git diff --cached`，确认只有当前 issue；再运行跨 Windows 的只读门禁：
  `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/audit-staged-commit.ps1 -IssueId WB-###`。
  如需排除已知的其他会话功能关键字，可传 `-ForbiddenPattern '<regex1>','<regex2>'`。脚本会检查敏感文件、跨 issue
  暂存、README 行归属、编号冲突、状态镜像与 whitespace error；任何失败都不得提交。
- commit 信息结尾：`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

## Issue 流程

活动台账在 [`docs/issues/`](docs/issues/)（索引 `docs/issues/README.md`），终态记录合并在 `docs/issues/archive/`。**所有发现的问题先登记成一条 issue（`WB-###`），再处理**。
登记/处理的完整规范由 skill **`issue-tracker`** 定义（`.agents/skills/issue-tracker/SKILL.md`），会话中用 `/issue-tracker` 调起。

- 处理某条时：改为 `in-progress`/🟡 → 按建议修法与验证完成 → 追加处理记录并改为终态 → 运行 `python scripts/archive_issues.py --apply` 合并归档，最后以 `--check` 校验。
- 新编号必须用 `python scripts/archive_issues.py --next-id`，同时覆盖活动文件和归档记录。
- 一条 commit 对应一个（或一组同源）issue，标题带 `WB-###`。
- 顺手发现的新问题**另开 issue**，不夹带进当前修复。

## 已知易踩的坑

- Windows 后端 `reload=False` → 改动后硬重启 `:8101` 进程再验收。
- Windows 终端 GBK 会把中文 JSON 显示成乱码，但底层数据是对的 UTF-8；curl 传中文 body 要写成 UTF-8 文件再 `--data-binary @file`。
- MCP 工具名必须 ASCII；spawn 的 MCP 服务器要强制 `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8`。
- Playwright 触发不了原生 HTML5 拖拽（需派发带共享 DataTransfer 的 DragEvent）；也读不到仓库根以外的上传文件。
