---
id: WB-104
title: Hub 专业 PM 数据模型 + 迁移（work_items 新字段 + milestones + activity）
severity: P1
area: backend
status: fixed
origin: WB-103 分片 P1
files:
  - hub/db.py:179
  - hub/db.py:201
  - hub/db.py:672
created: 2026-07-09
---

## 问题

现有 Hub `work_items` 只有 `title/status/source/assignee/description/sort`，不足以支撑专业 PM（无优先级/截止/标签/子任务/里程碑/活动）。见 epic [WB-103](WB-103-professional-pm-epic.md)。

## 建议修法

`hub/db.py`：
1. `work_items` 增列 `priority/due_date/start_date/labels(JSON)/parent_id/milestone_id`（CREATE TABLE + 老库幂等 `ALTER` 补列）。
2. 新表 `milestones`、`work_item_activity`（`CREATE TABLE IF NOT EXISTS`，老库自动补）。
3. CRUD：`create/update_work_item` 支持新字段（`labels` JSON 存取，`_row_to_work_item` 回列表）；`delete_work_item` 连带子任务 + 活动；新增 `*_milestone`、`log/list_work_item_activity`。

## 验证

`python -m py_compile hub/db.py` 过；进程内 TestClient 冒烟（见 WB-105 处理记录）覆盖建/改/删任务·里程碑·子任务级联·活动流·labels 解析。

## 处理记录（2026-07-09）
- 改动：`hub/db.py` 三处——建表扩列 + 两新表（179）、老库 ALTER 幂等补列（201）、CRUD 扩展 + milestones/activity 函数（672）。非破坏：全部带默认值、`IF NOT EXISTS`。
- 验证：`py_compile` 过；冒烟 20 项全 PASS（见 WB-105）。
- commit：未提交（等用户；与并发会话隔离，仅 hub 后端文件）。
