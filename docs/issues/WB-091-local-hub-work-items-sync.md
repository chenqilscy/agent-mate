---
id: WB-091
title: 本地 App ⇄ Hub work_items 双向同步（WB-081 的二期）
severity: P3
area: backend
status: open
origin: WB-081 拆分
files:
  - backend/hub_client.py
  - backend/hub_sync.py
  - backend/routers/work_items.py
created: 2026-07-08
---

## 问题

WB-081 已在 Hub 建 work_items 模型/路由 + 门户看板（团队在 BuddyWebMgr 里管计划/任务）。但本地 App 的
「计划/任务」tab 仍读**本地** work_items，与 Hub 的团队 work_items **未打通**——门户建的任务 App 看不到，反之亦然。

## 触发场景

团队在门户建了任务，队友在本地 App 的项目「计划/任务」tab 里看不到；App 里建的待办也不上 Hub。

## 影响

P3：门户侧管理已可用（WB-081）；本地⇄Hub 打通是深度集成，非阻塞。

## 建议修法

扩展 WB-062 同步：
- **下行**：`hub_sync.pull` 对 hub-origin 项目把 Hub work_items 镜像进本地 work_items 表（字段映射：Hub 无 owner_id/attachments/due_date，取默认）。
- **上行**：本地 work_items 的建/改状态经 `hub_client` 推回 Hub（或走 outbox）。团队共享，冲突以 Hub 为准。
- 保持离线可用（Hub 不可达→本地 work_items 照旧）。
- **注意**：本地 backend 正被并发会话重构（channels/多助理），改 `backend/` 前先协调、按 hunk 暂存（[[WB-053]]）。

## 验证

门户建任务→本地 App pull 后项目计划 tab 可见；App 建/移动任务→Hub 端一致；Viewer 只读；离线本地照旧。
