# WorkBuddy 真实实现方案

源于腾讯的WorkBuddy桌面应用

> 从高保真原型（`design/prototype.html`，即 workbuddy-v2.html，约 2200 行单文件）到可运行的真实产品。
> 原则：不硬编码、不模拟——所有流式输出来自真实 LLM，所有状态可持久化，所有轨迹是真实的 Agent 事件。
>
> **文档结构**：正文（第一～十节）是结论与蓝图，是唯一权威；文末「附录 A」是各项选型的论证依据（为什么这么选、否掉了什么、何时重估）。评审先读正文，对某项选型有疑问再查附录对应决策。

---

## 一、目标与范围

原型已经完整验证了交互设计：v5.2.3 的首页/对话/助理/项目/专家中心/自动化/灵感/我的文件八大视图、流式执行轨迹、向用户提问卡、产物面板与文件查看器、新建项目流程、九个弹层系统。真实实现的目标不是重写 UI（原型即视觉规格），而是把三样"假的东西"换成真的：

1. **假流式 → 真流式**：`setTimeout` 逐段吐 HTML 换成 SSE 推送的 LLM token 与 Agent 事件；
2. **假状态 → 真状态**：内存里的 `let` 变量换成 Zustand store + 后端持久化，刷新不丢；
3. **假执行 → 真执行**：写死的 KODA_SEGS 剧本换成真实的工具调用循环（读文件、跑命令、编辑代码），轨迹由事件驱动渲染。

第一阶段（MVP）只做**对话系统**：一个能真实流式对话、渲染 Markdown、展示 Agent 轨迹的核心闭环。项目/专家/自动化等先用真实路由 + 静态数据占位，逐里程碑替换。

## 二、关键技术决策

对齐原型剧情中确认的三个决策，并给出理由与替代方案：

| 决策点 | 选择 | 理由 | 备选 |
|---|---|---|---|
| 前端框架 | **React 19 + Vite + TypeScript** | 组件化承载 9 个弹层 + 3 种对话视图；生态最全；原型的 CSS 可近乎原样迁移为 CSS Modules | Vue 3 + Vite（迁移成本相当，团队熟悉哪个用哪个） |
| 状态管理 | **Zustand** | 轻量、无样板代码；对话流式 append 场景下比 Redux 顺手 | Jotai / Redux Toolkit |
| 后端 | **Python FastAPI + SSE** | 异步流式天然支持；**MCP/Agent 生态重心在 Python**（连接器护城河所在）；类型贯通用 OpenAPI 生成 TS 弥补 | Node.js（团队 Python 弱 / MCP TS 生态追平 / 改 Electron 同进程，满足两条再重估） |
| LLM 接入 | **OpenAI 兼容 API**（`LLM_API_KEY` / `LLM_API_BASE` 环境变量） | 一套接口适配 DeepSeek/GLM/Kimi/MiniMax 等原型模型菜单里的所有模型 | 各厂商原生 SDK（后期做多路由时再引入） |
| Agent 编排 | **MVP 自研薄循环 → 门槛触发后 PydanticAI** | 与自研循环连续（升级非改写）、类型安全、MIT 无商业平台绑定；**放弃 LangGraph**（生产闭环指向付费平台，违背 Local-first） | LangGraph（复杂 DAG 执行图出现时局部引入） |
| Markdown 渲染 | **marked + DOMPurify + highlight.js** | 与原型里"生成"的 package.json 一致；DOMPurify 兜底 XSS | react-markdown（更重但组件化更好） |
| 样式 | **CSS Modules + CSS 变量** | 原型的设计令牌（`--brand:#16B37A` 等）直接平移；深色主题沿用 `body.dark` 变量覆盖 | Tailwind（需重写全部样式，不建议） |
| 桌面壳 | **Local-first：后端即本机服务**，UI 先跑浏览器；**M4 定型 Tauri 2、M5 集成** | 桌面能力（本地文件/终端/本地 MCP）由本机后端提供，与壳无关；壳选型影响后端打包（sidecar），必须在 M4 定 | Electron（仅当后端改 Node 时重评） |

> 每项选型的**完整论证、被否方案与退出条件**见文末「附录 A：架构决策记录（ADR）」。Agent 编排层结论：MVP 自研薄循环，满足「跨进程中断恢复 / 并行子 Agent / 执行图」任意两条门槛时升级为 **PydanticAI**（非 LangGraph——后者生产闭环指向付费平台，违背 Local-first）。技术栈维持 Python（MCP/Agent 生态重心），设有明确退出条件。

## 三、系统架构

### 3.1 部署拓扑：Local-first

核心取舍是 **Agent 运行在用户本机**（读本地文件、跑本地命令、连本地 MCP 都要求进程在本地），而云只承载协作元数据。因此不是"前端 + 云后端"，而是三段式：**本机壳 + 本机后端 + 可选云端 Hub**。M0–M4 用浏览器直连 `localhost` 后端快速迭代（桌面能力一天不缺），M5 用 Tauri 2 套壳；协作版（M7+）才引入 Cloud Hub。

