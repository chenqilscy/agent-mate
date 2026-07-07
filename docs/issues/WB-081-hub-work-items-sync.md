---
id: WB-081
title: 团队计划/任务 —— Hub work_items 模型 + 路由 + 本地⇄Hub 同步 + 门户看板
severity: P2
area: fullstack
status: fixed
origin: WB-078 epic
files:
  - hub/models.py
  - hub/db.py
  - hub/routers/
  - backend/hub_sync.py
  - hub/web/console.html
created: 2026-07-08
---

## 问题

App 的 work_items（计划/任务看板）目前**本地独有**，Hub 无模型、无同步，故门户无法管理团队计划/任务。

## 触发场景

团队想在门户看/管项目的计划看板与任务列表 —— 数据不在 Hub。

## 影响

P2：管理面里最重的一块；触碰本地⇄Hub 同步。epic 内殿后。

## 建议修法

- **Hub 模型** `work_items`(id / project_id / title / status[todo·doing·paused·done] / source / assignee / order / created_at / updated_at) + DAO。
- **路由** `GET/POST/PATCH/DELETE /projects/{id}/work-items`（access-gated；Viewer 只读、Member+ 可写）。
- **同步**（扩展 WB-062）：下行 pull 把 Hub work_items 镜像进本地 backend；上行把本地新增/改状态回传 Hub。
  团队共享，冲突以 Hub 为准。保持离线可用（Hub 不可达→本地照旧）。
- **门户 UI**：看板（4 列拖拽）+ 列表，与 App「计划/任务」tab 对齐。

## 验证

门户建/拖动/改任务→持久化 Hub；本地 App pull 后一致；Viewer 只读；Hub 不可达时本地 work_items 照常。

## 处理记录（2026-07-08）

**已交付 Hub 侧 + 门户看板**（团队在 BuddyWebMgr 里管计划/任务）：
- `hub/db.py`：`work_items` 表（id/project_id/title/status[todo·doing·paused·done]/source/assignee/description/sort/时间戳）+ DAO（create/list/get/update/delete，create 自动排到该列末尾）。
- `hub/routers/work_items.py`（新）：`GET/POST/PATCH/DELETE /projects/{id}/work-items`，access-gated（owner OR 成员）、Viewer 只读（can_write 兜底 403）、跨项目 wid 校验。`main.py` 挂载。
- `hub/web/console.html`：项目详情加「计划/任务」看板卡——4 列（待办/进行中/暂停/完成）+ 新增待办 + 每项状态 select 移动 + 删除；Viewer 只读。
- **验证**：Playwright alice(admin)→项目→看板：API/UI 建任务、select 移「API 测试任务」待办→进行中（列计数 待办·1/进行中·1 实时更新）、API 核对 status 持久化。

**拆出二期**：本地 App ⇄ Hub work_items 双向同步（App「计划/任务」tab ↔ Hub 团队任务）另立 [WB-091](WB-091-local-hub-work-items-sync.md)——
它是深度集成、且触碰正被并发会话重构的 `backend/`，故按 epic「可拆二期」后置。门户侧管理（本 issue 的「管理面」核心）已完整可用。
