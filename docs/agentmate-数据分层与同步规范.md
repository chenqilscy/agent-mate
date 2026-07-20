# AgentMate 数据分层与同步规范

> 状态：v1（2026-07-10 立）。本规范是 **AgentMate App ⇄ AgentMate Server** 之间“哪些数据上云、哪些留本地、怎么同步”的**唯一准绳**；Console 是 Server 的 Web 管理界面。
> 新增任何实体前，先按 §5 的决策流程给它归层，再写代码。相关落地见 epic [WB-112](issues/WB-112-manager-positioning-data-spec.md)。

## 0. 定位

- **AgentMate App**（本地 backend `:8101` + React `:8102`）：**local-first 执行端**。用户实际干活的地方，离线可用。是前端的**唯一入口**（前端只连本地 backend）。
- **AgentMate Server**（`:8100`，目录 `server/`）：**中心 API / 控制平面**。账号·组织·项目·成员·协作的**权威源**，多端统一管理。它**不执行**任务、**不持有**凭据。
- **AgentMate Console**：由 Server 同源托管的 **Web 管理控制台**，通过 Server API 管理上述数据；它不是独立数据源或独立服务。

一句话：**App 干活、Server 管协作数据、Console 提供 Web 管理界面**。本地 backend 内嵌一个 guarded Server 客户端，对“协作实体”做读镜像+写代理，对“私有实体”一律不上云。

## 1. 三条不可妥协的红线（哪些**永不**上云）

1. **LLM 凭据 / 连接器 secret**：`LLM_API_KEY`、bot token、OAuth 令牌等。只存 App 本地（`backend/.env` 或本地 DB），绝不进 Server、绝不进前端、绝不透传子进程。
2. **沙箱工作区文件（资产/云盘）**：`workspace/projects/<id>/` 下的一切文件本体。属用户私有产物，只在本机。
3. **会话正文（消息/工具轨迹）**：对话内容、工具调用参数与返回。只以**元数据**（一条 timeline 事件：谁、在哪个项目、干了什么、何时）上行 Server，正文不上云。

> 违反以上任一条即为 P0 事故。任何"顺手上传一下"的便利都不能突破。

## 2. 数据分层总表

**权威源**列 = 谁是真相源；**上云**列 = 是否进 Server 的 DB；**同步**列 = 数据流向；**离线**列 = App 未连 Server 时的行为。

| 实体 | 权威源 | 上云 | 同步方向 | 离线行为 | 现状 |
|---|---|---|---|---|---|
| 账号 accounts | **Server** | ✅ | Server→App 镜像 | 回退本地匿名 `LOCAL_USER` | ✅ 已打通 |
| 组织 orgs / 成员 | **Server** | ✅ | Server→App 镜像 | 只读缓存 | ✅ |
| 项目 projects（元信息/角色） | **Server**（server-origin） | ✅ | 双向 | 本地原生项目纯本地 | ⚠️ 成员/配置写未回传（WB-112 修） |
| 项目邀请 invites | **Server** | ✅ | Server 权威 | 无 | ✅（App UI 未接，WB-112） |
| **任务 work_items（计划/任务）** | **Server**（server-origin） | ✅ | 双向：读镜像+写代理 | Server 不可达回退本地 | ✅ 已打通 |
| **里程碑 milestones** | **Server**（server-origin） | ✅ | 双向 | 同上 | ✅ |
| 任务活动流 work_item_activity | **Server** | ✅ | Server 逐条留痕 | 无 | ⚠️ App 未回读（WB-112） |
| 团队动态 timeline_events | **Server** | ✅（仅元数据） | App→Server 上行 push | 本地 sessions 兜底显示 | ⚠️ 未回读，队友动态互不可见（WB-112） |
| 讨论 comments / @提及 | **Server** | ✅ | Server 代理 | 无离线态 | ✅（设计取舍） |
| 在线状态 presence | **Server** | ✅ | Server | 无 | ✅ |
| 目录 catalog（人格/连接器/技能橱窗） | **Server** | ✅ | Server→App 下发 | 本地 builtin 兜底 | ✅ |
| **资产/文件 assets** | **App 本地** | ❌ | 不同步 | 全功能 | ✅ 故意不上云（红线 2） |
| 自动化 automations | **App 本地** | ❌ | 不同步（暂） | 全功能 | 未上云；是否需团队级待定 |
| 助理/频道 channels | **App 本地** | ❌ | 不同步 | 全功能 | 私有 |
| 会话 sessions/messages | **App 本地** | ❌（仅元数据上行） | 见红线 3 | 全功能 | ✅ |
| LLM 凭据 / secret | **App 本地** | ❌ | 永不 | 全功能 | ✅ 红线 1 |