```
╔══════════════ 用户本机（Local Agent，桌面能力所在） ══════════════╗
║ ┌── 壳：Tauri 2（M5 集成，M0–M4 用浏览器替代）──────────────────┐ ║
║ │ 前端 (React 19 + Vite + TS)                                   │ ║
║ │  views/   Home·Chat·Assistant·Projects·ProjExec              │ ║
║ │           ExpertsHub·Automation·Inspire·MyFiles              │ ║
║ │  components/ Composer(＋级联/模型/权限/上下文环)·TraceStream  │ ║
║ │           AskUserCard·OvPanel·PePanel·FileViewer·Popover系统 │ ║
║ │  stores/  chat·ui·task·project·settings·auth (zustand)       │ ║
║ │  platform/ windowControls·tray·notify·shortcut·dialog        │ ║
║ │            └ web 空实现 / tauri 实现（UI 不直接 import Tauri）│ ║
║ └──────────────────────────┬───────────────────────────────────┘ ║
║                    SSE / REST (JSON)，localhost                    ║
║ ┌──────────────────────────┴───────────────────────────────────┐ ║
║ │ 后端 (Python FastAPI，Tauri sidecar 打包)                     │ ║
║ │  auth 中间件（M1 桩 → M7 真账号）· OpenAPI→前端 TS 类型       │ ║
║ │  Agent Runtime：自研薄循环（门槛触发→ PydanticAI）             │ ║
║ │     LLM 循环 · 工具调度 · SSE 事件发射 · stop · token 统计     │ ║
║ │  tools/  read_file·edit_file·run_cmd·web_fetch·find_skills    │ ║
║ │  mcp/    连接器注册表（M5 拉起真实 MCP Server，含 Node 子进程）│ ║
║ │  storage/ SQLite（UUID·owner_id·project_id·role，M1 预埋）    │ ║
║ │  workspace/ 沙箱工作目录（默认权限=仅此目录内读写）            │ ║
║ └───────────────────────────────────────────────────────────────┘ ║
╚═══════════════════════════════┬═══════════════════════════════════╝
                     仅元数据同步（M7+，本地文件/执行细节默认不上云）
╔═══════════════════════════════┴═══════════════════════════════════╗
║ Cloud Hub（协作版 M7+，可选）                                      ║
║  账号/SSO(企业微信) · 项目元数据 · 成员与角色 · 公共连接器(加密)   ║
║  产物元数据+按需上云(5GB) · 消息推送(WS)→消息中心                  ║
╚═══════════════════════════════════════════════════════════════════╝
```

单机模式下 Cloud Hub 不存在，auth 中间件注入固定本地用户——协作是"接上 Hub"，不是"改架构"。

## 四、前端工程设计

### 4.1 目录结构

```
workbuddy/
├─ src/
│  ├─ views/            # 八大页面，一一对应原型 data-view
│  ├─ components/
│  │  ├─ composer/      # Composer.tsx · PlusMenu.tsx · ModelPicker.tsx
│  │  │                 # PermPopover.tsx · CtxUsage.tsx · ModeToggles.tsx
│  │  ├─ chat/          # MessageList.tsx · TraceStream.tsx · AskUserCard.tsx
│  │  │                 # DiffStep.tsx · CodeBlock.tsx · ArtifactGrid.tsx
│  │  ├─ panel/         # OvPanel.tsx · PePanel.tsx · FileTree.tsx · FileViewer.tsx
│  │  ├─ layout/        # MenuBar.tsx · Sidebar.tsx · TaskItem.tsx
│  │  └─ ui/            # Popover.tsx · Modal.tsx · Toast.tsx · Switch.tsx · Chip.tsx
│  ├─ stores/           # zustand：chatStore · uiStore · toastStore · authStore …
│  ├─ platform/         # 抽象层：windowControls·tray·notify·shortcut·dialog
│  │                    #   index.web.ts（空实现）· index.tauri.ts（M5）
│  ├─ lib/              # sse.ts · api.ts · markdown.ts · icons.tsx · api-types.ts(生成)
│  └─ styles/           # tokens.css（设计令牌）· 各 *.module.css
├─ backend/
│  ├─ main.py           # FastAPI 入口
│  ├─ auth/             # middleware.py（M1 固定本地用户桩 → M7 真账号）· deps.py
│  ├─ agent/            # runtime.py（薄循环→PydanticAI）· events.py · tools/
│  ├─ routers/          # chat.py · sessions.py · projects.py · files.py · members.py
│  └─ storage/          # models.py（UUID·owner_id·project_id·Role 枚举）· db.py
├─ src-tauri/           # M5 引入：tauri.conf.json · sidecar 打包配置
├─ .env.example         # LLM_API_KEY / LLM_API_BASE
└─ package.json         # react ^19 · zustand ^5 · marked · dompurify · highlight.js
```

> `src-tauri/` 与 `platform/index.tauri.ts` 在 M0 只留占位，M5 才落地——但 `platform/` 抽象接口 M0 就定义好，UI 层一律走抽象、永不直接 import Tauri，保证套壳零返工。

### 4.2 组件迁移映射（原型 → React）

原型每个交互都有对应组件，迁移时**样式零重设计**（拷贝对应 CSS 块进 module.css，选择器改类名即可）：

