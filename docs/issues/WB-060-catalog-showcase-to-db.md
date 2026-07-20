---
id: WB-060
title: 橱窗目录入库 —— catalog.ts 静态商品卡迁到 DB + API，前端改从接口取
severity: P2
area: frontend
status: fixed
origin: 既有实现
files:
  - src/data/catalog.ts:1
  - src/views/ExpertsView.tsx
  - src/views/ProjectHomeView.tsx
  - backend/storage/db.py:134
created: 2026-07-07
---

## 问题

可浏览的「橱窗目录」全是前端静态数组：[src/data/catalog.ts](../../src/data/catalog.ts) 里
`EXP_GRID`/`EXP_TEAMS`/`NP_EXPERTS`/`EXP_SCENES`/`SK_GRID`/`SK_RECO`/`SKILLHUB_GRID`/`SKILLHUB_FEATURED`/`SKILLHUB_KITS`/`CONNS`/`NP_CONNS`/`CONN_META`/`AUTO`/`INSP`/`NP_TPLS`/`PROJ_TPL` 等几十条商品卡。它们只是展示内容（多数未接真实能力），改一条要改前端发版，也无法由平台运营/团队维护。

## 触发场景

运营想上/下架一个专家团、技能卡、连接器橱窗项，或调整分类/排序/精选，只能改 `catalog.ts` 重新构建前端。

## 影响

P2（择机）：纯展示、不阻断功能，但为 Hub 目录（[WB-058](WB-058-hub-control-plane-epic.md)）统一运营做准备。本阶段先把橱窗迁到**本地 backend 库 + API**，前端改从接口取；将来目录权威切到 Hub 下发（WB-063）时前端无需再改。

## 建议修法

按 [架构设计](../agentmate-server-架构设计.md)，与 [WB-059](WB-059-catalog-definitions-to-db.md) 的表**统一**（同一张表既是橱窗又是真定义，用 `functional`/`status` 区分；橱窗卡 = 不接真实能力）：

### 后端
- `storage/db.py`：橱窗项并入 `catalog_experts`/`catalog_connectors`/`catalog_skills`（+ `catalog_expert_teams`/`catalog_automation_templates`/`catalog_inspirations`/`catalog_project_templates`）。含 `category`/`badge`/`sort`/`featured`/`downloads`/`stars` 等展示字段。
- 种子：把 `catalog.ts` 各数组作为 `scope='builtin'`、`functional=false`/`status='catalog'` 的初始数据 seed 入库（保持与现状**逐字一致**，避免视觉/内容漂移——铁律 2）。
- `routers/catalog.py`（新）：`GET /api/catalog/experts|expert-teams|skills|connectors|automations|inspirations|project-templates`（支持分类过滤/分页/排序）。挂 `main.py`。

### 前端
- `lib/api.ts` + 新 `stores/catalogStore.ts`：从接口拉取，替代 `import ... from data/catalog`。
- 消费点（[ExpertsView.tsx](../../src/views/ExpertsView.tsx)、[ProjectHomeView.tsx](../../src/views/ProjectHomeView.tsx)、[Composer.tsx](../../src/components/composer/Composer.tsx)、[NewProjectModal.tsx](../../src/components/project/NewProjectModal.tsx)）改用 store；保留一份静态兜底或首屏骨架，避免后端未连时白屏。
- **视觉零重设计**：卡片/网格 class 名与 token 逐字沿用，只换数据来源。

## 验证

- `npx tsc --noEmit` 通过；`npx vite build` 通过；`py_compile` 后端改动全过。
- 硬重启 :8000 后 Playwright 实测（**明暗双主题**、≤900px）：
  - 专家页 / 专家团 / 技能商店(SkillHub) / 连接器目录 / 新建项目模板 / 灵感 —— 各页内容与迁移前**逐字一致**、分类过滤/精选轮换/详情弹窗照常。
  - 真接入项（如金山文档 `CONN_META`、已安装技能、内置连接器）行为不变。
- 后端未连时前端不白屏（兜底/骨架生效）。
- 在库里上/下架或改排序一条橱窗项（不改前端），刷新后反映。

## 处理记录（2026-07-07）