## 3. 同步契约（协作实体怎么同步）

以 `work_items` 为**唯一样板**，所有"上云协作实体"都应遵循同一模式（见 [backend/routers/work_items.py](../backend/routers/work_items.py)）：

1. **归属判定**：仅当 ①Server 已启用（`AGENTMATE_SERVER_URL` 非空）②请求带 Bearer token ③项目 `origin=="server"` 三者同时成立，才走云端；否则纯本地。
2. **读 = 代理 + 镜像**：从 Server 拉取 → 覆盖本地镜像（离线兜底 + 让后续按 id 定位）→ 返回云端视图。Server 不可达 → 读本地镜像。
3. **写 = 代理 + 刷新**：先校验角色（Viewer 只读）→ 代理到 Server → 成功后重拉刷新镜像。Server 不可达 → 回退本地写（离线优先，红线不适用于协作元数据）。
4. **镜像合并**：**目标**是按 `id + updated_at` 增量合并、冲突可见（last-write-wins by timestamp）。**现状**是"整表删插"（离线并发会丢改动），列为 WB-112 待修项。

> 铁律：**协作实体的写，凡 server-origin 项目，必须代理到 Server**。只写本地 = 下次 pull 被覆盖 = 静默丢数据。当前 `projects`/`members` 违反此条，须补齐。

## 4. 统一用户与身份规范

- **单一账号权威**：Server 是**唯一**账号系统。App 登录即用 Server 账号身份，**app token == Server token**；本地 `users` 表用 **Server account id 作本地 id** 镜像（`upsert_external_user`）。全端一个用户体系。
- **本地匿名映射**：未登录 Server 时用本机 `LOCAL_USER`（`0000…0001`）。首次登录/导入时 `set_server_link` 记录 `LOCAL_USER ↔ Server account`，存量本地数据归到该云账号。
- **人归属必须强映射**：任务负责人、动态 actor 等“谁”字段，**权威值一律是 Server `account_id`**，显示名由成员表解析。
  - **现状缺陷**：`work_items.assignee` 是自由文本、Server 表无 `owner_id` 列 → 协作下“谁负责”对不准、无法按人过滤/统计。**WB-112 P1 修**：`assignee` 升级为 account_id 外键 + 存量迁移。
- **角色权威**：Owner/Admin/Member/Viewer 由 Server 定义，App 镜像后本地访问控制（`project_access_role`）自动生效；写操作按角色 gate，Viewer 只读。

## 5. 新增实体的归层决策流程

加任何新实体/新功能前，依次自问：

1. **含红线数据吗？**（凭据 / 文件本体 / 会话正文）→ 是则**必须本地**，最多上行元数据。停。
2. **需要多人共享/协作看到吗？** → 否则**本地**（如个人助理、自动化脚本）。
3. **需要跨端/跨设备统一管理吗？**（账号、项目、成员、任务）→ 是则 **Server 权威**，按 §3 契约做读镜像+写代理，并保证离线回退；Console 只是管理这些数据的 Web 界面。
4. **归 Server 的，人归属字段一律用 account_id**（§4），不要再引入自由文本的“谁”。

> 默认倾向：**能本地就本地**（隐私 + 离线 + 简单）；只有"协作/统一管理"这条硬需求才上云，且上云就要把 §3 契约做全（写代理 + 离线回退 + 增量合并），不做半套。