| 原型实现 | React 组件 | 迁移要点 |
|---|---|---|
| 9 个 `.pop` 弹层 + `buildPop`/`openSubAt` | 通用 `<Popover anchor dir>` + 各内容组件 | 用 floating-ui 替换手写定位；保留向上/向下、级联飞出、Esc 分级 |
| ＋级联菜单（6 项 + hover 子菜单） | `PlusMenu` + `SubMenu` | hover/click 双触发、根项高亮沿用 `.px-root.on` |
| 模型菜单（Max 开关/倍率/高标/自定义分组） | `ModelPicker` | 模型列表改为 `GET /api/models`，选择写入 settingsStore 并持久化 |
| streamReply / KODA_SEGS 剧本 | `TraceStream` | **改为消费 SSE 事件流**（见第六节），`.cur` 脉动/折叠逻辑保留 |
| 提问卡（1/3 翻页/其他补充/跳过） | `AskUserCard` | 由 `ask_user` 事件驱动挂载；答案 POST 回后端恢复 Agent 循环 |
| 产物面板三视图 + 文件树 + 查看器 | `OvPanel` / `PePanel` / `FileViewer` | 树与文件内容改为 `/api/files` 真实读取；README 走 markdown 管线，代码走行号视图 |
| 侧栏任务/空间实时插入 + 计数 | `Sidebar` + taskStore | 任务来自 `/api/sessions`，"刚刚/2小时前"用相对时间函数 |
| 新建项目弹窗 + 三个挑选器 + 模板预设 | `NewProjectModal` + `Picker*` | 模板/专家/连接器数据改 API；确认 POST `/api/projects` |
| 深浅主题（body.dark 变量覆盖） | `useTheme()` | 令牌不动，加 localStorage 持久化 + 跟随系统选项 |

### 4.3 状态设计（Zustand）

- **chatStore**：`sessions`、`activeSessionId`、`messages[]`（含 `trace: TraceEvent[]`）、`streaming: boolean`、`appendEvent(ev)`——SSE 每来一个事件就 append，React 按事件类型渲染，天然复现原型的逐条流出；
- **uiStore**：当前视图、面板开合、弹层栈（供 Esc 分级：栈顶先关）、主题；
- **taskStore / projectStore**：侧栏任务与空间、项目列表、执行状态徽章（待确认/运行中/完成时间）；
- **toastStore**：全局提示（原型剧情里 Agent 自己创建的那个 toastStore，如今成真）；
- **settingsStore**：当前模型、权限模式（默认/完全访问）、Plan/Ask 开关、上下文用量（后端随事件回传真实 token 统计）；
- **authStore**：当前用户与在各项目中的角色（M1 为固定本地用户桩，M7 接真账号后 UI 零改动）。

## 五、后端设计

### 5.1 REST 接口

所有路由过 auth 中间件（M1 注入固定本地用户，M7 换真实实现，路由零改动）。

```
GET  /api/me                          # 当前用户与角色（authStore；M1 返回本地用户桩）
GET  /api/models                      # 模型列表（含倍率/等级，驱动模型菜单）
GET  /api/sessions?space=…            # 侧栏任务/空间
POST /api/sessions                    # 新任务
GET  /api/sessions/{id}/messages      # 历史回放（kdocs/wps 场景即真实历史）
POST /api/chat                        # 发消息 → 返回 SSE 流
POST /api/chat/{id}/answer            # 提交 AskUser 答案，恢复 Agent
POST /api/chat/{id}/stop              # 停止键
GET  /api/files/tree?root=workspace   # 工作空间文件树
GET  /api/files/content?path=…        # 文件查看器内容（带 mime 判断）
GET  /api/artifacts?session=…         # 产物列表（12 项那种）
POST /api/projects                    # 新建项目（名称/指令/连接器/专家/技能）
GET  /api/projects/{id}/members       # 项目成员与角色（M1 单成员，M7 多成员）
POST /api/projects/{id}/connectors    # 项目公共连接器（Admin，secret 云端加密存储）
GET  /api/usage/{session}             # 上下文用量明细（系统提示词/工具/消息/技能）
```

> 前后端类型契约：CI 由 FastAPI 的 OpenAPI schema 经 `openapi-typescript` 生成 `lib/api-types.ts`，跨语言端到端类型安全，杜绝手写 DTO 漂移。

### 5.2 SSE 事件协议（核心）

轨迹渲染完全由类型化事件驱动，一种事件对应原型里的一种 DOM 形态：

| event | data 示例 | 前端渲染 |
|---|---|---|
| `status` | `{state:"running"}` / `{state:"done",secs:37}` | 「⟳执行中…」↔「已完成 Ns ⌄」，驱动侧栏徽章 |
| `think` | `{text:"深度思考"}` | 灰色思考行（当前项闪烁） |
| `step` | `{tool:"agent-browser",label:"处理agent-browser"}` | 工具步骤行（当前项图标脉动） |
| `file_read` | `{path:"…IndexPage.tsx",range:"L1-末尾"}` | 蓝链 + 范围（点击开文件查看器） |
| `diff` | `{op:"编辑",file:"chatStore.ts",add:1,del:1}` | ✎ 编辑行 + 绿 +N / 红 -N |
| `todo` | `{text:"Rebuild frontend…"}` | 虚线圆 todo 行 |
| `text` | `{md:"前端构建成功！…"}` | 经 marked+DOMPurify 渲染的正文（token 级增量拼接） |
| `ask_user` | `{questions:[{q,options[]}×3]}` | 挂载提问卡；回答走 `/answer`，摘要卡由 `qa_summary` 事件回推 |
| `artifact` | `{name:"README.md",size:"2.4 KB",path}` | 产物卡入网格 + 面板产物区 |
| `usage` | `{pct:3.7,used:36900,detail:{…}}` | 上下文环面板实时数字 |
| `done` | `{}` | 收流、追加操作行与消耗 meta |

### 5.3 Agent Runtime 与权限

**MVP 是自研薄循环（约 300–500 行）**：LLM 输出 → 解析 tool_call → 执行（`read_file / edit_file / run_cmd / web_fetch`）→ 结果回填 → 继续，全程把每步转成上表事件推给前端。本体只有 messages 管理、tool schema 注册、SSE 事件发射、stop 信号、token 统计——权限沙箱与停止键这类产品强需求直接内嵌，不背框架抽象税。

