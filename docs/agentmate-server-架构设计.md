# AgentMate Server 架构设计

> 状态：控制平面与 Skill 发布治理已实现；桌面二进制发布仍待生产化，更新于 2026-07-21。
> 对应基础 epic [WB-058](issues/archive/2026/WB-001-099.md#wb-058)；数据权威与隐私边界以
> [`agentmate-数据分层与同步规范.md`](agentmate-数据分层与同步规范.md) 为准。

## 1. 定位

AgentMate 采用“本地执行平面 + 可选中心控制平面”：

- **AgentMate App** 在用户本机运行 agent、LLM、工具、MCP 与沙箱工作区。
- **AgentMate Server** 是独立同仓的 FastAPI 服务，管理账号、组织、server-origin 项目、成员/角色、
  邀请、协作数据和 AgentMate 自有能力目录。
- **AgentMate Console** 是 Server 同源托管的 Web 管理界面，不是第三套后端或 App Web 版。

Server 不能执行用户本地任务，不能读取工作区或会话正文，也不能保存 LLM key、连接器 token、
第三方 SkillHub Key 或技能包。

## 2. 当前拓扑

```text
┌──────────────────────── AgentMate Server :8100 ────────────────────────┐
│ FastAPI + SQLite                                                       │
│ auth · accounts · orgs · projects · members/roles · invites            │
│ work items · milestones · comments/@ · presence · notifications        │
│ timeline metadata · AgentMate catalog definitions/recommendations       │
│                                │                                       │
│                                └── Console（同源 /api）                 │
└───────────────────────────────▲────────────────────────────────────────┘
                                │ guarded REST
                                │ login / pull / proxy / outbox push
┌───────────────────────────────┴────────────────────────────────────────┐
│ AgentMate App backend :8101                                            │
│ 本地 SQLite · agent runtime · MCP · credentials · workspace             │
│                                ▲                                       │
│                                │ REST + SSE                             │
│ React/Vite :8102 或 Tauri 2 桌面壳                                     │
└────────────────────────────────────────────────────────────────────────┘
```

`AGENTMATE_SERVER_URL` 为空时，App 不创建 Server 依赖，使用 `LOCAL_USER` 与本地项目。Server 不可达时，
App 保留本地执行能力并使用已有镜像；网络失败不能清空最后可用目录，也不能阻断本地会话。

## 3. 已实现边界

### 3.1 身份与项目

- Server 签发 Bearer token，是连接模式下的账号权威。
- App backend 代理登录/注册并缓存身份；前端仍只与 App backend 通信。
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
- 连接器定义与推荐位；
- Skill 定义、文件与推荐位；
- 内置工具的运营目录与 Skill 绑定策略；
- 其它受控模板/目录分类。

目录定义和推荐位是不同对象。第三方 SkillHub 推荐位只保存 `provider=skillhub`、稳定 slug、展示文案、
排序、启停与生效时间；Server 不搜索、镜像、代理或安装 SkillHub 内容。

App 通过 `POST /api/server/pull` 携带 revision 与 capability report 条件拉取；revision 变化时获取完整
Server snapshot 并原子替换本机 `catalog_downlink` 的 Server scope，未变化时不重写。App 自造专家、
本地 Skill 安装和连接器凭据属于本机 override，不上传、不被镜像覆盖。

## 4. 数据归属摘要

| 数据 | 权威源 | 当前流向 |
|---|---|---|
| 账号、组织、server-origin 项目、成员/角色、邀请 | Server | Server → App 镜像 |
| 工作项、里程碑、评论、presence、通知 | Server | App backend 代理，必要时本地镜像 |
| AgentMate 专家/团队/连接器/Skill 定义与推荐位 | Server | Server → App 条件全量快照 pull |
| 内置工具运营目录 | Server `tool_catalog`；App 实现注册表作执行裁决 | Console 管策略；App 上报真实 capability |
| server-origin 项目知识库与 WeKnora 服务凭据 | Server | Console 管理；App 按项目 token 代理检索/显式上传，不下发 provider ID/Key |
| 第三方 SkillHub 市场、Key、技能包 | App 本地/第三方 | App 直连，不经过 Server |
| 本机安装 Skill 与自造专家 | App 本地 | 不同步；可上报非敏感能力元数据的目标尚未落地 |
| 会话、消息、trace、工具参数 | App 本地 | 不上云；只可上报最小时间线元数据 |
| workspace 文件 | App 本地 | 不自动同步；仅用户显式 `knowledge_add` 的目标文件可进入项目中央知识库 |
| LLM/连接器 secret | App 本地 backend | 永不上云、永不进前端 |

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

## 6. 目录与运行时关系

目录卡只有在能解析到真实运行定义时才可标记 functional：

- 专家必须有可注入 persona 和稳定 slug。
- 专家团成员必须引用稳定 expert slug；成员清单本身不构成多 Agent 调度。
- 连接器必须有受支持 launch spec、工具清单和本机凭据门禁。
- Skill 必须在 App 本地形成可校验的安装快照；未安装目录定义不能冒充已运行内容。

Server 下发只改变控制面定义；App runtime 是本机最终执行裁决者。未知工具、版本不兼容、缺凭据、
未安装或被撤回的能力必须拒绝运行并给出明确原因。

### 6.1 内置工具目录

`tool_catalog` 是工具运营策略的唯一权威源。首次建库会从随版本交付的实现清单执行
`INSERT OR IGNORE`，之后 Server 查询、Skill 保存/发布校验、revision 计算和 Console 编辑全部读数据库；
升级只补充新实现，不能覆盖运营已经修改的字段。旧 `shared/skill-tools.json` 已删除。

当前目录登记 25 项内置能力，其中 16 项默认允许普通 Skill 绑定。其余按 `contextual`、`automatic`、
`internal` 分层，由 runtime 决定何时注入。Console 允许管理显示名、说明、分类、风险、启停、绑定、
最低 App 版本和排序，并记录 `tool_catalog_audit`；实现名、权限、契约和注入方式不可在网页伪造或删除。

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
已纳管 Skill 的定义和启停状态。技能页另有「内置工具」管理视图，直接维护 Server 数据库策略；不提供
任意工具创建/删除，以免把数据行误当成本机可执行实现。

## 9. 部署与安全

- Server 位于 `server/`，可单独启动在 `127.0.0.1:8100`；当前存储为 SQLite。
- Console 静态资源由 Server 同源托管并调用 `/api/*`。
- App backend 位于 `backend/`，默认 `127.0.0.1:8101`；开发前端为 `:8102`。
- 生产部署必须补 TLS、反向代理、安全响应头、备份、审计、密钥管理和数据库容量方案。
- SaaS 多区域、计费/套餐、正式 SSO 与企业合规部署不属于当前实现基线。

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
| Console 全站 React/Ant Design | 已完成 | WB-234、WB-236 |
| 桌面更新代码链 | 已完成；本机真实 updater 签名升级/拒绝/回滚已演练，正式生产部署验收由外部条件项追踪 | WB-257、WB-283、[`desktop-build.md`](desktop-build.md) |

腾讯 WorkBuddy 的任务工作台、能力分层、自动化与企业控制面可作为产品结构参考；AgentMate 保持
local-first、私有数据不上云与真实能力可验收的独立边界。参考资料见 [`WorkBuddy/`](WorkBuddy/README.md)。
