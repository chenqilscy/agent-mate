---
id: WB-081
title: 团队计划/任务 —— Hub work_items 模型 + 路由 + 本地⇄Hub 同步 + 门户看板
severity: P2
area: backend
status: open
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