**升级路径**：当满足「跨进程中断恢复 / 并行子 Agent / 执行图分支回滚」任意两条门槛时，把薄循环**升级为 PydanticAI**（非改写——messages/tool schema/结构化输出本就是其核心）。SSE 事件协议 100% 不变，PydanticAI 只管循环内部，不碰前端契约。刻意不选 LangGraph：其生产闭环指向付费平台（LangGraph Platform / LangSmith）并倾向状态托管上云，与 Local-first 冲突。

**中断-恢复**：`ask_user` 事件挂起协程（`asyncio.Event`），前端提问卡答案经 `/answer` 唤醒续跑；待答状态同时以「序列化消息历史 + 待答工具调用」落 SQLite——这正是升级 PydanticAI 后能跨进程恢复的形态（重启重放消息历史即可从断点续跑，对应侧栏"待确认"徽章可隔天再点）。

**权限与模式**：**默认权限 = 工具只能在 `workspace/` 沙箱内操作**，越界操作（如剧情里的完全访问）触发 `ask_user` 请求授权——原型里那个权限开关由此有了真实语义。Plan 模式 = 系统提示词切换为"只规划不执行 + 用 ask_user 确认关键决策"，正是剧情第一幕的真实机制。

## 六、里程碑

> **实现进度（活文档）**：M0–M4 已落地并逐项实测通过——真流式对话、事件驱动全量轨迹（think/step/diff/todo）、文件与产物面板、ask_user 双向闭环（asyncio 挂起/唤醒）、Plan 模式（只读工具）、新建项目落库 + 项目执行 + 变更列表。对照真实产品，"项目"应是**工作台**而非 M4 最小实现的"作用域对话"，深化蓝图见 **第十一节**，下一步从其**阶段 A** 开始。

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| **M0 脚手架**（1–2 天） | Vite+React+TS 初始化、tokens.css 迁移、MenuBar/Sidebar/路由壳、FastAPI hello + SSE echo | 八个视图可切换，样式与原型肉眼无差 |
| **M1 对话 MVP**（1 周） | Composer + `/api/chat` 真流式 + Markdown 渲染 + 停止键 + 会话持久化(SQLite) + 侧栏任务真实增删 + **多用户数据模型预埋**（UUID/owner_id/角色枚举/auth 中间件桩） | 配好 Key 后与真实 LLM 流式对话，刷新不丢历史 |
| **M2 轨迹系统**（1 周） | 事件协议全量落地：think/step/diff/todo/status、折叠、目录（概览含章节）、上下文用量真实统计 | koda 式执行轨迹由真实事件驱动复现 |
| **M3 文件与产物**（3–5 天） | 工作空间树 + 文件查看器（md 渲染/行号代码）+ 产物登记与面板联动 | 点树/产物卡/轨迹蓝链均能打开真实文件 |
| **M4 项目流程**（1 周，✅已落地最小闭环） | 新建项目全流程落库、项目执行视图、ask_user 双向闭环、Plan 模式、变更(diff)列表；框架门槛检查点（结论：维持自研薄循环，暂不升级 PydanticAI）。**项目工作台深化见 §11（阶段 A 为下一步）**；Tauri 2 壳定型顺延至 M5 | 完整重演"分析todo实现方案"剧情但全程真实 |
| **M5 技能与连接器**（1–2 周） | MCP 客户端接入 1–2 个真实连接器（建议先腾讯文档/GitHub）、技能=可注入的提示词+工具包、专家=预设人格；**Tauri 壳集成**（无边框窗口+托盘+sidecar） | ＋菜单里的连接/调用产生真实效果 |
| **M6 打磨** | 深色主题持久化、⌘F 对话内搜索、900px 响应式补全、安装包分发 | — |
| **M7 协作版** | 账号/SSO、Cloud Hub、项目成员与角色、公共+个人连接器双层授权、任务共享与消息推送（消息中心真实事件） | 两名成员在同一项目下各自本地执行、互见任务与产物 |
| **M8 实时围观** | 执行流 fan-out 只读直播 | 成员可实时旁观他人任务的轨迹流 |

## 七、原型功能 → 实现优先级清单

P0 = MVP 必须，P1 = M2–M4，P2 = M5+：

| 功能 | 优先级 | 落点 |
|---|---|---|
| 输入区（＋级联/模型/权限/上下文环/发送-停止） | P0 | M1（上下文环 M2 出真数） |
| 流式回复 + Markdown + 代码块 | P0 | M1 |
| 侧栏任务/空间 + 计数 + 相对时间 | P0 | M1 |
| 执行轨迹全事件（step/think/diff/todo/折叠） | P1 | M2 |
| 产物面板三视图 + 文件树 + 查看器 + 回到底部 | P1 | M2–M3 |
| 项目页 + 新建项目 + 模板预设 + 三挑选器 | P1 | M4 |
| 项目执行视图 + 提问卡 + Q&A 摘要 + 徽章状态机 | P1 | M4 |
| 历史提问弹层 / 分享 / 对话内搜索 | P1 | M2 / M6 |
| 专家中心（专家/技能市场/已安装/连接器） | P2 | M5（先静态数据 M0 占位） |
| 助理页（外部渠道连通） | P2 | M5+（依赖企业微信等回调） |
| 自动化 / 灵感 / 我的文件云端网盘 | P2 | M5+ |
| 消息中心 / 升级横幅 / 个人面板 | P2 | M6 |

## 八、工程注意事项

