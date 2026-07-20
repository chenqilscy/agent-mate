# AgentMate Console —— Web 管理控制台设计

> 状态：设计稿（2026-07-08）。epic **WB-078**，子任务 WB-079～084。
> 前置：[`agentmate-server-架构设计.md`](agentmate-server-架构设计.md)（Server 控制平面总纲）。
> 本文把原来那个「够用就好」的 Server 控制台升级为一个**完整的 Web 管理控制台**，
> 最终产品名为 **AgentMate Console**，由 `server/web/console.html` 提供。

## 1. 背景与定位

AgentMate = **local-first 执行内核**（本机 App 跑 agent、LLM、沙箱文件） **+ 云端控制平面**（Server：账号/组织/项目/成员/目录的权威源）。
Server 现有的 web 控制台只覆盖了控制平面的一小角：项目仅有 成员/邀请/讨论/在线/时间线，专家/技能/连接器只有一个**裸 JSON**「目录 Admin」，SkillHub 完全没有 UI。

用户诉求（2026-07-08）：
1. 门户的**项目管理**要与 AgentMate App 的项目管理对齐（当前完全不一致）。
2. **技能 / 连接器 / 专家·专家团**要在门户里有正经管理。
3. **SkillHub** 要在门户里有 UI（后端已在定时镜像 369 技能，见 WB-069）。
4. 管理界面使用独立、职责清晰的产品名 **AgentMate Console**。

**定位（关键）**：AgentMate Console 是 **AgentMate Server 的 Web 管理控制台**，不是「AgentMate App 的 Web 版」，也不是独立服务。见 §2 的硬约束。

## 2. 硬约束（决定「能对齐到哪」）

- **执行与文件是 local-first**：agent 工具循环、LLM 调用跑在**本机 backend**；沙箱文件（项目「资产」）
  **绝不上云**（铁律 4）。所以 App 项目工作台里的 **动态（执行记录）/ 资产（文件）/ 执行 composer** 这三块
  **本质上进不了 Web 门户** —— 门户能管的是**控制平面数据**（配置/成员/协作/目录）。
- **凭据绝不进 Server**：LLM key、连接器 token 只在本机 `backend/.env`。连接器 launch spec 里只存**环境变量名**
  （如 `secret_env: {GITHUB_PERSONAL_ACCESS_TOKEN: "GITHUB_TOKEN"}`，映射的是变量名不是值），故 launch spec 可安全入 Server。
- **离线优先不破坏**：门户是 Server 的皮；Server 不可达时本机 App 全功能照常（既有设计，不动）。

因此「项目管理与 AgentMate 完全一致」的准确落地 = **对齐可管理的部分**：项目配置 + 成员/角色/邀请 + 团队计划·任务 + 讨论/在线/时间线；执行/资产留在 App（门户里对执行仅以**时间线**只读体现）。

## 3. 现状盘点

**Server 后端（已有，多数够用）**
- `models.py`：`Account`(含 `is_platform_admin`) / `Org` / `Project`(**已含 `instruction`/`connectors`/`experts`/`skills`**) / `Invite`。
- 路由：`auth` `orgs` `projects`(成员/角色/邀请) `comments`(评论+@) `notifications` `timeline` `catalog`。
- `catalog_items`：`category`/`kind`/`data`(JSON)/`sort`/`enabled`/`scope='builtin'`；类别沿用 App 橱窗
  （`EXP_GRID` `EXP_TEAMS` `EXP_CATS` `EXP_SCENES` / `CONNS` `CONN_META` / `SK_GRID` `SKILLHUB_*` / `NP_*` `PROJ_TPL` …）。
- SkillHub：`skillhub_sync`（定时镜像→`replace_skillhub_mirror`）+ `skillhub_client`（CLI search 代理），端点 `POST /catalog/skills/sync`、`GET /catalog/skills/search`。
- **缺**：`work_items`（计划/任务）在 Server 无模型、无同步（App 本地独有）。

**AgentMate Console（`server/web/console.html`）**：auth / 项目(成员·邀请·讨论·在线·时间线) / 组织 / 通知 / 目录 Admin(裸 JSON)。

**改动集中在门户 UI + 少量 Server 后端（work_items + 目录写端点细化）；项目配置字段后端已支持 `PATCH /projects`。**

## 4. 目标形态

管理界面统一命名为 **AgentMate Console**，导航重构为：

```
AgentMate Console
├─ 项目            项目管理面（配置 / 成员·角色·邀请 / 计划·任务 / 讨论·在线·时间线）
├─ 目录运营中心     专家 · 专家团 · 连接器 · 技能 · SkillHub（类型化 CRUD + 下发）   〔平台管理员〕
├─ 组织            组织及成员（既有）
├─ 通知            @提及与协作事件（既有）
└─ 账号            当前账号 / 平台管理员徽标 / 退出
```

## 5. 模块设计

### 5.1 项目管理面（WB-080；计划/任务见 WB-081）
项目详情从「成员/邀请/讨论/在线/时间线」扩为与 App 对齐的**配置 + 协作**面：
- **配置**：指令（编辑，`PATCH /projects`）；连接器 / 专家 / 技能（从**目录**选择的多选 picker，写回 `project.connectors/experts/skills`）。字段后端已存在。
- **成员/角色/邀请**：既有，保留。
- **计划 / 任务**：见 §5.4（需新后端）。
- **讨论 / 在线 / 时间线**：既有，保留；执行只经**时间线**只读体现（不做 composer/资产）。

