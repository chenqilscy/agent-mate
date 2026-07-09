---
id: WB-108
title: App↔Hub 专业 PM 打通（同步扩展 + 本地模型对齐 + App 工作台任务 UI）
severity: P1
area: fullstack
status: fixed
origin: WB-103 分片 P1
files:
  - backend/storage/models.py
  - backend/storage/db.py
  - backend/routers/work_items.py
  - backend/routers/milestones.py
  - backend/hub_client.py
  - backend/main.py
  - src/components/project/ProjectWork.tsx
created: 2026-07-09
---

## 问题

WB-104/105 让 Hub 具备专业 PM 数据/API 后，App 端要与之**打通**：新字段（优先级/截止/开始/标签/子任务/里程碑）在 App 项目工作台可见可编辑，且 hub-origin（团队）项目双向同步。保留 local-first（离线全功能，铁律#4）。见 epic [WB-103](WB-103-professional-pm-epic.md)。

## 建议修法（分两片）

**108a 后端**（本地模型 + 同步 + 路由）：
- `WorkItem` 模型 + 本地 `work_items` 表 + 迁移：增 priority/start_date/labels/parent_id/milestone_id。
- 本地 `milestones` 表 + CRUD + `mirror_hub_milestones`。
- `mirror_hub_work_items` 镜像 Hub 新字段（含此前被丢弃的 due_date）。
- App `work_items` 路由：Body/`_hub_view`/hub-proxy 白名单/本地 CRUD 全部收发新字段（hub_client work_items 代理本就字段无关，写代理天然透传）。
- 新 App `milestones` 路由 + `hub_client` 里程碑代理（hub-origin 走 Hub + 本地镜像，离线回退本地）。

**108b 前端**：`ProjectWork.tsx` + 类型：任务卡/详情/新建接 优先级·标签·截止·负责人·里程碑·子任务；里程碑管理（列表/新建/指派）。

## 验证

- 108a：`py_compile` 全过；storage 层冒烟 25 项全 PASS（新字段持久化/labels JSON/子任务级联/里程碑 CRUD·解绑/Hub 形状 mirror）；路由本地路径冒烟 12 项全 PASS（字段串联/labels 清洗/优先级归空/里程碑绑定·解绑）。
- 108b：`tsc --noEmit` 过；Playwright 实测——App 项目工作台建/改任务的新字段真落库；hub-origin 项目与门户双向可见（待门户 UI 期或直接对 Hub 验）。
- 离线/本地项目：新字段纯本地全功能。

## 处理记录（2026-07-09）
- **108a 后端 ✅**：见 files（models/db/work_items 路由/milestones 路由/hub_client/main）。storage 冒烟 25 项 + 路由本地路径 12 项全过；全量 py_compile 过。
- **108b 前端 ✅**：`types.ts`（WorkItem 增 priority/start_date/labels/parent_id/milestone_id + WorkPriority + Milestone）、`api.ts`（work-item body 扩展 + milestones 4 端点）、`workItemStore.ts`（新字段 + milestones 状态/loadMilestones/addMilestone）、`ProjectWork.tsx`（PriorityPill/MilestonePill(就地新建)/LabelsEditor/LabelBadges，接卡片·详情·新建·任务列表）、`app.css`（`.wb-label-chip` 等，用 brand-soft/brand-600 token，暗色安全）。
- **验证**：`tsc --noEmit` 过、`vite build` 过；隔离栈(临时 DB) HTTP 端到端全过——建项目→里程碑→带优先级/截止/标签/里程碑建任务→列表持久化→labels **去重**→PATCH 改优先级·换标签·清里程碑→非法优先级归空→GET 里程碑。**明暗双主题可视渲染核对：过**——MCP 浏览器被并发会话占用，改用独立 headless chromium+CDP（见 [[cdp-screenshot-when-mcp-browser-locked]]）实截：看板卡片（优先级色点红/橙/绿 + 标签 chip + 🚩 里程碑 + 📅 截止）、新建弹窗（优先级/截止/里程碑 三 pill + 标签编辑器）、详情弹窗（同上 pill + 可删标签）在**暗色 + 浅色**均正确；标签用 brand-soft/brand-600 token，浅色下绿字浅绿底、暗色下绿字暗底，均无白底白字。
- **打通**：hub-origin 项目走 Hub 权威（读代理→镜像新字段、写代理透传→回镜像），本地/离线纯本地全功能。
- commit：未提交（等用户；`hub/web/console.html` 的改动是并发会话的，不并入）。