安全上有三条硬线：LLM 输出必须经 DOMPurify 才能进 `dangerouslySetInnerHTML`；`run_cmd/edit_file` 严格锁在 workspace 沙箱且记录审计事件（对应"变更(57)"）；API Key 只存后端 `.env`，前端永不接触。性能上注意两点：长轨迹（几百个事件）用虚拟列表或分段折叠渲染；SSE 断线重连要带 `last_event_id` 续传。数据层从 M1 起按多用户预埋（UUID 主键、owner_id/project_id、角色枚举、auth 中间件桩），协作拓扑为 Local Agent + Cloud Hub（详见附录 A.3）。工程习惯上，原型文件保留为 `design/prototype.html` 进仓库——它就是活的视觉验收标准，每个组件做完对着它逐像素核对。

## 九、本地启动（目标形态）

```bash
# 1. 配置 API Key
cd workbuddy/backend
cp .env.example .env   # 填入 LLM_API_KEY 和 LLM_API_BASE

# 2. 启动后端
python3.11 main.py

# 3. 启动前端（新终端）
cd workbuddy && pnpm install && pnpm dev

# 4. 打开浏览器 → http://localhost:5173
```

## 十、下一步

从 M0 开始：初始化仓库 → 迁移设计令牌与 MenuBar/Sidebar → 打通第一条 SSE echo。M0+M1 完成后就拥有一个"真的 WorkBuddy 核心"，剩下的是按清单逐项把原型里的每个交互接上真实数据。

> **进展更新**：M0–M4 已完成。下一阶段按第十一节的**项目工作台深化**推进，从阶段 A 起。

## 十一、项目工作台深化（M4+：从"作用域对话"到"工作台"）

> 背景：M4 把"项目"实现为一个**作用域对话**（会话带 `project_id`、注入项目指令），这是最小闭环。对照真实产品截图，"项目"应是一个**工作台**——主页 + 四标签 + 常驻配置侧栏 + 独立工作空间，执行/对话只是项目下的一个子项。本节把这一深化定为权威蓝图。

### 11.1 核心模型：项目 = 工作台

项目主页由四部分组成：

- **面包屑**：`项目 / <项目名>`，右上「邀请」（成员 = M7）
- **四标签**：
  - **动态**：成员操作时间线（由消息/事件的 `actor` 字段驱动——M1 已预埋；单机先做"我的动态"，多人 = M7）
  - **计划**：看板（待开始 / 进行中 / 暂停 / 完成），卡片 = 工作项
  - **任务**：工作项列表（私密/共享），与看板同源
  - **资产**：项目云盘（文件夹 / 上传 / 下载 / 配额 / 类型筛选）+ 富文件查看器
- **常驻「项目配置」侧栏**：指令(可编辑) · 连接器 · 专家 · 技能 · 自动化
- **执行是子项**：一个项目下可发起多个执行会话（如"分析todo实现方案"），左侧栏按项目分组挂在其空间下

### 11.2 独立工作空间（每项目一份沙箱）

对齐"项目=云端逻辑容器，workspace=每人本地检出（类 git 心智模型）"（见 A.3）：

- 项目会话 → `backend/workspace/projects/<project_id>/`
- 普通对话 → `backend/workspace/default/`
- 实现：`contextvar` 按请求设置当前 workspace 根，`agent/sandbox.py` 与所有工具读它（工具签名不变）；`/api/files/*` 增加 `?session=` / `?project=` 作用域参数
- 收益：产物 / 变更 / 文件树 / 资产都只看本项目，互不污染（当前 M4 为全局共享，是待补的简化）

### 11.3 数据模型与 REST 追加（并入 5.1 契约）

- `projects` 表已建（M4）。追加：
  - `GET  /api/projects/{id}` — 项目详情（含配置）
  - `PATCH /api/projects/{id}` — 编辑指令 / 连接器 / 专家 / 技能
  - `GET  /api/projects/{id}/sessions` — 项目下执行会话（左栏分组 / 动态来源）
- 新增 `work_items` 表（阶段 B）：`id · project_id · owner_id · title · status(待开始/进行中/暂停/完成) · source · assignee(actor) · created_at`。看板与任务列表同源。
  - `GET/POST /api/work-items`，`PATCH /api/work-items/{id}`（拖拽改状态）
- 资产复用项目 workspace（阶段 C）：`GET /api/files/tree?project=…`、`POST /api/files/upload?project=…`、下载/重命名/删除；配额为软限制展示。

### 11.4 分阶段完善路线

| 阶段 | 内容 | 验收 |
|---|---|---|
| **A 项目结构**（下一步先做） | ① 每项目独立工作空间（contextvar 作用域）；② 项目主页四标签壳 + 常驻「项目配置」侧栏（指令等可编辑，PATCH 落库）；③ 侧栏执行会话按项目分组；执行降为项目子视图 | 打开项目见工作台；改指令即改 Agent 行为；产物/文件只看本项目 |
| **B 工作管理** | 计划(看板拖拽) + 任务(工作项列表)，`work_items` 落库，状态机 | 卡片可新建/流转，任务列表与看板同源 |
| **C 资产** | 资产标签 = 项目云盘（列表/上传/下载/重命名/删除/配额）+ 富文件查看器（操作菜单/分页/字数） | 上传/下载/改名真实生效，查看器带操作 |
| **D 协作**（归入 M7） | 成员动态、邀请/成员与角色、共享、消息推送 | 两成员同项目互见（依赖 Cloud Hub） |

阶段 A 是骨架，也顺带解决独立工作空间；B/C 为独立大功能逐个加；D 归入 M7 协作版。