### 5.2 目录运营中心（WB-082/083/084）
用**类型化表单**替掉裸 JSON Admin；每类一张卡片列表 + 结构化编辑器，写 `catalog_items`，客户端 pull 后覆盖本地（WB-066 下发已就绪）。
- **专家**（`EXP_GRID`）：icon / 名称 / 副标题 / 简介 / 标签 / 分类（`EXP_CATS`）/ **persona**（真定义，可选下发）。
- **专家团**（`EXP_TEAMS`）：名称 / 图标 / 成员专家清单（引用专家名）。
- **连接器**（`CONNS`+`CONN_META`）：icon / 名称 / 状态(rdy/tok) / launch spec 编辑器（内置 `builtin_server` 或第三方 `command/args`；`requires`/`requires_bin`；`secret_env` **仅变量名**）。
- **技能**（`SK_GRID`）：icon / 名称 / 简介 / 分类（`SK_CATS`）。
- 通用能力：启用/停用（`enabled`）、排序（`sort`）、删除；保留「高级：裸 JSON」兜底特殊类别。

### 5.3 SkillHub（WB-084）
- **浏览**：Server 镜像的技能目录（`SKILLHUB_*` + `replace_skillhub_mirror` 存的行），分类过滤。
- **搜索**：走 `GET /catalog/skills/search`（CLI 代理，不可用则空+`cli:false`）。
- **上架/精选**：把镜像里的技能标记进 `SKILLHUB_FEATURED` 供客户端首页展示。
- **手动同步**：`POST /catalog/skills/sync` 按钮 + 上次同步统计。

### 5.4 团队计划 / 任务（WB-081，最重）
App 的 work_items 目前**本地独有**。要在门户管理团队计划/任务，需要 Server 侧新增并双向同步：
- **Server 新模型** `work_items`(project_id / title / status[todo·doing·paused·done] / source / assignee / order / created_at)。
- **路由**：`GET/POST/PATCH/DELETE /projects/{id}/work-items`（access-gated，Viewer 只读）。
- **同步**：扩展 WB-062 —— 下行 pull 把 Server work_items 镜像进本地；上行把本地新增/改状态回传（沿用 outbox 或直连）。冲突以 Server 为准（团队共享）。
- **门户 UI**：看板（4 列拖拽）+ 列表，与 App 的「计划/任务」tab 对齐。
> 体量最大、且触碰本地⇄Server 同步。建议放 epic 末尾；若想先要轻量收益可后置或拆二期。

## 6. 数据模型改动

| 模型 | 动作 |
|---|---|
| `Project` | 无需改（`instruction/connectors/experts/skills` 已在） |
| `catalog_items` | 复用；写端点已具备，门户做类型化表单即可 |
| **`work_items`（新）** | Server 新表 + DAO + 路由 + 本地⇄Server 同步（WB-081） |

## 7. 产品与技术命名

**中心 API 服务**：统一使用 **AgentMate Server**；代码目录 `server/`，环境变量使用 `AGENTMATE_SERVER_*`，本地客户端模块使用 `server_client` / `server_sync`。

**Web 管理界面**：统一使用 **AgentMate Console**；由 `server/main.py` 的 `GET /` 托管 `server/web/console.html`，同源调用 `/api/*`。

> Server 是权威数据与 API 服务；Console 是它的 Web 管理界面。两者不是两个后端服务。

## 8. Issue 拆分（epic WB-078）

| Issue | 领域 | 内容 | 体量 |
|---|---|---|---|
| **WB-078** | epic | 本设计 + 总纲 | — |
| **WB-079** | frontend | Console 品牌与导航重构（骨架） | 小 |
| **WB-080** | frontend | 项目管理面 —— 配置编辑（指令 + 连接器/专家/技能 picker，读目录、写 `PATCH /projects`） | 中 |
| **WB-082** | frontend | 目录运营中心框架 + **专家 / 专家团** 类型化 CRUD（替裸 JSON） | 中 |
| **WB-083** | frontend | 目录运营中心 —— **连接器** 类型化 CRUD（launch spec 编辑器） | 中 |
| **WB-084** | fullstack | 目录运营中心 —— **技能 + SkillHub**（浏览/搜索/上架/手动同步） | 中 |
| **WB-081** | backend | **团队计划/任务** —— Server `work_items` 模型 + 路由 + 本地⇄Server 同步 + 门户看板 | 大 |

**建议顺序**：WB-079（改名骨架）→ WB-080（项目配置）→ WB-082/083/084（目录运营中心）→ WB-081（计划/任务，最重殿后）。
每条独立可交付、独立提交（共享工作树按 hunk 暂存）。

## 9. 非目标（明确不做）

- 执行 / 沙箱文件（资产）/ composer 进 Web —— 违反 local-first + 铁律 4。
- org 级目录运营（团队私有目录）、实时通道（WebSocket 在线/评论，v1 仍 REST+轮询）。
- SaaS 托管 / 代码签名（需用户基建/证书）。
- 把 Console 拆成第二个后端服务——它保持由 Server 同源托管。
