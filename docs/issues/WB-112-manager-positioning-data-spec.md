---
id: WB-112
title: AgentMate Manager 管理端定位 —— 改名 + 数据分层规范 + 统一用户 + 协作打通 + PM 细化（epic）
severity: P1
area: fullstack
status: in-progress
origin: 2026-07-10 用户方向设定（Hub 改名 AgentMate Manager、定位管理端、要数据上云/本地规范、统一用户、PM 细化）
files:
  - docs/agentmate-数据分层与同步规范.md
  - hub/web/console.html
  - hub/main.py
  - hub/db.py
  - backend/routers/projects.py
  - backend/hub_client.py
created: 2026-07-10
---

## 背景

用户对 Hub/管理门户提出四条方向：
1. **改名** BuddyWebMgr → **AgentMate Manager**，定位为 **AgentMate App 的管理端**。
2. **数据分层规范**：哪些上云、哪些本地，必须成文有准绳。
3. **统一用户管理**：一个账号体系跨 App/Manager。
4. **项目管理功能细化、丰富**（用户强调很重要）。

前置探查（见 [WB-111](WB-111-portal-pm-workspace-redesign.md) 之后的架构分析）已摸清 App⇄Hub 现状：work_items/milestones 双向打通；成员/项目配置的写只落本地会被 pull 覆盖；assignee 是自由文本、协作对不准人；动态只上行不回读；资产/凭据/会话正文按红线不上云。

## 子任务

- **WB-112a｜改名（done）**：console.html 标题/logo/登录页 + hub/main.py + hub/db.py 的用户可见串改为 "AgentMate Manager / App 管理端"。历史 issue 台账保持原名不改写。
- **WB-112b｜数据分层规范（done）**：新增 [`docs/agentmate-数据分层与同步规范.md`](../agentmate-数据分层与同步规范.md) —— 三条红线 + 实体分层总表 + 同步契约 + 统一身份 + 新实体归层决策流程。
- **WB-112c｜P1 协作写代理 + 身份强映射**（待做，最高优先）：
  - `backend/routers/projects.py` 的成员增改删 + `update_project`（指令/连接器/专家/技能）按 work_items 模式加**写代理**到 Manager（hub-origin 项目），Manager 不可达回退本地。
  - `assignee` 由自由文本升级为 Manager `account_id` 强外键；Manager `work_items` 加 owner/assignee 账号列；存量迁移（旧文本 → 按成员名匹配 account_id，匹配不上保留原文本兜底）。显示名由成员表解析。
- **WB-112d｜动态回读**：`hub_client` 加 `list_timeline`；App「动态」tab 与 Manager 均消费 Manager `timeline_events`，队友执行动态互见。
- **WB-112e｜镜像增量合并**：`mirror_hub_*` 由"整表删插"改为按 `id+updated_at` 增量合并、冲突可见，避免离线并发丢改动。
- **WB-112f｜PM 细化丰富**：按与用户对齐的优先级细化项目管理功能（候选：看板 WIP/分组/泳道、任务模板与批量操作、自定义字段、保存的视图/筛选、任务依赖与关键路径、工时/预估、周期与燃尽、@提及联动任务、导出）。范围待用户拍板后分片。

## 验证（各子任务分别）

- 改名：Manager :8100 页面标题/顶栏/登录页显示新名，无残留旧名（历史台账除外）。
- 写代理：hub-origin 项目改成员/配置后，隔离 Manager 侧 DB 真变，App 再 pull 不回退；Manager 不可达回退本地不报错。
- 身份：多账号下任务负责人跨 App/Manager 显示一致、可按人过滤；存量迁移不丢数据。
- 无后端运行时回归；改后端硬重启核对。

## 处理记录

2026-07-10 起：
- WB-112a 改名落地（console.html 3 处 + hub/main.py 2 处 + hub/db.py 1 处；历史 issue 台账保留 "BuddyWebMgr" 不改写）。Manager :8100 页面标题/顶栏/登录页显示新名，0 报错。
- WB-112b 规范成文（`docs/agentmate-数据分层与同步规范.md` v1）。
- **WB-112c Part A（协作写代理）done**：`backend/hub_client.py` 加 `get_project/update_project/add_member/update_member/remove_member` 五个 guarded 代理；`backend/routers/projects.py` 的 `update_project`/`add_member`/`update_member`/`remove_member` 四个写 handler 接 `authorization` header + `_hub_token`（Manager 已接 & 项目 origin=='hub' & 带 token 才走代理）→ 代理到 Manager → `_mirror_project`/`_mirror_members` 刷新本地镜像 → Manager 不可达回退纯本地。修掉「hub-origin 项目改成员/配置只写本地、下次 pull 被覆盖 = 静默丢数据」。
  - 验证：`py_compile` 过；用 backend venv 置 `HUB_URL` 后直连 live Manager :8100（demopm token + 注册 bob 账号）实跑五函数：`update_project` 写入 instruction+skills、`add_member`(bob→Member)→`update_member`(→Admin)→`remove_member` 成员表逐步真变，全部落 Manager 权威。`HUB_URL` 空的运行中 :8000 backend 走 `hub_enabled()` 短路 → 全部回退纯本地，reload 后 `/api/health`+`/api/projects` 均 200，无回归。
  - **待补（本 Part 已知取舍）**：hub-origin 成员变更的「通知」目前 Manager 侧未生成（本地通知在代理分支被跳过），归入后续通知/动态回读分片。
- **WB-112c Part B（身份强映射 assignee→account_id）done**：无 schema 变更（assignee 列已存在），采用「写时归一 + 读时解析名 + 一次性存量迁移」，对异构客户端（App React 仍可能发名字）容错。
  - Hub：`hub/routers/work_items.py` 加 `_members_maps/_norm_assignee/_decorate` —— 创建/更新时把 assignee 由「名字或 id」归一到成员 `account_id`（匹配不上保留原值兜底，不丢数据）；list/create/update 返回补 `assignee_name`（成员名解析）；assignee 变更的活动流用成员名而非 uuid。`hub/db.py` 加 `migrate_assignees_to_account_id()`（幂等，按成员名归一存量行）+ `init_db` 里 `assignee_norm_v1` 标志守卫的一次性调用。
  - App backend：`backend/routers/work_items.py` `_view` 用新 `_assignee_name`（从本地 users 按 account_id 解析真名，替代 `[:2]` 截断）；`_hub_view` 用 Hub 返回的 `assignee_name`（缺失回退原值）。
  - Manager console：`PM_CTX.members` 保留 `{account_id,name,role}` 全对象；负责人筛选/详情下拉 value=account_id·label=name；看板卡头像 + 列表负责人显示 `assignee_name`。
  - 验证：隔离 Hub（TestClient + scratch DB）6 项断言全过——创建/更新/list 名字→account_id 归一、不可解析名保留不丢、存量迁移生效、活动流用名不漏 uuid。App backend reload 后 `/api/work-items` 422（非 500）、`/api/health` 200，无回归。
  - **运行中的 Manager :8100 需重启**才激活 Hub 侧改动（迁移 + 归一/解析）；console.html 每次请求实时读取、已即时更新。
- WB-112d/e/f（动态回读 / 镜像增量合并 / PM 细化四方向）：待做。用户已选 PM 细化范围 = 看板视图增强 + 任务字段丰富 + 计划与度量 + 协作联动（全选）。
