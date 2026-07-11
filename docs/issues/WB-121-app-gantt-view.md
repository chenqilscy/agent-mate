---
id: WB-121
title: App 端 PM 对齐 Manager 片5 —— 甘特视图（时间线 tab）
severity: P2
area: frontend
status: fixed
origin: WB-117 App 对齐 epic 之片5；对齐 Manager pmViewGantt
files:
  - src/components/project/ProjectWork.tsx
  - src/views/ProjectHomeView.tsx
created: 2026-07-10
---

## 背景

Manager 有甘特视图（WB-107/111：今天线 + 月度网格 + 优先级色条）。App 缺。本片加 App 项目页「甘特」tab。

## 建议修法

- `ProjectWork.tsx` 加 `GanttView`：读 workItemStore 有 start/due 的根任务，按相对时间画横条（无 start 用 due 当点）+ 今天竖线 + 6 档日期刻度 + 网格线 + 优先级色条；点条/名开 `TodoDetailModal`。用 `--border/--border-2/--text-3` 双主题。
- `ProjectHomeView.tsx` Tab 加「甘特」+ 渲染 `<GanttView/>`。

## 验证（自动化）

- tsc 过；驱动 App → 甘特 tab，断言横条渲染 + 今天线存在；无排期时空态；0 报错。

## 处理记录

2026-07-10 done：`ProjectWork.tsx` 加 `GanttView`（相对时间横条 + 今天蓝线 + 6 档日期刻度 + 网格线 + 优先级色条；点条/名开 `TodoDetailModal`；`--border/--border-2/--text-3` 双主题；无排期空态）；`ProjectHomeView.tsx` Tab 加「甘特」。自动化验证：tsc 过；给 便签测试 3 任务设 start/due 后驱动 App→甘特 tab，3 横条(title 含日期区间 07-08→07-14 等)渲染、今天线存在、0 报错。纯前端。