---

# 附录 A：架构决策记录（ADR）

> 本附录只回答"**为什么这么选、否掉了什么、何时该重估**"。结论以正文为准，冲突以正文为准，本附录只补论证。

### A.1　决策一：桌面应用 vs Web —— 本系统如何取舍

#### 结论

**桌面能力不可妥协，但桌面"壳"可以后置**。采用 **Local-first 架构**：后端从 M0 起就是跑在用户本机的 localhost 服务，浏览器只是临时的显示器；**壳选型在 M4 定型为 Tauri 2，M5 完成集成**——修正原方案"M6 后再评估"的排期错误。

#### 论证

先分清两件事。WorkBuddy 的桌面属性里，真正构成产品价值的是**桌面能力**，而不是桌面外观：

| 桌面属性 | 归类 | 纯 Web（云后端）能做吗 |
|---|---|---|
| 读写本地文件（原型轨迹里的 `D:\work\qp\koda\...`） | 能力 | ❌ |
| 执行本地命令（`pnpm dev`、`python3.11 main.py`） | 能力 | ❌ |
| CDP 直连本地 Chrome（Web Access 技能）、本地 stdio MCP | 能力 | ❌ |
| 默认权限 = 本机 workspace 沙箱 | 能力 | ❌（沙箱在云端就变味了） |
| Windows 菜单栏 / 窗口控制 / 托盘 / 全局快捷键 | 外观与系统集成 | 部分（原型已用 DOM 模拟菜单栏） |

"执行即交付"的核心场景全部落在左列——**Agent 操作的是用户自己的机器**。所以云后端 + 纯 Web 的路线直接排除。

但注意：这些能力来自"后端进程跑在本机"，与有没有壳无关。**浏览器访问 `localhost:5173`、后端跑在 `localhost:8000`，这个组合在能力上已经是一个桌面应用**——只是外观上多开了个浏览器标签。这就是 Local-first 架构的取舍：M0–M4 用浏览器承载 UI 快速迭代（热更新、DevTools、零打包成本），桌面能力一天不缺；壳只解决"看起来/用起来像原生应用"的最后一层。

壳的排期为什么必须提前到 M4：**壳的选型决定后端打包方式**（Tauri sidecar 拉起 PyInstaller 单文件，或 Electron 主进程管理子进程），影响进程生命周期管理、日志路径、更新机制。拖到 M6 后评估，意味着 M5 做的 MCP 进程管理可能按错误假设实现，返工面大。

壳选型对比（目标平台以截图为准：Windows 优先）：

| 维度 | Tauri 2 | Electron |
|---|---|---|
| 安装包体积 | ~10 MB | ~150 MB |
| 内存占用 | 低（系统 WebView2） | 高（自带 Chromium） |
| Python sidecar | 官方 sidecar 机制 | 手动 child_process |
| 渲染一致性 | Windows 用 WebView2（即 Chromium），风险低 | 完全一致 |
| 加分场景 | 安全模型、自动更新、托盘 | 后端若是 Node 可同进程 |

**选 Tauri 2**。唯一的重新评估触发条件：若决策二最终把后端换成 Node，则 Electron 重新入场。

#### 工程落点

- 新增 `src/platform/` 抽象层：`windowControls / tray / notify / globalShortcut / fileDialog` 五个接口，提供 web 空实现与 tauri 实现，UI 层永不直接 import Tauri API；
- 原型的 DOM 菜单栏**原样保留**：Tauri 用无边框窗口，最小化/最大化/关闭三个按钮通过 IPC 接到真实窗口控制——与原型像素一致，这也是保留 DOM 菜单栏而非用系统菜单的原因；
- 打包链：`pnpm build` → 前端静态资源；`pyinstaller --onefile main.py` → 后端 sidecar；`tauri build` → 安装包。

---

### A.2　决策二：后端 LLM 框架如何选

#### 结论

分三层决策：服务框架 **FastAPI**（已定）；模型接入层 **OpenAI 兼容直连，倍率/多供应商需求出现时引入 litellm 适配层**；Agent 编排层 **MVP 自研薄循环（约 300–500 行），设定明确的框架引入门槛，触发后引入 PydanticAI**（取代原定的 LangGraph）**，仅用于结构化工具循环与类型安全的中断-恢复**。

#### 论证

**为什么 MVP 不上 LangChain/LangGraph 这类框架**：本产品的差异化恰恰在于**事件协议与 UI 的一一对应**（think/step/diff/todo/ask_user/artifact 十一种事件 → 原型里十一种 DOM 形态）。框架有自己的事件流（如 LangGraph 的 `astream_events`），用了框架等于要写一层"框架事件 → 我们的事件"的翻译器，抽象税双倍。而一个自研工具循环的本体只有：messages 管理、tool schema 注册、SSE 事件发射、stop 信号、token 统计——300 行级别，完全可控，权限沙箱和停止键这类产品强需求直接内嵌。

**但要写清楚什么时候必须上框架**，避免自研循环无限膨胀。框架引入门槛（满足任意两条即引入）：

1. **中断-恢复需要跨进程持久化**：ask_user 挂起后，后端重启仍能从断点恢复执行（对应侧栏"待确认"徽章可以隔天再点）；
2. **并行子 Agent**：一个任务同时派发多个子执行流并汇聚（原型 v1 的多 Agent 演示如果回归）；
3. **执行图分支/回滚**：计划模式产出的 plan 需要按 DAG 执行、失败节点重试。

