# AgentMate 数据分层与同步规范

> 状态：v3（2026-08-03 修订）。本规范是 **AgentMate App ⇄ AgentMate Server** 之间“哪些数据上云、哪些留本地、怎么同步”的**唯一准绳**；Console 是 Server 的 Web 管理界面。
> 新增任何实体前，先按 §5 的决策流程给它归层，再写代码。相关落地见 epic [WB-112](issues/archive/2026/WB-100-199.md#wb-112)。

## 0. 定位

- **AgentMate App**（本地 backend `:8101` + React `:8102`）：**local-first 执行端**。用户实际干活的地方，离线可用。是前端的**唯一入口**（前端只连本地 backend）。
- **AgentMate Server**（`:8100`，目录 `server/`）：**中心 API / 控制平面**。账号·组织·项目·成员·协作的**权威源**，多端统一管理。它**不执行**任务；只持有 SSO/中央服务等控制平面凭据，不持有本机任务执行凭据。
- **AgentMate Console**：由 Server 同源托管的 **Web 管理控制台**，通过 Server API 管理上述数据；它不是独立数据源或独立服务。

一句话：**App 干活、Server 管协作数据、Console 提供 Web 管理界面**。本地 backend 内嵌一个 guarded Server 客户端，对“协作实体”做读镜像+写代理，对“私有实体”一律不上云。

## 1. 三条不可妥协的红线（哪些**永不**上云）

1. **本机任务执行凭据**：`LLM_API_KEY`、bot token、本机 MCP/连接器 OAuth 令牌等。只存 App 本地（`backend/.env` 或本地 DB），绝不进 Server、绝不进前端、绝不透传子进程。SSO provider client secret 与中央 WeKnora secret 是 Server 控制平面凭据，必须只写不回显、禁止下发 App。
2. **沙箱工作区文件（资产/云盘）**：`workspace/projects/<id>/` 下的一切文件本体。属用户私有产物，只在本机。
3. **会话正文（消息/工具轨迹）**：对话内容、工具调用参数与返回。只以**元数据**（一条 timeline 事件：谁、在哪个项目、干了什么、何时）上行 Server，正文不上云。

> 违反以上任一条即为 P0 事故。任何"顺手上传一下"的便利都不能突破。

## 2. 数据分层总表

**权威源**列 = 谁是真相源；**上云**列 = 是否进 Server 的 DB；**同步**列 = 数据流向；**离线**列 = App 未连 Server 时的行为。

| 实体 | 权威源 | 上云 | 同步方向 | 离线行为 | 现状 |
|---|---|---|---|---|---|
| 账号 accounts | **Server** | ✅ | Server→App 镜像 | 已登录身份读本地镜像；未登录使用匿名访客作用域 | ✅ 已打通 |
| SSO provider / external identities / signup invites | **Server** | ✅ | Console 配置；App 代理授权与绑定 | 已缓存登录仍可本地使用；新授权需 Server | ✅ Google/微信/Telegram |
| 组织 orgs / 成员 | **Server** | ✅ | Server→App 镜像 | 只读缓存 | ✅ |
| 项目 projects（元信息/角色） | **Server**（server-origin） | ✅ | 双向：增量镜像+写代理 | 本地原生项目纯本地 | ✅ 成员/配置写已代理 |
| 项目邀请 invites | **Server** | ✅ | Server 权威 | 无 | ✅ |
| **任务 work_items（含自定义字段/依赖/Sprint）** | **Server**（server-origin） | ✅ | 双向：增量镜像+写代理 | 读 last-known-good；写失败显式报错 | ✅ 已打通 |
| **里程碑 milestones** | **Server**（server-origin） | ✅ | 双向 | 同上 | ✅ |
| 项目自定义字段 project_custom_fields / Sprint | **Server** | ✅ | Console 管理；任务引用随 work_items 同步 | 读缓存 | ✅ |
| 任务活动流 work_item_activity | **Server** | ✅ | Server 逐条留痕、Console 回读 | 无 | ✅ |
| 团队动态 timeline_events | **Server** | ✅（仅元数据） | App↔Server；增量缓存 | last-known-good + 本机 sessions | ✅ |
| service identities / relay events | **Server** | ✅（事件 JSON，不含会话正文） | 外部系统→Server→指定 App 设备 | Server 持久排队；租约到期重投 | ✅ |
| 讨论 comments / @提及 | **Server** | ✅ | Server 代理 | 无离线态 | ✅（设计取舍） |
| 在线状态 presence | **Server** | ✅ | Server | 无 | ✅ |
| 目录 catalog（人格/连接器/技能/推荐位） | **Server** | ✅ | Server→App 带 revision 条件下发 | 首次用 builtin；离线保留最后可用快照 | ✅ Skill tombstone、能力报告与兼容门禁已完成；实时失效推送待补 |
| **资产/文件 assets** | **App 本地** | ❌ | 不同步 | 全功能 | ✅ 故意不上云（红线 2） |
| 自动化 automations | **App 本地** | ❌ | 不同步（暂） | 全功能 | 未上云；是否需团队级待定 |
| 助理/频道 channels | **App 本地** | ❌ | 不同步 | 全功能 | 私有 |
| 会话 sessions/messages | **App 本地** | ❌（仅元数据上行） | 见红线 3 | 全功能 | ✅ |
| 本机 LLM / MCP /连接器 secret | **App 本地** | ❌ | 永不 | 全功能 | ✅ 红线 1 |
| SSO / 中央服务 provider secret | **Server deployment** | ✅ | Console 只写；不下发 | 新授权/中央服务不可用 | ✅ 脱敏审计 |

## 3. 同步契约（协作实体怎么同步）

以 `work_items` 为**唯一样板**，所有"上云协作实体"都应遵循同一模式（见 [backend/routers/work_items.py](../backend/routers/work_items.py)）：

1. **归属判定**：仅当 ①Server 已启用（`AGENTMATE_SERVER_URL` 非空）②请求带 Bearer token ③项目 `origin=="server"` 三者同时成立，才走云端；否则纯本地。
2. **读 = 代理 + 镜像**：从 Server 拉取 → 按 `id + updated_at` 增量合并 → 返回本地一致视图。Server 不可达 → 读 last-known-good 镜像。
3. **写 = 代理 + 刷新**：先校验角色（Viewer 只读）→ 代理到 Server → 成功后重拉刷新镜像。server-origin 写不可达时显式失败，不能写一条下次 pull 会消失的本地假成功。
4. **镜像合并**：项目/成员/work item/milestone 均保留 `server_updated_at/server_dirty`；本地与远端并发修改进入可查询冲突台账，不静默覆盖。远端撤权仍以 Server 为准。

> 铁律：**协作实体的写，凡 server-origin 项目，必须代理到 Server**。只写本地 = 下次 pull 被覆盖 = 静默丢数据。项目、成员、任务与里程碑已统一遵循此约束。

### 3.1 目录与 Skill 的专用同步契约

目录不是普通协作表：它还要同时处理随 App 打包的 builtin、Server 公共定义和用户本机安装快照。

1. **Server 定义权威**：连接 Server 且至少成功同步一次后，同 slug 的 Server 发布/停用语义优先于
   builtin。停用必须下发 tombstone，不能用“省略该行”表达。
2. **离线保留最后状态**：Server 不可达时不清目录、不解除 tombstone、不自动回到更旧 builtin；
   last-known-good 继续可用。
3. **首次兜底**：从未配置 Server 或从未成功拉取时，才使用当前 App 版本内置种子。
4. **定义与安装分离**：目录可更新展示和待安装版本；已安装 Skill 的指令、工具、文件、权限和版本
   必须作为本机原子快照升级，不允许“旧指令 + 新工具”混跑。
5. **兼容门禁**：App 上报版本和公开工具能力；低于 `min_app_version/tool_contract_version` 时，
   目录可展示但不得安装/运行，并给出明确升级要求。
6. **刷新机制**：启动/登录/恢复/手动刷新 + 低频条件请求；实时通道只推 revision 失效信号，
   完整定义仍经认证 pull 获取。

现状基础链路为 `POST /api/server/pull` 全量替换 `scope=server`；本节描述目标语义。实现前后均不得
把网络不可达与中心撤回合并为同一个“回退 builtin”状态。

## 4. 统一用户与身份规范

- **单一账号权威**：Server 是**唯一**账号系统。App 登录即用 Server 账号身份，**app token == Server token**；本地 `users` 表用 **Server account id 作本地 id** 镜像（`upsert_external_user`）。全端一个用户体系。
- **联合身份不自动合并**：Google、微信、Telegram 外部 subject 显式绑定到唯一 account_id；同邮箱冲突时拒绝自动链接。默认 `invite_only` 注册，最后一种可用登录方式不能解除。
- **禁止本地账号分叉**：App 不创建或认证本地口令账号；Server 未配置或不可达时不能注册/重新登录。已缓存的 Server token 可继续解析为原 Server account id，保证已登录会话离线可用。
- **本地匿名映射**：未登录 Server 时用 `LOCAL_USER`（`0000…0001`）承载匿名访客数据作用域；它不是账号。首次登录/导入时 `set_server_link` 记录访客存量数据与 Server account 的归属，存量本地数据归到该云账号。
- **人归属必须强映射**：任务负责人、动态 actor 等“谁”字段，**权威值一律是 Server `account_id`**，显示名由成员表解析。
  - `work_items.assignee` 已采用“写时名字/id 归一为 account_id、读时解析显示名、无法解析的历史文本不丢失”的兼容迁移。
- **角色权威**：Owner/Admin/Member/Viewer 由 Server 定义，App 镜像后本地访问控制（`project_access_role`）自动生效；写操作按角色 gate，Viewer 只读。

## 5. 新增实体的归层决策流程

加任何新实体/新功能前，依次自问：

1. **含红线数据吗？**（凭据 / 文件本体 / 会话正文）→ 是则**必须本地**，最多上行元数据。停。
2. **需要多人共享/协作看到吗？** → 否则**本地**（如个人助理、自动化脚本）。
3. **需要跨端/跨设备统一管理吗？**（账号、项目、成员、任务）→ 是则 **Server 权威**，按 §3 契约做读镜像+写代理，并保证离线回退；Console 只是管理这些数据的 Web 界面。
4. **归 Server 的，人归属字段一律用 account_id**（§4），不要再引入自由文本的“谁”。

> 默认倾向：**能本地就本地**（隐私 + 离线 + 简单）；只有"协作/统一管理"这条硬需求才上云，且上云就要把 §3 契约做全（写代理 + 离线回退 + 增量合并），不做半套。
