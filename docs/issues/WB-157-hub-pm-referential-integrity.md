---
id: WB-157
title: Hub PM 引用完整性 —— parent_id/milestone_id 跨项目未校验 + 级联删除/清空无 project 过滤
severity: P2
area: backend
status: fixed
origin: 🆕 近期改动
files:
  - hub/routers/work_items.py:80
  - hub/db.py:812
  - hub/db.py:865
created: 2026-07-14
---

## 问题

Hub 专业 PM（WB-104/105）宽松校验引入引用完整性漏洞：

1. `work_items.py` create/update 把 `parent_id`/`milestone_id` **原样落库**，不校验它们属于同一项目。
2. `db.py:812-818` `delete_work_item` 里 `DELETE FROM work_items WHERE parent_id=?` **全局无 project_id 过滤**；`db.py:865-870` `delete_milestone` 的 `UPDATE work_items SET milestone_id='' WHERE milestone_id=?` 同样全局。

## 触发场景

- **跨项目级联删除**：项目 B 成员把 B 任务的 `parent_id` 设为项目 A 的某 work-item id；当 A 的 owner 删那个 item，B 的任务被静默跨租户级联删除。同理外部 `milestone_id` 被别项目删里程碑时清空。
- **项目内完整性**：把任务 `parent_id` 设成不存在/自身 id → 该任务有 parent 从而被排除出看板根、又不在任何真 parent 下 → 从所有视图消失但仍在库。

## 影响

P2：跨项目静默删数据 + 任务「幽灵消失」。仅 Hub 部署下。

## 建议修法

1. create/update：校验 `parent_id`/`milestone_id` 引用的是**同项目**的行（否则拒绝或置空；拒绝自引用/环）。
2. 级联 `DELETE`/`UPDATE` 加 `AND project_id=?`。

## 验证

- `py_compile`（hub）+ TestClient 冒烟。
- 跨项目 parent_id 被拒/置空；删 A 的 item 不动 B 的任务；删里程碑只清本项目引用。
- 回归：同项目子任务/里程碑 CRUD 正常。

## 处理记录（2026-07-14）

- 改动：
  - `hub/routers/work_items.py`：新增 `_sanitize_refs(project_id, self_id, changes)`（parent_id/milestone_id 归一到同项目存在的行，否则置空；拒自引用）；create 与 update 都调用。
  - `hub/db.py`：`delete_work_item` 级联子任务加 `AND project_id=?`；`delete_milestone` 解绑加 `AND project_id=?`（先查该行 project_id）。
- 验证：py_compile 过；隔离 Hub TestClient 冒烟——B 项目任务设 A 项目任务为 parent → 落库为 ''；自身为 parent → 置空。
- commit：未提交（待用户确认）。
