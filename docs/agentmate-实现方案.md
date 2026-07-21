# AgentMate 实现方案

> 状态：当前实现基线，更新于 2026-07-21。
> 历史里程碑、缺陷与验收记录见 [`issues/`](issues/README.md)。腾讯 WorkBuddy 只作为产品与视觉参考，资料集中在
> [`WorkBuddy/`](WorkBuddy/README.md)。

## 1. 产品定位与工程原则

AgentMate 是可真实运行的 local-first 桌面 AI 工作系统。App 在用户本机执行 LLM、工具、MCP
连接器与文件操作；可选的 AgentMate Server 只承担账号、组织、项目协作和能力目录控制面；
AgentMate Console 是 Server 同源托管的 Web 管理界面。

工程上遵守以下边界：

1. 流式回复来自真实 LLM，状态写入 SQLite，轨迹来自真实工具事件；不以静态剧本伪装执行。
2. LLM key 与连接器 secret 只存 App backend 的 `.env` 或按 owner 存本机 DB，不进前端、
   Server、工作区文件或普通子进程环境。
3. 工作区文件、会话正文和工具参数默认只留本机；Server 仅接收被允许的协作元数据。
4. UI 沿用 `src/styles/tokens.css` 与 `src/styles/app.css` 的全局 class/token；暗色主题由
   `body.dark` 覆盖变量。项目没有使用 CSS Modules。
5. 一种 SSE 事件对应一种 UI 形态；事件契约同时维护
   `backend/agent/events.py` 与 `src/stores/chatStore.ts`。
6. 功能是否完成以真实工具、持久化、权限门禁和端到端结果为准，不以目录卡片或提示词为准。

## 2. 当前部署拓扑

```text
AgentMate App（用户本机）
┌──────────────────────────────────────────────────────────────────┐
│ Tauri 2 桌面壳 / 开发期浏览器                                   │
│ React 19 + Vite + TypeScript + Zustand                           │
│              │ REST + SSE                                       │
│              ▼                                                   │
│ FastAPI backend :8101                                            │
│ agent 工具循环 · MCP · SQLite · workspace/projects/<id>/         │
│              │ 可选、guarded、失败回退本地                        │
└──────────────┼───────────────────────────────────────────────────┘
               ▼
AgentMate Server :8100
账号 · 组织 · 项目/成员/角色 · 协作 · AgentMate 能力目录
               │
               └── AgentMate Console（同源 Web 管理界面）

开发期前端 :8102 ── /api 代理 ──▶ backend :8101
```

- `AGENTMATE_SERVER_URL` 为空时是纯本地模式；Server 不可达时，网络调用返回受控失败并保留本地能力。
- 前端只访问本地 backend。登录 Server 时，App backend 代理登录并缓存 Server 身份；浏览器不直接
  依赖 Server 地址。
- Server 不是远程执行器，不读取用户工作区，也不持有 LLM/连接器凭据。
- 第三方 SkillHub 是 App 本地访问的市场：搜索、排行、安装、Key 和技能包不进入 Server。

数据权威与同步细则以 [`agentmate-数据分层与同步规范.md`](agentmate-数据分层与同步规范.md) 为准。

## 3. 代码结构

```text
src/
  views/             页面与工作台
  components/        composer、对话、项目、设置、Server 协作等组件
  stores/            Zustand 状态与 API 编排
  lib/               API、SSE、Markdown、类型和图标
  platform/          Web/Tauri 平台抽象
  styles/            tokens.css + app.css

backend/
  agent/             runtime、事件、工具、沙箱、技能、MCP、调度器
  routers/           App 本地 API 与 Server 代理入口
  auth/              本地身份、Server token 桥与访问门禁
  storage/           SQLite 模型、迁移与 DAO
  mcp_servers/       内置 MCP server

server/
  main.py            独立 FastAPI 控制平面入口
  routers/           账号、组织、项目、协作、目录等 API
  db.py              Server SQLite 与迁移
  web/               legacy Console 与构建后的 React Console 资源

console/             React + Ant Design Console 源码（分阶段迁移 legacy 页面）
src-tauri/           Tauri 2 壳、sidecar、托盘与 updater 脚手架
docs/                当前方案、专项设计、参考资料和 issue 台账
```

