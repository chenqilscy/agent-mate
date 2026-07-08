---
id: WB-091
title: 本地 App ⇄ Hub work_items 双向同步（WB-081 的二期）
severity: P3
area: backend
status: fixed
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

## 处理记录（2026-07-08）

采用**「读代理+镜像 / 写代理」**（比原计划的 outbox 更实时、无漂移），且**前端零改动**（App 已带 token，代理透明）：
- `backend/hub_client.py`：加 `_patch`/`_delete` + `list/create/update/delete_work_items`（guarded，不可达→None/False）。
- `backend/storage/db.py`：`mirror_hub_work_items(pid, items)`——用 Hub 的 work_items 覆盖本地某 hub-origin 项目（Hub id 作本地 id，供 update/delete 定位 + 离线读兜底）。
- `backend/routers/work_items.py`：`_hub_token(pid, auth)` 判 hub-origin+已接+带 token → 走 Hub 权威；
  **list** 代理读 Hub + 镜像本地；**create/update/delete** 代理到 Hub 再刷新镜像；Hub 不可达一律回退纯本地（离线优先）。
- 本地专有字段（owner_id/due_date/attachments）Hub work_items 不带，代理视图补默认。
- **验证**：隔离本地 backend :8001（HUB_URL→我的 Hub :8100）E2E：pull 镜像项目 P →
  本地 `GET /work-items` 代理回 Hub 的「API 测试任务/门户 UI 建的任务」（门户建的，App 侧现可见）→
  本地 POST「从本地 App 建的任务」→ Hub 端出现 → PATCH→done→ Hub 一致 → DELETE→ Hub 移除。双向打通。
