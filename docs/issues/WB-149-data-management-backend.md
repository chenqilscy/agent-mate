---
id: WB-149
title: 数据管理真后端 —— 数据导出（真 dump 用户数据）+ 清空个人对话记录（真删除·二次确认）
severity: P2
area: fullstack
status: fixed
origin: 🆕 近期改动
files:
  - backend/routers/data.py
  - backend/storage/db.py
  - src/components/settings/SettingsModal.tsx
created: 2026-07-14
---

## 问题

设置中心「数据管理」tab 还是「即将上线」占位。做成**完全真实**的一刀切：真导出用户自己的数据、
真清空对话记录——不做那些需要执行层改造才生效的策略开关（删除保护/批量审批），以免假开关（铁律#1）。

## 触发场景

设置 → 数据管理 → 看到会话/消息/记忆的真实条数 → 点「导出」下载一份含自己会话+设置+记忆的 JSON →
点「清空个人对话记录」二次确认后，个人对话（kind=chat）真被删、条数归零。

## 影响

P2：数据可携（导出）与清理是设置中心的常见诉求；纯读/删自己的数据，不碰安全执行层，风险可控。

## 建议修法

1. **DB**（`storage/db.py`）：`clear_conversations(owner)` —— 删 owner 的 `kind='chat'` 会话 + 其 messages，
   返回删除数（只删个人对话，不误伤项目执行/助理/自动化会话）。
2. **路由 `routers/data.py`**：
   - `GET /api/data/summary` —— 会话/消息/记忆条数（面板展示）。
   - `GET /api/data/export` —— dump {user, settings, memories, sessions[含 messages]}（前端下载为 JSON）。
   - `POST /api/data/clear-conversations` —— 真删个人对话，返回删除数。
   `main.py` 注册。
3. **前端**：`api.dataSummary/dataExport/clearConversations`；`SettingsModal` 数据管理 panel——
   条数卡 + 导出按钮（Blob 下载 JSON）+ 清空按钮（二次确认）。删除保护等策略项诚实占位。

## 验证

- `py_compile` 后端；`tsc --noEmit`。
- 建一条对话 → summary 条数对；export 拿到含该会话的 JSON；clear 后 summary 归零、export 不再含它。
- 明暗双主题看数据管理 panel。

## 处理记录（2026-07-14）

- 改动：
  - `backend/storage/db.py`：`clear_conversations(owner)` —— 删 owner 的 `kind='chat'` 会话 + 其 messages（IN 子查询），返回删除数；只删个人对话，不误伤项目执行/助理/自动化会话。
  - 新增 `backend/routers/data.py`：`GET /api/data/summary`（会话/消息/记忆条数）、`GET /api/data/export`（dump user+settings+memories+sessions[含 messages]，用 Session/Message.to_dict()）、`POST /api/data/clear-conversations`。`main.py` 注册。
  - 前端 `src/lib/{types,api}.ts`：`DataSummary` + `dataSummary/dataExport/clearConversations`。
  - `src/components/settings/SettingsModal.tsx`：`DataPanel`——概览统计卡 + 导出（Blob 下载 JSON）+ 清空个人对话（二次确认 danger）+ 删除保护/批量审批诚实占位（`Soon`）；替掉占位。
  - `src/styles/app.css`：`set-stats/set-stat*/set-confirm` 样式（token 化，暗色安全）。
- 验证：
  - `py_compile` 三个后端文件过；`tsc --noEmit` 过。
  - 后端重启后 `GET /api/data/summary` 返回真实条数（342 会话/698 消息/0 记忆）；`GET /api/data/export` 真 dump（顶层 user/settings/memories/sessions，首会话含 title/kind/messages）。
  - **clear 未在真库跑**（会删用户 342 条真会话）——改对**临时库**跑真 `db.clear_conversations`：removed=2、owner 的非 chat 会话保留(2)、他人 chat 保留(1)、被删会话消息级联清除，作用域与级联正确。
  - CDP 截图**明暗双主题**数据管理 panel 渲染无坑（统计卡/导出/清空/占位）。
- commit：feat(WB-149) e1486e0。

## 审查修复（2026-07-14 复盘）

- **摘要 N+1**（P2）：`summary` 原对每个会话 `list_messages`（`SELECT *` + 反序列化 trace/usage）只为计数，
  重度用户几十会话数千消息全构造一遍。修：新增 `db.owner_data_counts(owner)`（会话 + 消息各一条 COUNT），
  `summary` 改用它。实测仍返回 347/706。
- **clear_conversations 变量上限 + 冗余**（P2）：原 `DELETE FROM messages WHERE session_id IN (?,?,…)` 展开全部会话 id，
  超 SQLite 变量上限（老版 999）会失败；而 messages 已 `ON DELETE CASCADE`（+ `PRAGMA foreign_keys=ON`），
  手删消息本就多余。修：只 `DELETE FROM sessions ... kind='chat'`，消息靠级联删，`cur.rowcount` 计数。
  临时库测：removed=2、非 chat 保留、消息级联清零。
