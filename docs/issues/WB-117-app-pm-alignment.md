---
id: WB-117
title: App 端项目管理对齐 Manager（epic）—— 片1：工时字段全链路打通
severity: P2
area: fullstack
status: in-progress   # epic 持续；片1 已 done（见处理记录）
origin: WB-112/113/114/115/116 的 PM 增强目前多在 Manager 控制台，App（React src/）项目工作台未跟进
files:
  - backend/storage/models.py
  - backend/storage/db.py
  - backend/routers/work_items.py
  - src/lib/types.ts
  - src/stores/workItemStore.ts
  - src/components/project/ProjectWork.tsx
created: 2026-07-10
---

## 背景

Manager（控制台）已做完 PM 工作台重构 + 身份强映射 + 看板/视图增强 + 任务模板/内联编辑 + 工作量视图 + 任务评论 + 工时。
App 桌面端（`src/`）的项目工作台（KanbanBoard 计划 / TaskList 任务，WB-108）已较专业，但缺 Manager 新增的能力。
本 epic 分片把 App 端对齐。**片1 = 工时字段（estimate_h/spent_h）全链路**（WB-116 此前 Manager-only）。

## 片1 修法（工时全链路）

- **App 后端**：`models.py` WorkItem 加 `estimate_h/spent_h: float=0`；`db.py` `_migrate_columns` + CREATE + `_row_to_work_item` + `create_work_item` + `mirror_hub_work_items` + `update_work_item` 带两字段；`routers/work_items.py` Create/Update Body + `_hub_view` 透传 + 写代理 patch 带上。
- **App 前端**：`types.ts` WorkItem 加两字段；`workItemStore` patch/create 支持；任务详情弹窗加 预估工时/已投入 输入。

## 后续片（App 对齐 epic 余项）

- 视图对齐：列表/甘特/工作量视图、WIP/泳道/保存视图（App 目前只有看板）。
- 任务模板 / 列表内联编辑（App）。
- 任务级评论（App 复用 Hub 端点，App 后端加代理 + 任务详情评论区）。

## 验证

- App 后端：HTTP create/patch estimate_h/spent_h 落库回读；hub-origin 经代理回读（重启后端）。
- tsc 过；App UI 任务详情填工时保存回读；明暗双主题看一眼。

## 处理记录

2026-07-10 **片1（工时全链路）done**：
- App 后端：`models.py` WorkItem 加 `estimate_h/spent_h: float=0`（asdict 自动进 to_dict）；`db.py` CREATE + `_migrate_columns` + `_row_to_work_item` + `create_work_item` + `mirror_hub_work_items` + `update_work_item` 全带两字段；`routers/work_items.py` Create/Update Body + `_hub_view` 透传 + 写代理 create body/update keys 带上。
- Hub 侧补：`hub/db.py` `create_work_item` 签名+INSERT 加两字段（此前只加了 update/迁移）；`hub/routers/work_items.py` `CreateBody` 加两字段——让 App→Hub create-with-hours 也不丢。
- App 前端：`types.ts` WorkItem + `api.ts` create/update 载荷 + `workItemStore` WorkItemPatch 加两字段；`ProjectWork.tsx` 任务详情弹窗加「工时（小时）」预估/已投入 输入（np-input，blur 即 update）。
- 验证：`npx tsc --noEmit` 过、backend+hub `py_compile` 过；**硬重启 :8000**（reload 未跑迁移，CLAUDE.md 坑）后 API create 6/2→patch spent 5→list 回读全对；App :5173 任务详情弹窗见「工时（小时）」两输入、编辑 est=8/spent=3 经 update→PATCH 真落库（focusout 触发 React onBlur）；0 控制台报错；已重置 demo 数据。
- Hub create 改动（`hub/db.py`/`hub/routers`）需 :8100 重启生效——本片改后已重启 :8100，PATCH 工时早已可用、create-with-hours 亦通。

## epic 余项（后续片）

见上「后续片」：App 端 列表/甘特/工作量视图、WIP/泳道/保存视图、任务模板/内联编辑、任务级评论。
