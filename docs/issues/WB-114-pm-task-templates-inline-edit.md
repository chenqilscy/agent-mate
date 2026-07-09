---
id: WB-114
title: PM 细化之二（纯前端片）—— 任务模板 + 列表内联编辑 + 子任务进度条
severity: P2
area: frontend
status: fixed
origin: WB-112f PM 细化四方向「任务字段丰富」，本片取纯前端可落地部分
files:
  - hub/web/console.html
created: 2026-07-10
---

## 背景

「任务字段丰富」里自定义字段/任务依赖/附件需后端加字段（单独设计，见末尾）；本片先做**纯前端**能落地、日常高价值的三项。

## 建议修法（`hub/web/console.html` PM 区，续 `pm-` 前缀）

1. **任务模板**：per-project 存 localStorage（`pm.tpl.<pid>`）。模板 = 一组字段默认值（priority/labels/milestone_id/assignee/description）。
   - 工具栏/新建区「从模板…」下拉：选中 → 提示标题 → 用模板字段 `POST work-items`，刷新并打开抽屉续编辑。
   - 任务详情抽屉加「存为模板」：把当前任务字段存成命名模板。
   - 模板管理（删除）。
2. **列表内联编辑**：列表视图里 状态/优先级/负责人/里程碑 单元格点击就地变 `<select>`，改完即 `PATCH` + 刷新；点单元格不触发打开抽屉（`stopPropagation`）。Viewer 只读不启用。
3. **子任务进度条**：抽屉子任务区加完成进度条（已完成/总数）。

## 验证

- 本机 Manager :8100 CDP：存模板→从模板新建（字段带出）→删除模板；列表点状态/优先级/负责人/里程碑就地改、真落库、不误开抽屉；子任务进度条随勾选更新；Viewer 只读回归；0 控制台报错。无后端改动。

## 处理记录

2026-07-10 done（仅改 `hub/web/console.html`，续 `pm-` 前缀）：
- 任务模板：`pm.tpl.<pid>` localStorage；工具栏「🧩 从模板…」下拉(选中→`pmNewFromTpl`：提示标题→带模板字段建任务→刷新并打开抽屉) + 「🗑」删所选；抽屉页脚「存为模板」(`pm-f-tpl`，抓当前表单 priority/assignee/milestone/desc/labels 存命名模板)。
- 列表内联编辑：状态/优先级/负责人/里程碑单元格加 `.ecol.pm-ecell`+`data-f/data-id`，点击→`pmInlineEdit` 就地换 `<select>`，change→PATCH+刷新、blur 无改动还原；`stopPropagation` 不误开抽屉；Viewer 无 `.pm-ecell` 不可编辑。
- 子任务进度条：抽屉子任务区标题改 `done/total` + 进度条（`pm-bar`）。
- 验证（本机 Manager :8100 CDP，stub prompt）：模板入下拉、从模板建的任务带出 priority=high/labels/desc；列表点状态→done 真落库；父任务 1/2 子完成→进度条 50%；0 控制台报错。无后端改动。

## 后续（需后端，另立设计）

- **任务依赖**（前置/后置 blocked_by）：Hub+App 加字段/校验环 + 甘特依赖线；更新数据分层规范。
- **自定义字段**：work_items 加 JSON `custom` 字段，项目级字段定义。
- **附件引用登记**：Hub 目前无 attachments（App 有）；且「本地路径」对团队他人无意义（见数据分层规范红线 2）——需先决策附件引用是否/如何上云，再落地。
