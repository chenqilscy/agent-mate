---
id: WB-070
title: 前端接入 Hub SkillHub 镜像目录 + 搜索代理（触发下行 pull + catalogStore 承载 skill 类 + ExpertsView 改读 + 搜索接线）
severity: P2
area: frontend
status: fixed
origin: 🆕 近期改动
files:
  - src/lib/api.ts
  - src/stores/catalogStore.ts
  - src/views/ExpertsView.tsx
  - backend/routers/skills.py
  - backend/hub_client.py
  - backend/hub_sync.py
created: 2026-07-08
---

## 问题

[[WB-069]] 已在 Hub 侧把 SkillHub 目录定时镜像成 `catalog_items(category='skill' + 'skill-category')`
（369 技能、12 分类）并加了查询代理 `GET /api/catalog/skills/search`。但**前端还没接**：

- 技能页浏览（精选/网格/分类过滤）仍读 `src/data/catalog.ts` 的**静态** `SKILLHUB_*`（[[WB-064]] 遗留），
  非 Hub 镜像；分类计数/下载星数与 SkillHub 不同步。
- 本地 backend 的 Hub 下行 pull（`hub_sync.pull_catalog` → `catalog_downlink` → `showcase_all` 已 merge
  `skill`/`skill-category` 进本地 `GET /api/catalog`）**已就绪但从没被触发**（无人调 `POST /api/hub/pull`）。
- `catalogStore` 的 `Pick`/`FALLBACK` 只白名单了固定键，**丢弃** `skill`/`skill-category` 两类。
- 技能页搜索框（`ExpertsView.tsx` 的 `<input>`）是**死的**（无 value/onChange/handler）。

## 触发场景

打开技能页：看到的是静态假数据（写死的下载 174k/星 109），不是 Hub 镜像的真实 369 技能；搜索框打字无反应。

## 建议修法（前端只连本地 `:8000`，不直连 Hub）

- **触发下行 pull**：前端登录 Hub 后调 `POST /api/hub/pull`（`src/lib/api.ts` 加 `hubPull()`；`backend/routers/hub.py`
  的端点已在），或后端定时兜底。未接 Hub → 无害返回、前端保留本地兜底。
- **catalogStore 承载**：`src/stores/catalogStore.ts` 加 `skill`/`skill-category` 两类的接收（因带连字符、
  且非 catalog.ts 静态键，走独立 state 字段而非 `Pick`），后端未提供时空/兜底。
- **ExpertsView 改读**：技能浏览（`SkillHubView`/`FeaturedSkills`/分类 chips）**有 Hub 镜像则用镜像卡**
  （字段 `slug/name/description/downloads/stars/iconUrl/skillhub_category`，来自 Hub `_normalize_card`），
  无则回退现有静态 `SKILLHUB_*`（local-first，视觉零重设计、复用现有 class/token）。
- **搜索接线**：给 `<input>` 加 value/state/onChange → 调本地 `GET /api/skills/search`；本地 backend 的
  `search_skills`（`routers/skills.py`）**优先走 Hub 代理**（`hub_client` 加转发 `GET Hub /api/catalog/skills/search`），
  Hub 不可达/未接 → 回退本地 `skills_store.search`。渲染结果网格。

## 依赖 / 边界

- 依赖 [[WB-069]]（Hub 侧镜像 + 代理，已完成）。Hub 镜像浏览需**已连 Hub 并 pull**；纯本地/未连 Hub 时
  回退静态 + 本地 CLI 搜索（离线全功能不受影响）。
- 与 [[WB-067]]（协作面板/通知/Hub 连接入口）**不同范围**，避免撞 `ProjectHomeView`/`notificationStore`。
- 不碰 `catalog.ts` 的 `SKILLHUB_*` 定义（保留作兜底）；[[WB-064]] 的本地 `rankings/search` 作离线兜底保留。

## 验证

- `npx tsc --noEmit` 必过；`vite build` 需要时验证。
- 未接 Hub：技能页浏览=静态兜底、搜索=本地 CLI 结果，一切照常（明暗双主题）。
- 接 Hub 并 pull：浏览显示镜像 369 技能真实下载/星数、按 12 分类过滤；搜索走 Hub 代理返回富结果。
- 后端 `py_compile` 通过；手动跑 `/api/skills/search`（接/不接 Hub 两路）确认。

## 处理记录（2026-07-08）

- **改动**：
  - 后端 `hub_client.py`：加 `search_skillhub(token,q,limit)`（转发 Hub `GET /api/catalog/skills/search`，guarded 返回 None）。
  - 后端 `routers/skills.py`：`GET /api/skills/search` 优先经 Hub 代理（`hub_enabled` + 带 token），未接/不可达/空 → 回退本地 `skills_store.search`；带 `source` 字段。
  - 前端 `lib/types.ts`：`SkillCard`（富字段可选，兼容 Hub 富卡与本地精简结果）。
  - 前端 `lib/api.ts`：`searchSkills(q,limit)`、`hubPull()`。
  - 前端 `stores/catalogStore.ts`：承载 `skillMirror`（raw['skill']）+ `skillCats`（raw['skill-category'][0].items）；启动后 `syncFromHub()` 登录态触发一次 `POST /api/hub/pull` 并重载目录（未接/未登录静默）。
  - 前端 `views/ExpertsView.tsx`：`MirrorSkillCard`（对象卡，iconUrl 图标）+ `SkillSearchResults`（去抖 300ms）；`SkillHubView` 有镜像用镜像（按 12 场景过滤）否则回退静态；顶栏搜索框接线（value/onChange，切 tab 清空）。
- **验证（真实数据，非模拟）**：
  - `npx tsc --noEmit` 通过；`npx vite build` 通过。
  - 搜索路由实跑：未配 HUB_URL → `hub_enabled=False` 回退本地，`search('tencent')` 返回真实 Tencent/腾讯文档/腾讯会议、`source=local`。
  - **浏览镜像数据契约端到端**：Hub `sync_once`（370 项）→ 本地 `replace_all_downlink` → `showcase_all` 产出 `skill`(369) + `skill-category`；复刻 catalogStore 解析得 skillMirror=369、skillCats=12、卡字段齐全（slug/name/description/downloads/stars/iconUrl/skillhub_category*）、12 类计数正确（AI Agent 77 … 教育 5）。
- **未做/环境所限（如实）**：
  - **Playwright 实测被并发会话占用的共享浏览器挡住**（未硬抢），未做明暗双主题实测；搜索路径逻辑简单且路由已返真实数据。
  - 本 dev 环境**未配 HUB_URL**，故 UI 里「浏览到 Hub 镜像 369」无法当场演示（会回退静态）——需连本地 Hub（配 HUB_URL + 登录 + pull）才能看到；数据契约已证通。
  - `FeaturedSkills`/`KitView` 保持静态（local-first 精选/套件，Hub 镜像不含这两类）；`skillTile` 图标查静态未改。
- commit：（见 git 历史，标题带 WB-070）。
