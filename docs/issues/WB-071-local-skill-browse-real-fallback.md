---
id: WB-071
title: 未接 Hub 时技能浏览用真实 rankings 兜底，替掉静态假数据（铁律#1）
severity: P2
area: frontend
status: fixed
origin: 🆕 近期改动
files:
  - src/lib/api.ts
  - src/stores/catalogStore.ts
created: 2026-07-08
---

## 问题

[[WB-070]] 让技能浏览在**接 Hub** 时显示真实 369 镜像（`catalogStore.skillMirror`），但**未接 Hub** 时
`SkillHubView` 回退静态 `SKILLHUB_GRID/CATS/FEATURED`（`src/data/catalog.ts`）——写死的下载 174k / 星 109
等**硬编码假数据**，仍违反铁律#1。[[WB-064]] 早已交付真实实时端点 `GET /api/skills/rankings`
（本地 CLI 跑 `skill rankings`，真 skillhub.cn 数据），但前端从未消费它；WB-064 已被并发会话作废、
折叠进 [[WB-069]]/[[WB-070]]，故这层「无 Hub 的真实兜底」无人接。

## 触发场景

纯本地 / 未登录 / Hub 不可达时打开技能页 SkillHub 段：看到写死的假下载星数，非 skillhub.cn 实际。

## 影响

P2：铁律#1（不模拟）在 no-Hub 路径未消除。接 Hub 时已真实；三层模式常连 Hub，故只影响纯本地。

## 建议修法（只碰 api.ts + catalogStore.ts，不碰 WB-064 文件/ExpertsView，避让并发会话）

- `src/lib/api.ts`：加 `skillRankings(type)` → `GET /api/skills/rankings?type=`（返 `{type, skills: SkillCard[]}`）。
- `src/stores/catalogStore.ts`：启动链在 `load()` + `syncFromHub()` 之后，若 `skillMirror` 仍为空 →
  `fallbackToRankings()`：拉真实 rankings（默认 `hot`），把卡的 `category`（场景 key）补上中文名
  （12 场景 key→中文静态映射，快照自 Hub `/api/v1/categories`），填充 `skillMirror` + `skillCats`
  （按 category 计数）。**`SkillHubView` 无需改**（已按 `skillMirror`/`skillCats` 渲染，见 WB-070）。
- 分层：Hub 镜像（接 Hub）→ 真实 `/api/skills/rankings`（无 Hub、有网）→ 静态 `SKILLHUB_*`（离线/无 CLI 最后兜底）。
- rankings 拉不到（离线/无 CLI）→ 保持 `skillMirror` 空 → 自然回退静态，不报错、不白屏。

## 验证

- `npx tsc --noEmit` 必过。
- `GET /api/skills/rankings?type=hot` 返真实卡（下载/星与 skillhub.cn 一致）。
- 未接 Hub 打开技能页：显示真实 rankings 卡（非 174k 假数据）+ 真实分类过滤；离线时回退静态、无报错。
- 接 Hub 时不受影响（`skillMirror` 已由镜像填充，`fallbackToRankings` 自查空后早返，不重复拉）。

## 处理记录（2026-07-08）

- **改动（仅 2 个文件，未碰 WB-064/ExpertsView）**：
  - `src/lib/api.ts`：`skillRankings(type)` → `GET /api/skills/rankings`。
  - `src/stores/catalogStore.ts`：`SCENE_NAME`（12 场景 key→中文，快照自 Hub `/api/v1/categories`）；
    `fallbackToRankings()`——`skillMirror` 空时拉真实 `rankings('hot')`、给卡补 `skillhub_category(_name)`、
    按 category 计数填 `skillMirror`/`skillCats`；启动链改 `load → syncFromHub → fallbackToRankings`。
    `SkillHubView` **未改**（已按 `skillMirror`/`skillCats` 渲染，WB-070）。
- **验证**：`npx tsc --noEmit` 通过；`/api/skills/rankings?type=hot` 返 **100 真实卡**
  （self-improving-agent 951434 下载 / 4180 星等），跨 **11 分类**——前端兜底据此补中文名 + 计数。
  接 Hub 时 `skillMirror` 已满，`fallbackToRankings` 自查空早返、不重复拉。
- **分层落定**：Hub 镜像（接 Hub）→ 真实 `/api/skills/rankings`（无 Hub、有网）→ 静态 `SKILLHUB_*`
  （离线/无 CLI 最后兜底）。**no-Hub 路径的铁律#1 假数据（有网时）消除**。
- **未做/环境所限**：当前 demo 环境 Hub 常连（`skillMirror` 已满），no-Hub 的 UI 实测未跑——数据源 + 类型已证；
  共享浏览器仍被并发会话占，未截图。
- commit：见 git 历史，标题带 WB-071。