Console 技能管理已迁移到 React + Ant Design，其余 legacy 页面按
[WB-236](issues/WB-236-console-remaining-pages-ant-design.md) 继续迁移。生产构建门禁见
[WB-237](issues/WB-237-app-production-build-type-errors.md)。

## 4. App 前端

前端是本地 backend 的状态投影，不自行制造业务真相：

- `chatStore` 消费 SSE 并持久化会话投影；停止、提问恢复、轨迹与 token 用量都来自后端事件。
- `projectStore` / `workItemStore` 管理项目工作台；server-origin 项目的协作实体通过本地 backend
  代理到 Server。
- `catalogStore` 合并 AgentMate 目录下行与 App 本地市场数据，但不接收第三方 SkillHub 镜像。
- `skillStore` 展示磁盘上真实安装的 Skill，安装、编辑、启停和卸载均经 App backend。
- `loadoutStore` 将会话级专家、Skill 与连接器选择传给 runtime；ask 模式不挂工具。
- `src/platform/index.ts` 隔离 Web 与 Tauri API，业务组件不直接依赖原生壳。

Markdown 输出按 `marked → highlight.js → DOMPurify` 处理。任何新增富文本入口都必须沿用同一消毒链路。

## 5. App backend 与 Agent runtime

`backend/agent/runtime.py` 的 `run_chat` 是异步生成器。一次执行的核心流程为：

```text
鉴权与项目访问检查
  → 解析模型、项目指令与会话 loadout
  → 构造工具 schema
  → 调用 OpenAI-compatible LLM
  → 执行真实工具并发射 SSE 事件
  → 继续 function-calling 循环
  → 持久化消息、轨迹、状态与用量
```

基础工具包括目录/文件读写、命令执行、计划更新和向用户提问；Skill 可以绑定受支持的真实工具。
工具注册表同时声明读写/网络/进程等结构化权限、超时和隔离级别；MCP 连接器由
`backend/agent/mcp_client.py` 统一拉起和隔离环境。

安全边界：

- 文件工具使用 `backend/agent/sandbox.py`，路径必须位于当前项目工作区。
- `run_command` 固定工作目录、限时、剔除密钥并受安全策略与审计约束，但它仍以后端 OS 权限运行，
  不能宣称为完整虚拟机级沙箱。
- Viewer 只读；会话、文件、项目和 Server 协作路由按 owner/成员角色检查。
- `ask_user` 在进程内用 `asyncio.Event` 挂起，并由 `/api/chat/{id}/answer` 在原 SSE 执行上恢复。

## 6. 能力模型

### 6.1 专家与专家团

专家是稳定 slug 对应的 persona；运行时必须解析到真实定义后才注入。专家团目录已经使用稳定成员身份，
但“多张专家卡”不等于多 Agent。并行子 Agent、汇总者和可观察调度仍属于后续执行内核能力。

### 6.2 Skill

Skill 包含 `SKILL.md`、可选 `references/`/`scripts/`、工具绑定与本机元数据。目录定义、推荐位和本机安装
是不同生命周期：

- Server 管 AgentMate 自有定义与推荐位；SkillHub 推荐只保存 slug 和展示文案。
- App 本地完成安装并扫描磁盘；未安装内容不能读取本地源码或伪装可运行。
- Server Skill 以不可变 release 发布，状态覆盖 draft/testing/approved/rolling_out/published/
  withdrawn/superseded；未发布 draft 不进入 App 下行。
- App 上报版本与工具契约，Server 做兼容门禁和稳定账号灰度；撤回显式下发 tombstone。
- 安装快照校验文件 hash、工具、权限和 release id；扩大权限的升级必须再次确认。
- 安装/启停状态按 owner 入库，物理包可安全去重；并发操作加锁，最后引用删除进入可恢复回收站。
- runtime 按需读取 manifest 内 resources，总 Skill 指令有预算与冲突优先级；安装/运行结果按 release
  仅上报非敏感聚合指标。

