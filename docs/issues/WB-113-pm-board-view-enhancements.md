---
id: WB-113
title: PM 细化之一 —— 看板/视图增强（泳道分组 + WIP 上限 + 保存的视图 + 批量操作）
severity: P2
area: frontend
status: fixed
origin: WB-112f PM 细化四方向（用户全选），本片 = 看板/视图增强
files:
  - hub/web/console.html
created: 2026-07-10
---

## 背景

WB-111 把 Manager 项目管理做成了专业工作台。用户要 PM 再细化丰富，选了四方向；本片做**看板/视图增强**（纯前端 console）。

## 建议修法（`hub/web/console.html` PM 区，续 `pm-` 前缀）

1. **泳道分组**：工具栏加「分组」选择（不分组 / 按负责人 / 按里程碑）。分组时看板按组渲染横向泳道，每条泳道内是该组的四状态列；拖拽换列仍只改 status（不改分组维度）。`PM_GROUP` 状态。
2. **列 WIP 上限**：每状态可设 WIP 上限（`PM_WIP` per project 存 localStorage）；列头显示 `count` 或 `count/limit`，超限列头/计数标红。工具栏「WIP」按钮开内联编辑（四个数字输入 + 保存）。
3. **保存的筛选视图**：工具栏「视图」下拉列出已存视图 + 保存当前（名/筛选/排序/视图/分组）+ 删除；存 localStorage `pm.views.<pid>`。应用即套用整组筛选。
4. **批量操作**（列表视图）：行前多选框 + 全选；选中非空时出现批量条（改状态 / 改负责人 / 改里程碑 / 删除），顺序调用 API 后刷新。Viewer 只读不显示。

## 验证

- 隔离/本机 Manager :8100：泳道按负责人/里程碑分组正确、拖拽仍换列；WIP 超限标红且 localStorage 持久；保存/应用/删除视图；列表多选 → 批量改状态/负责人/删除真落库；明暗（控制台单暗色）对比度 OK；0 控制台报错。Viewer 只读回归。
- 无后端改动。

## 处理记录

2026-07-10 done（仅改 `hub/web/console.html`，续 `pm-` 前缀）：
- 状态：`PM_GROUP`（none/assignee/milestone）、`PM_SEL`（列表批量选中 id Set）、`PM_WIPEDIT`；WIP 上限/保存视图 per-project 存 localStorage（`pm.wip.<pid>` / `pm.views.<pid>`）。
- CSS：`.pm-lane/.pm-lanehead/.cnt.over/.pm-wipin/.pm-batch/.pm-selrow`。
- 助手：`pmGroups`（分组，未指派/无里程碑排最后）、`pmApplyView`、`pmBatch`/`pmBatchDelete`。
- 工具栏（`pmRender`）：加「分组」选择 + 「视图」下拉(应用) + 「保存视图」(prompt 命名) + 「🗑」(删所选视图) + 看板态「WIP 上限」开关按钮，并接线。
- 看板（`pmViewBoard`）：抽 `boardFor(items)`；`PM_GROUP!=="none"` → 按 `pmGroups` 渲染横向泳道，每泳道内四状态列；列头 WIP 显 `count/limit`、超限计数 `.over` 标红、编辑态出数字输入（>0 存、空/0 清）；拖拽仍只改 status 不动分组维度。
- 列表（`pmViewList`）：行前多选框 + 表头全选；选中非空出批量条（改状态/改负责人/改里程碑/删除/取消）；勾选 `stopPropagation` 不触发打开抽屉；选中项按当前 roots 剪枝防陈旧。Viewer 只读全不显示。
- **验证**（本机 Manager :8100，Playwright/CDP）：按负责人泳道 = `demopm 1`+`未指派 6`、按里程碑 = `设计定稿 3`+`开发上线 4`；WIP doing=1 → `2/1` 标红(.over)；保存视图入下拉、`pmApplyView` 恢复 status=doing；列表选 2 个 todo → `pmBatch({status:paused})` 两条真落库 paused、选择清空；0 控制台报错。无后端改动。
