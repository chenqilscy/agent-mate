---
id: WB-031
title: 计划 · agent 改计划项状态时实时回写看板（SSE 事件），而非仅返回时刷新
severity: P3
area: frontend
status: fixed
origin: 🆕 近期改动
files:
  - backend/agent/events.py
  - backend/agent/tools.py
  - backend/agent/runtime.py
  - src/lib/types.ts
  - src/stores/chatStore.ts
  - src/stores/workItemStore.ts
created: 2026-07-06
---

## 问题

WB-030 让 agent 能改计划项状态，但看板只在**返回「计划」页时重挂载重拉**才体现。
若看板与执行同时可见（未来分栏）、或后台自动化/并发运行改了状态，当前不会即时更新。
缺一条「状态变更」的实时 SSE 契约。

## 影响

P3：单栏流程下功能等价（返回即对）；主要是架构正确性与未来多栏/并发场景的实时性。

## 建议修法（遵铁律 #5：events.py 定义 ⇄ chatStore 消费）

- 后端 `events.py` 加 `work_item(item)` 事件（`event: work_item`）。
- `tools.ToolOutcome` 加 `live: list[dict]`（**瞬时**事件，不进持久化 trace，避免历史重放误更新）；
  `set_work_item_status` 回填 `live=[{id,status,project_id,title}]`；`runtime` 在跑完工具后
  `yield events.work_item(ev)`（不经 `record()`，不持久化）。step trace 仍保留（历史可见）。
- 前端 `types.ts` 增 `WorkItemEvent` 与 `work_item` 分支；`chatStore.onEvent` 加 `case 'work_item'`
  → `workItemStore.applyRemote(item)`（仅当 `project_id===当前 projectId` 时本地更新匹配项，无 API 调用）。

## 验证

- `py_compile` + `npx tsc --noEmit` 过。
- 真实 LLM：agent 改状态时前端收到 `work_item` 事件、`workItemStore` 即时更新；返回看板仍一致。
- 历史重放不因该事件误改状态（未持久化）。

## 处理记录（2026-07-06）
- 改动：
  - 后端 `events.py` 加 `work_item(item)` 事件；`tools.ToolOutcome` 加 `live` 字段（瞬时、不持久化），`set_work_item_status` 回填 `live=[{id,project_id,status,title}]`；`runtime` 跑完工具后 `yield events.work_item(ev)`（不经 `record()`，故不进 trace、历史重放不误触发）。
  - 前端 `types.ts` 加 `WorkItemEvent` 与 `work_item` 分支；`workItemStore.applyRemote(item)`（仅当 project_id===当前 projectId 本地改状态，无 API）；`chatStore.onEvent` 加 `case 'work_item'`。
- 验证：`py_compile` + `npx tsc --noEmit` 过；真实 LLM 跑通——用 fetch tee 抓到 SSE 帧 `event: work_item data: {"item":{...status:"done",title:"发布周报"...}}`，前端消费无报错，DB done，返回看板卡片落「完成」列（回归 WB-030 正常）。
- commit：（待提交）