发布模型与剩余扩展边界见 [`agentmate-server-架构设计.md`](agentmate-server-架构设计.md) 的能力发布章节。

### 6.3 连接器

Server 可管理 AgentMate 连接器定义与推荐位，App 保存凭据并在本机启动连接器。内置与已实现的连接器
必须有真实启动 spec 和工具清单；目录展示项不能冒充已连接能力。

### 6.4 助理与渠道

助理持有自己的指令、模型、权限、工作空间和 loadout。Telegram 与邮件渠道已有真实后端；渠道 token
按本机 owner 保存。其它渠道只有完成真实收发、配对/授权、去重与自回复防护后才能标记可用。

## 7. Server、Console 与同步

AgentMate Server 是独立同仓服务，权威管理账号、组织、server-origin 项目、成员角色、邀请、协作数据和
AgentMate 能力目录。AgentMate Console 同源调用 `/api/*`，不直接执行 App 工具。

当前同步基线：

- 登录桥与项目/成员镜像已实现。
- 目录使用显式 `POST /api/server/pull` 全量替换本机 `scope=server` 镜像。
- 项目会话完成后可把不含正文的时间线元数据写入 outbox；后台失败重试，且上报默认关闭。
- server-origin 工作项、里程碑等协作实体采用 Server 代理与本地镜像回退。
- 目录 revision、条件请求、tombstone、客户端 capability report 和兼容门禁已形成闭环；实时推送
  “目录已失效”信号仍未实现，当前由显式/低频 pull 获取。

## 8. 桌面构建与升级

Tauri 2 外壳、PyInstaller sidecar、托盘和 MSI/NSIS 打包链已经存在。updater 插件也已接入下载、安装和
重启代码，但配置仍使用占位 endpoint，UI 没有正式更新入口，发布签名和托管服务尚未上线。

构建与发布要求见 [`desktop-build.md`](desktop-build.md)。Server 发布目录内容不会自动升级 App 二进制；
两者必须通过能力兼容门禁和签名更新服务协同。

## 9. 本地运行

前置：Node.js 20+、pnpm、Python 3.11+。

```powershell
# App backend
Set-Location backend
python -m venv .venv
./.venv/Scripts/pip.exe install -r requirements.txt
Copy-Item .env.example .env
./.venv/Scripts/python.exe main.py       # http://127.0.0.1:8101

# App frontend（新终端，仓库根）
pnpm install
pnpm dev                                 # http://127.0.0.1:8102
```

需要 Server 与 Console 时，可在仓库根执行 `./run-stack.ps1`，启动 `:8100/:8101/:8102` 三层。
不设置 `AGENTMATE_SERVER_URL` 即为纯本地模式。

常用验证：

```powershell
pnpm build
backend/.venv/Scripts/python.exe -m unittest discover -s backend/tests/regression -p "test_*.py"
backend/.venv/Scripts/python.exe -m py_compile backend/main.py server/main.py
```

改 backend 运行时后必须硬重启 `:8101` 再做真实请求验证；文档或静态检查不能替代真机端到端验收。

## 10. 文档职责

| 文档 | 权威范围 |
|---|---|
| 本文 | 当前产品拓扑、代码边界与真实能力基线 |
| [`agentmate-数据分层与同步规范.md`](agentmate-数据分层与同步规范.md) | App/Server 数据权威、隐私红线与同步契约 |
| [`agentmate-server-架构设计.md`](agentmate-server-架构设计.md) | Server 控制平面、Skill 发布实现与扩展边界 |
| [`agentmate-console-管理门户设计.md`](agentmate-console-管理门户设计.md) | Console 管理范围与迁移状态 |
| [`agentmate-助理-架构设计.md`](agentmate-助理-架构设计.md) | 多助理、多渠道数据与运行时边界 |
| [`desktop-build.md`](desktop-build.md) | 桌面构建、签名与更新 |
| [`issues/README.md`](issues/README.md) | 问题、历史里程碑、处理与验证记录 |

当文档冲突时，隐私/同步以数据分层规范为准，运行状态以代码与已关闭 issue 的验证记录为准；发现新冲突
必须先登记 issue，再修正文档和实现。