### 设计取舍
- 用**一张通用 `catalog_showcase` 表**（`kind` + `sort` + `enabled` + `data`(JSON) + `is_scalar`）承载全部橱窗导出：数组类每元素一行（可按行上/下架、改 sort），对象类（QUICK/CONN_META）`is_scalar=1` 单行整存。比把 25 个异形元组硬映射到 typed 列更稳、逐字一致、天然支持「按行运营」；与 WB-059 的**功能表**（catalog_experts/connectors）职责分离（功能定义 vs 纯浏览卡）。
- 种子源：用已装的 `tsc` 把 `src/data/catalog.ts` 逐字转出 `backend/storage/catalog_showcase.json`（免手抄近 400 行、保证逐字一致）。
- **与 WB-064 协调**：SkillHub 商店浏览列表（`SKILLHUB_GRID/FEATURED/KITS/CATS`）**不入库、不改写其消费视图**——WB-064 要把它换成实时 rankings/search，避免撞车；`catalog.ts` 整体保留作静态兜底，`ExpertsView` 的 SkillHub 面仍从 `catalog.ts` 直取。

### 改动
- 后端：
  - `storage/catalog_showcase.json`（新，种子源）；`storage/db.py`：`catalog_showcase` 表 + `_seed_showcase`（幂等 by kind，`_SHOWCASE_SKIP` 跳过 SKILLHUB_*）+ `showcase_all()` DAO；`routers/catalog.py`（新）`GET /api/catalog`；`main.py` 挂载。
- 前端：
  - `lib/api.ts`：`getCatalog()`。`stores/catalogStore.ts`（新）：以 `catalog.ts` 为静态兜底初值 + 启动 `load()` 从 API 覆盖（zustand 响应式；READY/NEEDS 数组→Set）；导出 `useCatalog()` hook。
  - 9 个消费点改从 store：组件列表渲染用 `useCatalog()`（HomeView/InspireView/ProjectsView/AutomationView/ConnectorDetailModal/ExpertsView 的 ExpertsPane·RecoView·ConnectorsPane/NewProjectModal 的外层与 **PickerOverlay**）；模块级/装饰性图标查找用 `useCatalogStore.getState()`（ProjectHomeView.iconOf、Composer.iconOf、AutomationView.iconOf、NewProjectModal.iconFor、ExpertsView.skillTile）。`ExpertsView` 保留 `SKILLHUB_*` 从 `catalog.ts` 直取。

### 验证
- `py_compile` 全过；隔离库 smoke：20 kinds 与 JSON 源**逐字一致**、幂等、按行 disable/改 sort 均生效、SKILLHUB_* 已跳过。
- `npx tsc --noEmit` 通过；`npx vite build` 通过。
- 硬重启 :8000，`GET /api/catalog` 200（20 kinds、无 SKILLHUB_*、CONN_META 为对象、READY_CONNECTORS 为数组）。
- Playwright（**明暗双主题**）：专家页精选场景（EXP_SCENES×6）/分类（EXP_CATS×15）/专家网格、项目页模板（PROJ_TPL×5）、新建项目弹窗均渲染**逐字一致**、暗色可读；`/api/catalog` 200、store 已 hydrate；除 favicon 404 外无 console 错误。
- **驱动 UI 抓到并修复一个真 bug**：`NewProjectModal` 的 `PickerOverlay` 是独立组件、漏挂 `useCatalog()` → 打开连接器选择器时 `NP_CONNS is not defined` 崩溃。**注意：`tsc` 未报此错（增量缓存漏检），靠浏览器实测发现**。修后连接器选择器 0 错误、`内置/需配置` 徽标正确（`READY_CONNECTORS.has()`/`NEEDS_TOKEN_CONNECTORS.has()` Set 路径生效）。
- edit-row：删除库中 SKILLHUB_* 行后 `/api/catalog` 立即反映（20 kinds）。

注：真库（gitignored）曾被并发会话的后端重启用本 issue mid-flight 的 no-skip 种子灌入 SKILLHUB_* 行，已手动清除，与 `_SHOWCASE_SKIP` 最终状态一致。

commit：未提交（待用户确认；共享工作树，提交需按 hunk 暂存，排除 WB-064 的 skills_store.py/routers/skills.py 及 main.py 里非我 hunk）。
