---
id: WB-105
title: Hub 专业 PM API（work_items 全字段 + 子任务 + milestones CRUD + 活动 feed）
severity: P1
area: backend
status: fixed
origin: WB-103 分片 P1
files:
  - hub/routers/work_items.py
  - hub/routers/milestones.py
  - hub/main.py
created: 2026-07-09
---

## 问题

新数据模型（WB-104）需要 API 暴露：任务全字段读写 + 子任务 + 里程碑 CRUD + 活动流查询。见 epic [WB-103](WB-103-professional-pm-epic.md)。

## 建议修法

- `hub/routers/work_items.py`：`CreateBody/UpdateBody` 补 `priority/due_date/start_date/labels/parent_id/milestone_id`；create/update 落新字段并写活动流（关键字段变化逐条 `log_work_item_activity`）；新增 `GET .../work-items/{wid}/activity` 与 `GET .../activity`。
- 新 `hub/routers/milestones.py`：里程碑 CRUD（access-gated，Viewer 只读）。
- `hub/main.py`：装配 milestones 路由。

## 决策

- **assignee/priority 宽松校验**：不硬拒非成员 assignee / 非法 priority（非法 priority 静默归空），以**保护 App↔Hub 同步健壮性**（同步写代理传入的值不应打断）；成员约束由门户 UI 的下拉承担而非 API 硬门。

## 验证

进程内 TestClient（临时 DB，`backend/.venv`）冒烟 20 项全 PASS：注册/建项目/建里程碑/列里程碑/建任务(带 priority·due·labels·milestone)/labels 解析为列表/建子任务/非法 priority 归空/PATCH 触发活动/活动含 created+status+priority/列任务/删里程碑解绑任务/删父任务级联子任务。

## 处理记录（2026-07-09）
- 改动：见 files；活动流来自真实操作事件（铁律#1，无假数据）。
- 验证：`py_compile` 过；冒烟全 PASS。
- commit：未提交（等用户）。
