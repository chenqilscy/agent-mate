---
id: WB-065
title: 更深协作 —— 评论 / @提及 / 在线状态（分层：v1 REST+轮询，实时作增强）
severity: P2
area: backend
status: fixed
origin: 既有实现
files:
  - docs/agentmate-hub-架构设计.md
  - hub/routers/timeline.py
  - backend/stores/notificationStore.ts
created: 2026-07-07
---

## 问题

M7 协作做到 C4（成员/角色/只读可见/消息中心）+ Hub epic 的团队时间线（WB-062）。但**更深的协作**
——对项目/执行的**评论**、**@提及**、成员**在线状态**——还没有。架构设计 §2 把「实时通道」列为本轮非目标，
所以要分层：先用 REST + 轮询做出可用的 v1（与现有通知 30s 轮询一致，零新基建），真实时推送作后续增强。

## 触发场景

- 队友想在某个项目/某次执行下留言讨论，并 @某人让 TA 收到提醒。
- 想看谁当前在线 / 最近活跃。

## 影响

P2：协作深度增强，非阻断。**依赖 WB-061/062**（Hub + 团队时间线已就绪）。是「共享后端即 Hub」之后
自然的下一层协作。

## 建议修法（分层，避免过早上重型实时通道）

- **评论**：团队协作内容 → 落 **Hub**（权威、跨机可见），挂在项目（可选挂在某条 timeline 事件/执行上）。
  `hub` 加 `comments` 表 + `POST/GET /api/projects/{id}/comments`（access-gated，延续 timeline 的成员校验）。
- **@提及**：评论正文解析 `@用户名` → 给被提及成员建**通知**（复用 M7 C4 通知系统 / Hub 侧通知）。
- **在线状态**：Hub 记 `accounts.last_seen`（客户端心跳/任意 authed 请求刷新）；`GET /api/orgs|projects/{id}/presence`
  返回成员 last_seen。**v1 用轮询**（复用现有通知轮询节奏），实时推送后续。
- **传输决策（本 issue 的关键岔路）**：
  - **v1：REST + 轮询**——与现有 `notificationStore` 30s 轮询一致，Hub/本地/前端零新长连基建。**推荐先做这个。**
  - **实时：WebSocket / 长连 SSE**——Hub + 本地 backend + 前端都要加通道，架构更重；作为 v1 之后的增强。
- **本地回退**：未接 Hub / 离线 → 协作层降级隐藏，绝不阻断本机使用（铁律：Hub 是可选增强）。

## 验证

- 评论 CRUD + access-gate（非成员 404）；@提及生成通知给正确的人；presence 返回 last_seen。
- 两账号 E2E：A 评论 + @B → B 收到通知 → B 回复；非成员看不到/不能评论。
- 未接 Hub：本机全功能照常，协作入口隐藏、不报错。

## 处理记录（2026-07-07）—— Hub 协作机制 v1（REST + 轮询）完成

### 改动（Hub 侧；传输按决策取 v1 REST+轮询）
- `hub/db.py`：`comments` 表 + `hub_notifications` 表 + `accounts.last_seen`（幂等补列）+ DAO
  （add/list_comment、add/list/unread/mark_read notification、touch_last_seen、list_presence）。
- `hub/routers/comments.py`（新）：`POST/GET /api/projects/{id}/comments`（access-gated）；评论正文
  **解析 @提及** → 给被提及的**项目成员**建通知（去重、不通知自己、非成员名忽略）；`GET /api/projects/{id}/presence`
  （成员 + last_seen + online，窗口 120s）。
- `hub/routers/notifications.py`（新）：`GET /api/notifications`（列表 + unread）+ `POST /api/notifications/read`。
- `hub/auth.py`：`current_account` 每个 authed 请求 `touch_last_seen` —— 在线状态心跳（v1 轮询即刷新）。

### 验证
- py_compile；隔离 live hub 两账号 E2E **15 项全过**：A 评论 @B → B 收到 mention 通知（**只通知成员、忽略非成员名、作者不自通知**）→ B 读评论 + 回复 @A → A 收到；presence 列 owner+member、online、last_seen；mark-read → unread 0；**非成员 C 对评论/发评论/presence 一律 404**。

### 传输决策
按约定取 **v1：REST + 轮询**（与现有通知 30s 轮询一致，Hub/本地/前端零新长连基建）。真实时推送
（WebSocket / 长连 SSE）作后续增强。

### 未做（follow-up，同 WB-066 的前端二期）
- 本地 backend 代理这些 Hub 端点（`/api/projects/{id}/comments|presence`、`/api/notifications` 转发 Hub）供前端轮询。
- 前端评论/在线/通知 UI；未接 Hub 时隐藏协作入口（local guard，`GET /api/hub/status` 已可判断）。

commit：见下。
