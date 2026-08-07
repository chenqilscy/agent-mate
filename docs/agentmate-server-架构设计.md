# AgentMate Server 架构设计

> 状态：控制平面、联合 SSO、外部事件中继、Skill 发布治理与组织模型策略已实现；桌面二进制发布仍待生产化，更新于 2026-08-04。
> 对应基础 epic [WB-058](issues/archive/2026/WB-001-099.md#wb-058)；数据权威与隐私边界以
> [`agentmate-数据分层与同步规范.md`](agentmate-数据分层与同步规范.md) 为准。
>
> **历史基线说明（2026-08-08）：** 本文记录已经实现的 local-first + 可选控制平面架构，供迁移追溯。
> 新增功能和迁移后的唯一目标以 [`agentmate-server-first-架构设计.md`](agentmate-server-first-架构设计.md)
> 及 [WB-431](issues/archive/2026/WB-400-499.md#wb-431) 为准；不得继续扩展新的本地业务权威或通用镜像同步。

## 1. 定位

AgentMate 采用“本地执行平面 + 可选中心控制平面”：

- **AgentMate App** 在用户本机运行 agent、LLM、工具、MCP 与沙箱工作区。
- **AgentMate Server** 是独立同仓的 FastAPI 服务，管理账号、组织、server-origin 项目、成员/角色、
  邀请、联合身份、外部接入、协作数据和 AgentMate 自有能力目录。
- **AgentMate Console** 是 Server 同源托管的 Web 管理界面，不是第三套后端或 App Web 版。

Server 不能执行用户本地任务，不能读取工作区或会话正文，也不能保存 LLM key、本机连接器 token、
第三方 SkillHub Key 或技能包。Google/微信/Telegram SSO client secret、中央 WeKnora secret 等控制平面
服务凭据属于 Server deployment secret，只写不回显，不能下发 App 或进入任务执行环境。

## 2. 当前拓扑

```text
┌──────────────────────── AgentMate Server :8100 ────────────────────────┐
│ FastAPI + SQLite                                                       │
│ auth/SSO · accounts · orgs · projects · members/roles · invites        │
│ work items · milestones · comments/@ · presence · notifications        │
│ service identities · durable event relay · timeline metadata · catalog │
│                                │                                       │
│                                └── Console（同源 /api）                 │
└───────────────────────────────▲────────────────────────────────────────┘
                                │ guarded REST
                                │ login / pull / proxy / outbox push / relay lease+ack
┌───────────────────────────────┴────────────────────────────────────────┐
│ AgentMate App backend :8101                                            │
│ 本地 SQLite · agent runtime · MCP · credentials · workspace             │
│ durable job worker · automation/outbox/relay poll · health snapshot     │
│                                ▲                                       │
│                                │ REST + SSE                             │
│ React/Vite :8102 或 Tauri 2 桌面壳                                     │
└────────────────────────────────────────────────────────────────────────┘
```

`AGENTMATE_SERVER_URL` 为空时，App 不创建 Server 依赖，使用匿名 `LOCAL_USER` 作用域与本地项目，
但不会创建本地账号。Server 不可达时，App 保留本地执行能力并使用已验证 Server 身份的缓存与已有
镜像；网络失败不能清空最后可用目录，也不能阻断已登录用户的本地会话。

## 3. 已实现边界

### 3.1 身份与项目

- Server 是唯一账号权威并签发 Bearer token；App 不创建或认证本地口令账号。
- Server 联合身份 broker 支持 Google OIDC、微信开放平台网站 OAuth 和 Telegram OIDC。默认仅邀请注册；
  已登录用户须显式绑定，邮箱相同不自动合并，最后一种登录方式不能被解除。
- SSO provider 配置与一次性 signup invite 由 Console 平台设置管理；provider secret 只写不回显，
  以独立主密钥 AES-GCM 加密落库，启停/Client ID/密钥轮换写入脱敏不可变审计。
- App backend 代理登录/注册并缓存已验证的 Server 身份；前端仍只与 App backend 通信。
- Server 管理组织、项目、成员、Owner/Admin/Member/Viewer 角色与邀请。
- App 镜像 server-origin 项目与成员，并在本地路由执行同样的角色门禁；Viewer 只读。

### 3.2 协作数据

Server 已提供工作项、里程碑、活动、评论、@提及、在线状态、通知和团队时间线 API。App 对
server-origin 协作实体通过本地 backend 代理；Server 不可达时按各实体契约读取镜像或受控回退。

会话完成后，App 可把 `title/summary/ext_id/actor/project/time` 等最小元数据写入本地 outbox，后台以
用户 Server token 补推。时间线上报默认关闭；消息正文、工具参数、文件内容和 secret 不进入 payload。

### 3.3 目录

Server 管理以下 AgentMate 自有控制面对象：

- 专家定义与推荐位；
- 专家团定义；
- 连接器公开元数据、兼容性声明与推荐位；
- Skill 定义、文件与推荐位；
- 内置工具的运营目录与 Skill 绑定策略；
- 其它受控模板/目录分类。

目录定义和推荐位是不同对象。第三方 SkillHub 推荐位只保存 `provider=skillhub`、稳定 slug、展示文案、
排序、启停与生效时间；Server 不搜索、镜像、代理或安装 SkillHub 内容。

#### 外部目录参考源

腾讯 WorkBuddy 的[专家](https://www.workbuddy.cn/app/experts)、
[技能](https://www.workbuddy.cn/app/skills)和
[连接器](https://www.workbuddy.cn/app/connectors)公开目录可以用于候选发现、分类体系、卡片字段和
运营文案参考，但不是 AgentMate 的运行时依赖或权威数据源。Server 不自动抓取或镜像这些页面，
也不能把外部卡片名称与描述直接发布为可运行能力。

外部候选进入 Server 的受控流程是：

```text
来源 URL + 访问日期 + 必要短摘要
  → 人工筛选、去重和 schema 映射
  → 补齐 AgentMate 运行定义
  → 测试/权限/兼容性验收
  → Console 审核发布
  → Server 数据库成为 AgentMate 权威目录
```

其中专家必须有稳定 slug 与可注入 persona；Skill 必须形成可校验的本地安装快照并声明工具与权限；
连接器可以声明所需 launch spec、凭据门禁和工具协议，但本机真正可执行的 launch spec 必须随 App
发布并进入可信注册表，Server 声明只用于逐字段兼容匹配。参考页后续变化只形成复核信号，不自动覆盖
已发布数据。来源索引和核实摘要见
[`WorkBuddy/official-sources.md`](WorkBuddy/official-sources.md#动态能力目录)。

App 通过 `POST /api/server/pull` 携带 revision 与 capability report 条件拉取；revision 变化时获取完整
Server snapshot 并原子替换本机 `catalog_downlink` 的 Server scope，未变化时不重写。App 自造专家、
本地 Skill 安装和连接器凭据属于本机 override，不上传、不被镜像覆盖。

### 3.4 外部系统接入与后台执行

- 同机事件通过每条 Automation 独立 HMAC webhook 进入 App；公网事件通过 Server scoped service identity
  写入 durable relay，由目标 App 设备租约拉取、触发本地 Automation 后 ack。离线或崩溃会在租约到期后重投。
- Server token、webhook secret 和 service token 均只在创建/轮换时显示一次；读取接口不回显，服务身份支持限速、
  撤销和 scope 门禁。完整契约见 [`external-system-integration.md`](external-system-integration.md)。
- App 常驻任务不是“助理专用 worker”。`backend/main.py` 生命周期同时启动 durable job worker 与 scheduler；
  前者承载工作项执行/多 Agent 编排，后者承载 Automation、Server outbox、relay poll 等周期任务。
  `/api/ops/background-health` 独立报告各循环连续失败、最近成功与恢复状态。

## 4. 数据归属摘要

| 数据 | 权威源 | 当前流向 |
|---|---|---|
| 账号、组织、server-origin 项目、成员/角色、邀请 | Server | Server → App 镜像 |
| SSO provider 配置、外部身份、注册邀请 | Server | Console 管理；App 只代理登录/绑定流程 |
| service identity、relay event、设备租约与确认 | Server | 外部系统 → Server → 指定 App 设备 |
| 工作项、里程碑、评论、presence、通知 | Server | App backend 代理，必要时本地镜像 |
| AgentMate 专家/团队/Skill 定义及连接器公开元数据/推荐位 | Server | Server → App 条件全量快照 pull |
| MCP 连接器本机启动定义 | App 随版本交付的可信注册表 | Server 只能声明兼容目标；完全匹配后由 App 本地定义执行 |
| 内置工具定义与运营目录 | Server `tool_catalog`；native 由 App 签名实现，shell 由 Server 下发 | Console 管策略/跨平台脚本；App 校验镜像并执行裁决 |
| server-origin 项目知识库与 WeKnora 服务凭据 | Server | Console 管理；App 按项目 token 代理检索/显式上传，不下发 provider ID/Key |
| 第三方 SkillHub 市场、Key、技能包 | App 本地/第三方 | App 直连，不经过 Server |
| 本机安装 Skill 与自造专家 | App 本地 | 不同步；可上报非敏感能力元数据的目标尚未落地 |
| 会话、消息、trace、工具参数 | App 本地 | 不上云；只可上报最小时间线元数据 |
| workspace 文件 | App 本地 | 不自动同步；仅用户显式 `knowledge_add` 的目标文件可进入项目中央知识库 |
| LLM/连接器 secret | App 本地 backend | 永不上云、永不进前端 |
| 组织模型策略 | Server | Server → App 非敏感镜像；App 在每次 Run 前最终裁决 |
| 用户模型策略、Provider health、用量与成本 | App 本地 backend | 不上云；按 owner 统计并执行 |

配置也按同一归属治理：平台级中央 WeKnora 与协作策略由 Console 写入 Server；设备级 Langfuse、ASR、
Server 连接和时间线上报由 App 设置中心写入本地 backend。数据库值优先于环境变量，清除页面覆盖后回退
环境变量；密钥只写不回显并记录脱敏审计。数据库路径、监听端口、密码学启动材料和发布版本仍为
deployment-only，不能通过通用设置 API 伪装成热更新。

详细冲突规则、离线行为和红线见数据分层规范，本文不再复制一套容易漂移的表。

## 5. 当前同步契约

### 5.1 下行

- 登录后或用户显式刷新时，App backend 拉取项目/成员与目录。
- 目录使用 revision 条件请求；发生变化时下发完整快照并原子替换，不传增量 patch。
- server-origin 协作实体通常采用“Server 读取 → 本地镜像 → 返回”；网络失败时读取最后镜像。
- 从未成功连接 Server 的 App 才使用随版本打包的 builtin 作为首次兜底。

### 5.2 上行

- 工作项等 Server 权威实体由 App backend 代理写入 Server，成功后刷新镜像。
- 会话执行产出只上报可配置的时间线元数据；先写本地 outbox，再由调度器重试。
- 写 Server 失败不能伪装为已经完成同步；是否允许离线本地写由具体实体契约决定。

### 5.3 已完成与剩余边界

已完成：目录 revision、条件请求、last-known-good、显式 tombstone、App capability report、工具契约
门禁，以及启动/窗口恢复/低频刷新。

剩余：Server 主动推送“目录已失效”信号；跨实体同步冲突可视化、稳定重放与企业级审计。

### 5.4 模型治理与执行边界

Server 组织管理员维护不含凭据和接入地址的模型策略：允许列表、fallback 顺序、日/月 token 与成本软硬预算、
健康状态有效期和凭据轮换提示周期。App 随项目镜像获取组织策略，并在每次 Run 建立、模型解析和网络调用前，
将它与用户本地策略合并；allowlist 取交集语义，硬预算取更严格的剩余额度。裁决结果和策略 revision 固化到
Run 的非敏感快照，便于恢复与审计。

Provider API Key、自定义 base URL、健康检查结果和真实用量仍只在 App 本机。共享监听模式会拒绝指向
localhost、私网和保留地址的模型端点；纯 local-first 模式保留 Ollama 等本机模型。健康检查只有用户显式
触发后才参与 TTL 内的受控 fallback，响应和 Run 快照都不保存或回显 key。

当前组织预算是“组织策略约束下的本机 owner 用量”，不是 Server 汇总的全组织全设备账本。若要做企业级
统一额度，需要另行设计最小用量上报、幂等聚合和离线额度租约；在该隐私与一致性契约落地前不能把本地统计
表述为全局强一致预算。

## 6. 目录与运行时关系

目录卡只有在能解析到真实运行定义时才可标记 functional：

- 专家必须有可注入 persona 和稳定 slug。
- 专家团成员必须引用稳定 expert slug；成员清单本身不构成多 Agent 调度。
- 连接器目录必须按稳定 slug 解析到 App 本地可信 launch spec；Server-only 或声明漂移的定义只可浏览、不可执行。
- Skill 必须在 App 本地形成可校验的安装快照；未安装目录定义不能冒充已运行内容。

Server 下发只改变控制面定义；App runtime 是本机最终执行裁决者。MCP 子进程只按 App 随版本交付的
可信定义启动，Server 的 `command/args` 不会直接进入进程创建。未知工具、版本不兼容、缺凭据、
未安装、定义漂移或被撤回的能力必须拒绝运行并给出明确原因。

### 6.1 内置工具目录

`tool_catalog` 是工具定义与运营策略的唯一权威源。首次建库会从随版本交付的实现清单执行
`INSERT OR IGNORE`，之后 Server 查询、Skill 保存/发布校验、revision 计算和 Console 编辑全部读数据库；
升级只补充新实现，不能覆盖运营已经修改的字段。旧 `shared/skill-tools.json` 已删除。

工具分为两类：`native` 只下发定义、启停与绑定策略，执行代码仍由 App 签名构建提供；`shell` 同时下发
参数 JSON Schema、权限、超时、输出上限以及 `windows` / `linux` / `macos` 脚本。AgentMate 原子校验并
镜像完整快照，离线或损坏时保留最后可用版本；运行时按实际操作系统选择，Windows 固定用 PowerShell 7，
Linux/macOS 固定用 bash，参数只经 UTF-8 JSON 标准输入传入，工作目录固定为项目工作区且子进程环境剔除密钥。

默认目录登记 25 项 native 能力，其中 16 项允许普通 Skill 绑定。其余按 `contextual`、`automatic`、
`internal` 分层，由 runtime 决定何时注入。Console 可创建、编辑、删除 shell 工具并记录
`tool_catalog_audit`；native 的实现名、权限、契约和注入方式不可在网页伪造或删除。

发布校验只接受数据库中已启用且可绑定的工具。既有系统 Skill 可继续保留原有 internal 工具，但普通
Skill 不能新增绑定。客户端 capability report 直接枚举 App 真实实现；Server 只有在“目录允许且客户端
实现契约满足”时才判兼容。

## 7. Skill 能力发布（已实现基线）

> WB-245～WB-250 已落地 Skill 的不可变快照、兼容门禁、权限确认、灰度、撤回、回滚和聚合指标。
> Expert、Expert Team、Connector 与 Policy 复用该模型仍属于扩展目标。

### 7.1 不可变 release

```text
CapabilityRelease
  id
  kind                 skill | expert | expert_team | connector | policy
  slug
  version
  content_hash
  status               draft | testing | approved | rolling_out | published | withdrawn | superseded
  min_app_version
  min_tool_contract_version
  permissions
  rollout              channel | percentage | orgs
  created_by
  reviewed_by
  published_at
  release_notes
```

Skill release 已原子包含 `instructions + tools + files + permissions + hash`。Console 保存产生新 draft，
不再直接覆盖公开投影；推荐排序、营销文案或目录分类不是运行包版本。

### 7.2 客户端 capability report

App 只上报公开兼容信息：`app_version`、平台/架构、`tool_contract_version`、受支持工具名/版本和更新
通道。禁止附带凭据、工作区、会话正文或工具调用内容。

Server 据此完成发布前兼容检查和下行门禁。不兼容版本可浏览说明，但不得安装或运行，并应返回最低
升级要求。

### 7.3 下行状态机

| 状态 | App 行为 |
|---|---|
| 从未配置或从未成功同步 | 使用随 App 打包的 builtin |
| Server 暂时不可达 | 保留 last-known-good，不清空、不降回旧 builtin |
| 发布兼容版本 | 校验 hash/权限后原子安装或等待用户确认 |
| 明确停用/撤回 | 接收 tombstone，压制同 slug builtin，禁止新加载 |

网络失败和中心撤回是两种不同状态，不能都实现成“目录为空 → 回退 builtin”。

### 7.4 灰度、回滚与客户端更新

- Skill 灰度按通道、比例和稳定账号分桶；重复刷新不会在版本间抖动。组织定向分桶尚未实现。
- App 保留 last-known-good；Skill 安装/升级为原子写入，Console 支持显式回滚到历史内容并生成新版本。
- App 只按 release 聚合上报安装/运行成功与失败计数，不上传 prompt、文件、工具参数或凭据。
- Server API 在桌面升级窗口内保持向后兼容；强制升级只用于明确的安全/协议断裂。
- App 二进制升级走 Tauri 签名 updater，不能由目录 payload 自行替换可执行文件。

## 8. Console 管理职责

Console 管账号、组织、项目协作和 AgentMate 自有目录。Skill 定义与推荐位已分离；Skill 编辑统一
创建不可变 draft。发布治理页展示客户端 Test Run 证据、作者/审核者分离、定义/工具/权限 diff、
灰度比例、暂停、撤回、回滚、审计及按 release 聚合的安装/运行指标。普通目录 CRUD 已禁止直接修改
已纳管 Skill 的定义和启停状态。技能页另有「内置工具」管理视图，直接维护 Server 数据库。native 只能
调整运营策略；新增/删除仅限具备参数契约和至少一个平台脚本的 shell 工具。

## 9. 部署与安全

- Server 位于 `server/`，可单独启动在 `127.0.0.1:8100`；当前存储为 SQLite。
- Console 静态资源由 Server 同源托管并调用 `/api/*`。
- App backend 位于 `backend/`，默认 `127.0.0.1:8101`；开发前端为 `:8102`。
- Server 入口是 `server/main.py`；App backend 入口是 `backend/main.py`。后台 worker/scheduler 由 App backend
  生命周期启动，不是另一个需要单独部署的守护进程。
- App 与 Server 各自维护 `schema_migrations(scope,version,name,applied_at)`；升级按版本顺序单事务执行，
  只有成功才登记，失败回滚并在下次启动重试。新 schema 变更不得继续追加匿名兼容 DDL。
- 生产部署必须补 TLS、反向代理、安全响应头、备份、审计、密钥管理和数据库容量方案。
- 联合 SSO 协议与管理面已实现；生产启用仍需各 provider 审批、HTTPS 公网域名、精确 callback allowlist 与真实账号验收。
- SaaS 多区域、计费/套餐与企业合规部署不属于当前实现基线。

## 10. 里程碑依据

| 范围 | 状态 | 依据 |
|---|---|---|
| 目录定义与橱窗入库 | 已完成 | WB-059、WB-060 |
| 独立 Server 骨架 | 已完成 | WB-061 |
| 登录桥、镜像与时间线 outbox | 已完成基础链路 | WB-062 |
| 存量迁移与 local-first 回退 | 已完成基础链路 | WB-063 |
| 第三方 SkillHub 回归 App 本地 | 已完成 | WB-215 |
| Skill/连接器/专家推荐位分离 | 已完成 | WB-217、WB-220、WB-221 |
| Skill 生产发布与客户端兼容闭环 | 已完成 | WB-245～WB-250 |
| 内置工具目录入库、扩充与 Console 管理 | 已完成 | WB-266 |
| 内置工具完整下发与跨平台 Shell 执行 | 已完成 | WB-319 |
| Console 全站 React/Ant Design | 已完成 | WB-234、WB-236 |
| 后台循环健康、故障恢复与 CI 隔离 | 已完成 | WB-359、WB-360 |
| 外部系统 durable relay | 已完成 | WB-361、[`external-system-integration.md`](external-system-integration.md) |
| Google/微信/Telegram 联合 SSO broker | 协议、账户生命周期、加密审计和上线自检已完成；真实 provider 验收待部署方域名/凭据 | WB-362、WB-366～372、[`sso-deployment.md`](sso-deployment.md) |
| App/Server 版本化数据库迁移 | 已完成 | WB-363 |
| 桌面更新代码链 | 已完成；本机真实 updater 签名升级/拒绝/回滚已演练，正式生产部署验收由外部条件项追踪 | WB-257、WB-283、[`desktop-build.md`](desktop-build.md) |

腾讯 WorkBuddy 的任务工作台、能力分层、自动化与企业控制面可作为产品结构参考；AgentMate 保持
local-first、私有数据不上云与真实能力可验收的独立边界。参考资料见 [`WorkBuddy/`](WorkBuddy/README.md)。
