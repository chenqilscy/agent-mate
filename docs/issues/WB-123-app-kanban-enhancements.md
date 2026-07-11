---
id: WB-123
title: App 端 PM 对齐 Manager 片7 —— 看板增强（WIP 上限 + 泳道分组 + 保存视图）
severity: P2
area: frontend
status: fixed
origin: WB-117 App 对齐 epic 之片7；对齐 Manager WB-113 看板增强
files:
  - src/components/project/ProjectWork.tsx
created: 2026-07-10
---

## 背景

Manager 看板有 WIP 上限/泳道分组/保存视图（WB-113）。App KanbanBoard 只有筛选/批量/搜索。本片对齐。

## 建议修法（`ProjectWork.tsx`）

- 模块级 `getWip/setWip`（`pm.wip.<pid>`）、`getKViews/setKViews`（`pm.kview.<pid>`）。
- `KanbanBoard`：抽 `renderKanban(source)`（列渲染），WIP：列头显 count 或 count/limit、超限标红、`WIP` 开关出数字输入；`group`(none/assignee/milestone)→ 泳道；工具栏加「分组」下拉 + 「视图」下拉(应用) + 「保存视图」；拖拽仍只改 status。

## 验证（自动化）

- tsc 过；驱动 App→计划：设 WIP 超限标红；按负责人分组出泳道；保存/应用视图；0 报错。

## 处理记录

2026-07-10 done：模块级 `getWip/setWip`（`pm.wip.<pid>`）、`getKViews/setKViews`（`pm.kview.<pid>`）；`KanbanBoard` 加 `group/wipEdit/tick` 状态 + `wip/kviews/lanes` 派生 + `saveWip/applyKView/saveKView` 处理器；抽 `renderKanban(source)`（列渲染，WIP：列头 count 或 count/limit、超限红底、编辑态数字输入 onBlur 存）；工具栏加「分组」下拉(none/负责人/里程碑) + 「视图」下拉(应用) + 「保存视图」(prompt 命名) + 「WIP」开关；`group!=='none'` → 按 lanes 渲染泳道(每泳道一 renderKanban)；拖拽仍只改 status。
- **自动化验证**：tsc 过；驱动 App→计划：WIP 开关出 4 列数字输入、设 待办=5 → 列头「10/5」红底(rgb 239,68,68)；「按负责人」→ 泳道头「奇 10」；stub prompt「保存视图」→ localStorage `pm.kview` 存 {name:'我的视图',group:'assignee'}、「视图」下拉出现；0 控制台报错；已清理测试 localStorage。纯前端。
