---
id: WB-112
title: AgentMate Manager 管理端定位 —— 改名 + 数据分层规范 + 统一用户 + 协作打通 + PM 细化（epic）
severity: P1
area: fullstack
status: fixed
origin: 2026-07-10 用户方向设定（Hub 改名 AgentMate Manager、定位管理端、要数据上云/本地规范、统一用户、PM 细化）
files:
  - docs/agentmate-数据分层与同步规范.md
  - server/db.py
  - console/src/components/project/ProjectWorkspace.tsx
  - backend/routers/projects.py
  - backend/routers/server.py
  - backend/server_client.py
  - backend/server_sync.py
  - backend/storage/db.py
  - src/views/ProjectHomeView.tsx
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
- **WB-112c｜P1 协作写代理 + 身份强映射（done）**：当前 Server 架构下，server-origin 项目的成员/配置写代理与 assignee `account_id` 归一已经落地；Server 不可达时保留 local-first 回退。
- **WB-112d｜动态回读（done）**：`server_client.list_timeline` + App scoped readback API；在线增量缓存 last-known-good，Server 不可达回退缓存；App「动态」合并团队时间线和本机 session，其他成员的远端事件不提供本机会话跳转。
- **WB-112e｜镜像增量合并（done）**：项目/成员/work item/milestone 按 `id+updated_at` 合并，不再整表删插；本地离线协作改动以 dirty/tombstone 保留，分叉进入可查询冲突台账并在 App 显示数量。owner/成员角色/项目访问仍以 Server 权限为准，远端撤权会收敛本地访问。
- **WB-112f｜PM 细化丰富（done）**：看板 WIP/分组/泳道、批量操作、保存视图/筛选、工时/预估、甘特、协作时间线、项目级任务模板、自定义字段、任务依赖/关键路径、Sprint/周期与燃尽、PM CSV 导出均已完成。

## 验证（各子任务分别）

- 改名：Manager :8100 页面标题/顶栏/登录页显示新名，无残留旧名（历史台账除外）。
- 写代理：hub-origin 项目改成员/配置后，隔离 Manager 侧 DB 真变，App 再 pull 不回退；Manager 不可达回退本地不报错。
- 身份：多账号下任务负责人跨 App/Manager 显示一致、可按人过滤；存量迁移不丢数据。
- 动态：两个真实 Server 账号仅能回读有权限项目；在线事件进入缓存，Server 停止后同一账号可读缓存，陌生账号不可读。
- 增量合并：远端更新正常合并；离线本地与远端并发改动不静默覆盖且冲突可见；远端成员角色/撤权不会被本地 dirty 绕过。
- PM 模板切片：模板按项目隔离保存；套用只预填任务表单，保存仍走 Server 权限与创建 API。
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
- 当时 WB-112d/e/f（动态回读 / 镜像增量合并 / PM 细化四方向）尚待做；用户已选 PM 细化范围 = 看板视图增强 + 任务字段丰富 + 计划与度量 + 协作联动（全选）。

2026-07-22（d/e 完成，f 新增一个连续切片）：
- 重新审计当前 `server/` + `backend/server_client.py` 架构，确认 a/b 文档与命名存在，c 的项目/成员写代理及 assignee 账号归一已在重构后路径中保留；未覆盖既有 Server 重构。
- **d 动态回读**：新增项目门禁下的 `/api/server/projects/{id}/timeline`，成功回读后以事件 id 增量缓存，不可达时返回 last-known-good；App 动态流与本机 session 去重合并，缓存状态可见。缓存只含协作元数据，不含会话正文、凭据、数据库或 workspace。
- **e 冲突安全镜像**：为项目/成员/任务/里程碑维护 `server_updated_at/server_dirty`；成员删除用 tombstone；冲突保存本地/远端快照并提供 scoped 查询。Server owner、角色及项目列表作为权限权威，远端角色回写、撤权后本地入口移除，防止离线 dirty 扩权。
- **f 任务模板切片**：React Console 恢复项目级任务模板的保存/套用/删除；模板是本机偏好，套用后的任务只能通过既有 Server API 与权限门禁创建。其余未完成 PM 能力仍列在 112f，不标完成。
- 验证：Server 全量 `41/41`；WB-112 增量/隔离回归 `6/6`（含成员子请求失败时保留 last-known-good）；隔离 Server+Backend 双账号、双临时 DB 的真实 HTTP 场景 `1/1`（在线回读→Server 停止缓存回退→离线本地改→Server 恢复并发改→本地保留且冲突 API 可见）；PM 模板契约 `1/1`；`npx tsc --noEmit`、`pnpm build`（App + Console）通过。
- 当时基线：该独立切片曾观察到 Backend regression 97 项中的 8 个既存失败；这些失败已在后续 WB-277/WB-279/WB-280 集成修复，本次最终全量回归为 131/131。

2026-07-22（f 最终收口）：
- **自定义字段**：Server 新增项目级定义表与权限 API，支持文本、数字、日期、单选和布尔类型；任务仅接受本项目已定义字段，删除定义会清理任务值。Console 提供可视化管理和动态任务表单。
- **依赖与关键路径**：任务保存 `dependency_ids`，服务端只接受同项目引用并拒绝依赖环；列表按预估工时计算确定性的最长依赖链并标记关键路径。
- **Sprint 与燃尽**：Server 新增 Sprint 权威表和 CRUD，任务关联 Sprint；燃尽按 Sprint 日期、真实任务工时和完成活动计算理想/实际剩余，Console 提供周期管理与燃尽明细。
- **PM 导出**：Server 生成带 UTF-8 BOM 的权限受控 CSV，包含基础字段、Sprint、依赖标题及动态自定义字段列；Console 直接下载，不在前端拼接假数据。
- **同步与文档**：App 本地 work item 镜像补齐三组字段，Server-origin 增量同步不会丢值；同步规范与功能规划删除了整表覆盖、自由文本负责人、动态未回读和 WB-257 未验收等过时描述。
- **验证**：WB-112 PM 新增 Server 2/2、Backend 镜像 1/1；双服务真实 HTTP 集成 1/1；Server 全量 45/45、Backend 全量 131/131；TypeScript、App 与 Console 生产构建通过。
- **状态**：a～f 全部完成，epic 更新为 `fixed`。
- **commit**：随本提交。
