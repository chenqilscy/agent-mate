---
id: WB-109
title: App 精选技能区消费 Hub 的 SKILLHUB_FEATURED（打通 mgr「加入精选」→ App，渲染真图标）
severity: P3
area: frontend
status: fixed
origin: 用户选 B（WB-092/WB-084 精选下发缺口）
files:
  - src/stores/catalogStore.ts
  - src/views/ExpertsView.tsx
created: 2026-07-09
---

## 问题

BuddyWebMgr 目录中心 SkillHub 的「加入精选」写 Hub `SKILLHUB_FEATURED`（完整技能对象），本地 backend pull 下发、
`/api/catalog` 也会带上（`showcase_all` 覆盖 downlink 分类，实测会 surface）。但 **App 的「精选技能」区只读静态
`data/catalog.ts` 的 `SKILLHUB_FEATURED`（固定 5 元组），不从 catalogStore 取、也不认对象形态** → mgr 的精选**根本到不了 App**。

## 触发场景

管理员在 mgr「加入精选」几个技能 → 用户在 App 技能页「精选技能」区看不到，仍是静态那几个。

## 影响

P3：打通「运营精选 → App 展示」的最后一公里（选项 B）。注：精选=展示/推荐，安装才是可用，二者独立，本 issue 只管展示打通。

## 建议修法（纯前端）

- `catalogStore`：加 `skillFeatured: SkillCard[]`，`load()` 从 `raw['SKILLHUB_FEATURED']`（Hub 下发的对象数组）填；无下发 → 空。
- `ExpertsView` 精选区：`skillFeatured` 非空 → 用它（对象），否则回退静态元组。`FeaturedCard` 归一成 `{iconUrl?,icon,name,desc,badge}`——
  有 `iconUrl` 渲染真图标 `<img>`（.fc-ic 38×38，object-fit cover，broken 隐藏），否则 emoji；点开详情/安装照旧。

## 验证

mgr 加入精选 → App pull 后精选区显示这些技能 + 真图标；取消精选后消失；未接 Hub 时精选区仍是静态兜底。

## 处理记录（2026-07-09）

纯前端（`src/`，未碰并发会话正改的 `hub/`）：
- `catalogStore`：加 `skillFeatured: SkillCard[]`，`load()` 从 `raw['SKILLHUB_FEATURED']` 填（Hub 下发的对象数组；无下发→空）。
- `ExpertsView`：`FeaturedCard` 归一成 `FeaturedItem {iconUrl?,icon,name,desc,badge}`——有 iconUrl 渲染 `<img class=fc-ic object-fit:cover>`(broken 隐藏)，否则 emoji；
  `FeaturedSkills` 从 `catalogStore.skillFeatured`（非空）取对象、否则回退静态元组，「换一换」按池长轮换。
- **验证**：tsc + vite build 过；**数据链路 E2E**：起隔离 backend :8003(HUB_URL→隔离 Hub :8100，有 1 条精选 `summarize`)→ pull → 本地
  `GET /api/catalog` **surface `SKILLHUB_FEATURED`=1 个对象（带 iconUrl）** → App catalogStore 即得 skillFeatured。
- **未做**：App 精选区的**界面级实时渲染**（需 vite→自定 backend 代理 + Playwright，当前 vite 硬编 :8000、并发占 :8000 真库 + Playwright 浏览器争用）——渲染逻辑 tsc 验、自包含、数据链路已实测；界面级留待有干净环境时补。
