---
id: WB-110
title: BuddyWebMgr 门户 PM 增强 —— 看板拖拽换列 + 项目级任务活动流面板
severity: P2
area: frontend
status: fixed
origin: WB-103 收尾增强（epic 处理记录列为可选项）
files:
  - hub/web/console.html
created: 2026-07-09
---

## 问题

两个 epic WB-103 的收尾缺口：
1. **看板无拖拽**：WB-106 后卡片改状态必须开抽屉改下拉——专业 PM 的标配是拖卡换列（App 端看板早有 HTML5 拖拽）。
2. **项目级活动流无 UI**：WB-105 已有 `GET /projects/{pid}/activity` 端点，但门户只在任务抽屉里显示单任务活动，项目维度的「谁改了什么」没有入口。

## 建议修法

`hub/web/console.html`（续 pm- 前缀 + 内联样式，不碰 `<style>`，避开并发区）：
- **拖拽**：`pmCardHtml` 卡片加 `draggable`（Viewer 只读不加）；`pmViewBoard` 列容器 `data-colstack` 接 dragover（高亮）/dragleave/drop → `PATCH status` → `loadWorkItems` 刷新。
- **活动面板**：`projectDetail` 右列「时间线」下加「任务活动」卡片（`#pm-activity`）；新 `pmLoadActivity(pid)` 读项目级 activity 端点渲染（actor · kind · detail · ago，前 30 条）；`loadWorkItems` 成功后顺带刷新（任何任务变更后活动面板保持新鲜）。

## 验证

隔离 Hub + CDP：派发带共享 DataTransfer 的 DragEvent（已知坑：原生 HTML5 拖拽无法用鼠标事件模拟）把卡从「待办」拖到「进行中」→ Hub 数据真变、看板刷新、活动面板出现 status 事件；Viewer 只读不可拖；无 JS 报错。

## 处理记录（2026-07-09）
- 改动：`hub/web/console.html` —— ①`pmCardHtml` 卡片 `draggable`（`PM_CTX.ro` 不加）；②`pmViewBoard` 列容器 `data-colstack` + dragstart/dragover(绿色高亮)/dragleave/drop→`PATCH status`→`loadWorkItems`；③`projectDetail` 右列加「任务活动」卡（`#pm-activity`）+ 新 `pmLoadActivity(pid)`（读 `GET /projects/{pid}/activity` 渲前 30 条）+ `loadWorkItems` 成功后顺带刷新。续 pm- 前缀 + 内联样式。
- 验证：`node --check` 过；隔离 Hub(:8155)+CDP——拖拽派发后探针 BEFORE `todo:[待拖拽任务]` → AFTER `doing:[待拖拽任务,进行中任务]`（重新 GET 渲染=Hub 真变）；活动面板自动刷新、顶部出现 `pmuser · status · todo→doing`；截图确认列计数 待办·0/进行中·2；**JS ERRORS: NONE**。
- commit：console.html 共享，按 hunk 只暂存我的块。