触发后引入 **PydanticAI**。原方案定的是 LangGraph，现改选 PydanticAI，理由如下：

**为什么放弃 LangGraph**：`langgraph` 开源库本身是 MIT 免费的，但它的**生产闭环强烈指向商业产品**——持久化/可观测/调试一路被引导到 LangGraph Platform 与 LangSmith（托管、按量计费）。对一个 **Local-first、数据必须留在用户本机**的产品，这种"自托管能跑但顺着走就付费、且倾向把状态托管到云"的绑定方向本身就是反模式。框架对比表中 LangGraph 的隐性成本列标注"生产部署几乎必须付费平台"，印证了这一点。

**为什么选 PydanticAI**（隐性成本最低的那一档）：

| 维度 | PydanticAI | LangGraph |
|---|---|---|
| 许可与成本 | MIT，纯库，无配套商业平台绑定 | 库 MIT，但生产可观测/持久化指向付费平台 |
| 设计哲学 | 薄、类型安全、"像写 FastAPI 一样写 Agent" | 图编排为中心，抽象较重 |
| 与自研循环的连续性 | 高——本就是"给薄循环加类型与工具编排"，几乎是我们 MVP 循环的规范化版本 | 低——需把循环重构成 StateGraph |
| 中断-恢复 | 支持 tool 内触发人工介入 + 消息历史序列化，落 SQLite 即可跨进程恢复 | checkpointer 语义完善，但与其平台生态耦合 |
| 供应商中立 | 原生多模型（OpenAI 兼容/各家），与决策的 OpenAI 兼容层一致 | 需经 LangChain 模型层 |
| 事件流归属 | 我们自己的 SSE 协议不变，PydanticAI 只负责循环内部 | 需写 astream_events → 自有事件的翻译层 |

关键优势是**连续性**：MVP 的自研薄循环长大后"升级"成 PydanticAI，而不是"改写"成另一套图模型——messages 管理、tool schema、结构化输出本就是 PydanticAI 的核心，我们只是把手写的部分换成它的规范实现。**ask_user/待确认徽章**用"工具触发人工介入 + 序列化消息历史落 SQLite"实现跨进程恢复；**SSE 事件协议 100% 仍是我们自己的**，PydanticAI 只管循环内部，不碰前端契约。

若未来真出现 LangGraph 才擅长的复杂 DAG 执行图（多分支回滚、大规模并行编排），再局部引入亦不冲突——但以本产品的形态，PydanticAI 覆盖面已足够，且不背商业化包袱。

其余框架的定位：**litellm** 作为可选的模型适配层（模型菜单里的倍率计费、Max 模式路由、多供应商故障转移，M2 按需评估）；**LlamaIndex** 只在 M5 做 ima/乐享知识库检索时按需引入（RAG 专长，不参与 Agent 循环）；**AutoGen / CrewAI 不采用**——多智能体编排的控制权和事件流都不匹配我们"UI 即事件消费者"的架构。

**与决策一的耦合**（这正是你指出排期问题的价值）：Python 后端在桌面形态下以 PyInstaller sidecar 交付，Tauri 官方支持该模式，链路已验证可行。备选的"全 Node 路线"（Fastify + Vercel AI SDK，Electron 同进程托管）在语言统一上有优势，但会失去 MCP 官方 Python SDK 和 Python agent 工具生态——除非团队 Python 能力空缺，否则不建议切换。

#### ask_user 的两阶段实现示意

自研循环阶段：Agent 发出 `ask_user` 事件 → `asyncio.Event` 挂起协程 → 前端提问卡 POST `/api/chat/{id}/answer` → 唤醒续跑；同时把待答状态落库，**进程重启后无法恢复协程**——这个局限被触发时，就是切换 PydanticAI 的时机：把执行状态收敛为「序列化的消息历史 + 待答工具调用」落 SQLite，重启后重放消息历史即可从断点续跑（门槛条件 1）。

---

### A.3　决策三：多用户协作——方案是否考虑了

#### 结论

原方案确实没有展开，这是疏漏——产品自身已经明示了协作需求（项目页副标题"多人协同，打造超级团队"；添加连接器弹窗文案"添加后**成员**可使用**个人账号**授权连接……可在创建项目完成后配置**公共连接器**"）。补齐策略：**单机先行，协作预埋**——MVP 不做账号系统，但数据模型与 API 从 M1 起就按多用户设计；协作功能作为新增的 M7/M8 里程碑交付。

#### 论证

预埋的成本几乎为零，反向补救的成本极高（全量数据迁移 + 全 API 改造）。M1 起强制执行的预埋清单：

- 全部表用 **UUID 主键**，业务表统一携带 `owner_id` 与 `project_id`（单机模式下填固定的本地用户）；
- 定义 `Role` 枚举：`Owner / Admin / Member / Viewer`，项目成员表建好但暂时只有一行；
- 所有 API 过 **auth 中间件**，dev 模式注入固定用户桩——上线账号系统时只换中间件实现，路由零改动；
- 每条轨迹事件与产物记录带 `actor` 字段（为未来的团队时间线准备）。

**拓扑：Local Agent + Cloud Hub**。协作与 Local-first 并不冲突，关键是分清什么在本地、什么上云：

```
每个成员的本机                          Cloud Hub（协作版新增）
┌─────────────────────┐               ┌──────────────────────────┐
│ Local Agent(FastAPI)│  ←── 同步 ──→ │ 账号(SSO/企业微信)        │
│ workspace/ (本地检出)│               │ 项目元数据 · 成员与角色    │
│ 个人连接器 token(加密)│               │ 共享指令/技能/公共连接器   │
│ 执行·轨迹·本地产物   │               │ 产物元数据+按需上云(5GB)   │
└─────────────────────┘               │ 消息推送(WS) → 消息中心    │
                                      └──────────────────────────┘
```

