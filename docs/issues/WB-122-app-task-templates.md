---
id: WB-122
title: App 端 PM 对齐 Manager 片6 —— 任务模板（存为模板 + 从模板新建）
severity: P2
area: frontend
status: fixed
origin: WB-117 App 对齐 epic 之片6；对齐 Manager WB-114 任务模板
files:
  - src/components/project/ProjectWork.tsx
created: 2026-07-10
---

## 背景

Manager 有任务模板（WB-114，per-project localStorage：详情「存为模板」+ 工具栏「从模板新建」）。App 缺。本片搬到 App。

## 建议修法（`ProjectWork.tsx`）

- 模块级 `getTpl/setTpl`（`pm.tpl.<pid>` localStorage；模板 = {name, priority, labels, milestone_id, description}）。
- 详情弹窗 `TodoDetailModal`：加「存为模板」（以标题命名，抓当前字段存模板 + toast）。
- 看板 `KanbanBoard` 工具栏：有模板时加「从模板」下拉（FilterDropdown），选中 → `add({title:模板名, ...字段})` → 开详情续编辑。

## 验证（自动化）

- tsc 过；驱动 App：详情存模板 → 看板「从模板」下拉出现该模板 → 选中建任务带出字段；0 报错。

## 处理记录

2026-07-10 done：模块级 `WorkTemplate`/`getTpl`/`setTpl`（`pm.tpl.<pid>` localStorage）；`TodoDetailModal` 顶部加「存为模板」(以标题命名抓当前字段+toast)；`KanbanBoard` 加 `projectId`/`templates`/`newFromTpl`，工具栏有模板时加「🧩 从模板」FilterDropdown(选中→add 带模板字段→开详情)。自动化验证：tsc 过；驱动 App→计划→开卡「111」→存为模板→localStorage 1 条；再「从模板」下拉选「111」→任务数 10→11、详情弹窗标题「111」；0 报错；已删重复任务。纯前端。
