---
id: WB-066
title: Hub 目录运营 Admin + 下发覆盖 —— 激活已预埋的 catalog capability
severity: P2
area: backend
status: fixed
origin: 既有实现
files:
  - hub/db.py
  - hub/routers/catalog.py
  - backend/hub_client.py
  - backend/storage/db.py
created: 2026-07-07
---

## 问题

WB-061 在 Hub 建了 `catalog_items` 表 + `GET /api/catalog/{category}`；WB-063 在本地建了 `hub_client.list_catalog`
的**下发 capability**。但 Hub 目录目前**空、无写入/管理**，本地也**没把下发接进** `/api/catalog`——所以架构 §5/§8
的「目录权威切 Hub 下发 + 本地 override」只到了「预埋 + 离线兜底」，运营侧还没真正激活。

## 触发场景

- 平台运营想新增/调整一个内置专家人格、连接器、技能橱窗卡，或团队 Admin 想给本 org 定制目录——应在 Hub 改一条、
  客户端 pull 后反映，而不是改代码发版。

## 影响

P2：让「目录入库（WB-059/060）」的价值真正兑现为「集中运营 + 下发」。**依赖 WB-061/063**（Hub catalog 表 + pull capability）。

## 建议修法

- **Hub 写端点**：`hub/routers/catalog.py` 加 `POST/PUT/DELETE /api/catalog/{category}` —— `builtin` 由平台运营
  （超级管理员）维护、`org` 级由该 org 的 Admin/Owner 维护（access-gated）。`hub/db.py` 补 upsert/delete/reorder DAO。
- **seed 下发源**：把 backend 的 builtin 人格/连接器/橱窗（`catalog_seed.py` + `catalog_showcase.json`）种进 Hub
  `catalog_items`(scope='builtin')，作为下发权威源。
- **本地下发覆盖**：把 `hub_client.list_catalog` 接进 `showcase_all()` / `builtin_persona()` / `connector_specs()`——
  **Hub 下发覆盖本地、本地 builtin 作离线兜底**（架构 §5 的 override 层）。注意别把空覆盖或阻塞网络接进热路径
  （沿用 WB-062 的 guarded + 线程池 / 缓存做法）。
- **前端 Admin 面（可选二期）**：目录管理视图（列/增/删/改/排序/上下架），复用现有 `.np-*`/卡片 class（视觉零重设计）。

## 验证

- Admin 在 Hub 增/改一条目录 → 客户端 pull 后**反映**（正是 WB-063 验证里点名的「目录在 Hub 改一条→客户端 pull 后反映」）。
- 本地 override / 离线兜底正确：Hub 有则覆盖，Hub 空/离线则本地 builtin 权威——两态都跑通、无白屏、无阻断。
- 权限：非运营/非 org-Admin 不能写；builtin 与 org 级隔离。

## 处理记录（2026-07-07）—— 后端核心完成（前端 Admin 视图为标记的可选二期）

### 改动
- **Hub 侧**：`accounts.is_platform_admin`（首个注册账号自举为平台管理员）；`hub/routers/catalog.py` 写端点
  `POST /api/catalog`、`PATCH/DELETE /api/catalog/item/{id}`（**仅平台管理员** gated）+ `GET /api/catalog`（一次拉全量 builtin，供下发）；`hub/db.py` `get/update/delete/list_all_catalog_items` DAO。
- **本地侧（下发覆盖）**：`catalog_downlink` 表 + `replace_all_downlink`（幂等全量重建，Hub 删除随之消失）+ `downlink_by_category`；`showcase_all()` **叠加下发**——数组类分类若 Hub 有下发则以 Hub 为准（覆盖本地），无下发/离线 → 本地 builtin 兜底；`hub_client.list_all_catalog`；`hub_sync.pull_catalog`（**不可达保留上次下发**、Hub 空 → 清空回落兜底）；`/api/hub/pull` 顺手 `pull_catalog`。

### 验证
- py_compile 两端；隔离 backend × live hub E2E **13 项全过**：admin gate（首账号 admin、非 admin 写 403）、Hub 加一条 → pull 后 `showcase_all` 该分类**被 Hub 覆盖**、未管理分类仍本地、update 反映、delete 后**回落本地 16**、离线 pull no-op + 本地目录照常兜底。新表迁移安全（`catalog_downlink` 本地新表；`is_platform_admin` Hub 幂等补列）。
- 对齐 WB-063 验证点「目录在 Hub 改一条 → 客户端 pull 后反映」✅；「本地 override / 离线兜底」✅。

### 未做（后续）
- 前端目录管理 Admin 视图（本 issue 已列**可选二期**）：列/增/删/改/排序 UI。
- org 级目录运营（团队 Admin 维护本 org 目录，scope='org'）。
- scalar 分类（QUICK / CONN_META）的下发覆盖（skeleton 只覆盖数组类分类）。

铁律：Hub 不可达一律保留上次/回退本地；写端点仅平台管理员；无凭据/工作区文件涉及。commit：见下。