- **项目 = 云端逻辑容器，workspace = 每人本地检出**（类 git 心智模型）：两个成员在同一项目下各自本地执行，互不阻塞；产物按需上传（对应原型"云端网盘 880KB / 5GB"）；
- **连接器双层授权**，与原型文案一一对应：项目**公共连接器**（Admin 在项目创建后配置，secret 云端加密存储）与成员**个人授权**（各自 OAuth，token 只加密存本地、云端仅记授权状态）；
- 隐私边界：本地文件与执行细节默认不上云，只有显式产物与元数据同步。

**协作深度分级**，逐级交付、不过度设计：

| 级别 | 内容 | 里程碑 |
|---|---|---|
| L0 异步共享 | 项目/指令/技能配置云端同步，成员看到彼此的任务列表与产物 | M7 |
| L1 任务可见与通知 | 任务状态变更 WS 推送（消息中心从此有真实消息）、@成员 | M7 |
| L2 同会话围观 | 一个成员的执行流实时 fan-out 给其他成员（只读直播） | M8 |
| L3 指令共同编辑 | CRDT（Yjs）级实时协同编辑 | 远期，暂不承诺 |

---

### A.4　决策四：后端技术栈必须是 Python 吗

#### 结论

**不是"必须"，但对本产品是当前最优，维持 Python。** 前端 TypeScript 不动。语言选择的决定权在**生态**而非偏好，给出正面论证、Node 全栈的代价、以及一个明确的退出条件。

#### 论证

先明确：这里只讨论**后端 Agent 服务**的语言。前端已是 React+TS，无争议。候选是 Python（FastAPI）与 Node/TS（Fastify + Vercel AI SDK）。

**选 Python 的正面理由**，全部落在"别人替我们写好了、且只在 Python 侧成熟"的生态上：

| 能力 | Python 生态 | Node/TS 现状 |
|---|---|---|
| MCP 协议（连接器的根基，M5 主线） | 官方 `mcp` SDK 成熟，社区连接器多为 Python stdio（原型里的 kdocs-mcp 即是） | 有 TS SDK，但社区 server 以 Python 为主，跨语言拉起子进程反而更绕 |
| Agent 编排 | PydanticAI / 自研循环生态完整 | Vercel AI SDK 偏"模型调用+流式"，多步工具循环需自己补 |
| 本地能力 | 文件/子进程/CDP/数据科学工具链齐全 | 文件与子进程同样能做，数据类工具弱 |
| 模型接入 | openai sdk + litellm，OpenAI 兼容一套通吃 | Vercel AI SDK 体验好，能力等价 |

对 WorkBuddy 而言，**M5 的连接器与技能是产品护城河，而它们的重心在 Python MCP 生态**——这是天平决定性的一侧。原型里 Agent 读写的 kdocs-mcp、Web Access、各类套件，社区实现大量是 Python stdio server；后端用 Python，等于和这些 server 同语言，进程管理、类型、调试都顺。

**Node 全栈（前后端同 TS）值不值**：诱惑是"一种语言、类型贯通、共享 DTO"。代价是：把 MCP 与 Agent 工具生态里最成熟的一侧换成较弱的一侧，为了语言统一牺牲能力供给——对一个能力密集型 Agent 产品不划算。而"类型贯通"的收益可用更轻的方式拿到：**前后端契约用 OpenAPI 自动生成 TS 类型**（FastAPI 原生出 OpenAPI schema → `openapi-typescript` 生成前端类型），跨语言也能端到端类型安全，SSE 事件同样可定义 schema 共享。

**与决策一/二的一致性**：决策一定了 Python 后端以 PyInstaller sidecar 随 Tauri 打包（链路已验证）；决策二的 PydanticAI 是 Python。三者自洽，无需为语言再做妥协。

**退出条件（什么时候该重估为 Node）**：满足任意两条即重新评估——① 团队 Python 工程能力显著弱于 TS，维护/招聘成本主导；② MCP 的 TS SDK 与社区 server 生态追平甚至反超 Python；③ 决策一最终改用 Electron 且强烈希望后端与主进程同语言同进程。当前三条都不成立，故维持 Python。

#### 落点

- 前后端类型契约：CI 里由 FastAPI 的 OpenAPI schema 生成前端 TS 类型，杜绝手写 DTO 漂移；
- Python 版本锁 3.11+（原型启动脚本即 `python3.11 main.py`），保证 sidecar 打包与 asyncio 表现一致；
- 若某个连接器只有 Node 实现，作为独立 MCP 子进程由 Python 后端拉起即可——MCP 本就是跨语言进程协议，不构成换语言的理由。

---


---

### A.5　里程碑影响索引

本文各决策对里程碑的影响（完整 M0–M8 总表见主方案第六节，此处只列因决策产生的变化点）：

- 决策一 → M0 新增 `platform/` 抽象层骨架；M4 定型 Tauri 壳、M5 集成（原"M6 后评估"作废）。
- 决策二 → M4 结束设框架门槛检查点，决定 M5 前是否将薄循环升级为 PydanticAI。
- 决策三 → M1 起数据层多用户预埋；新增 M7（协作版 L0+L1）、M8（实时围观 L2）。
- 决策四 → 无新增里程碑；约束后端语言与 sidecar 打包方式，与决策一/二自洽。
