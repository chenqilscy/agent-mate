---
id: WB-159
title: 前端 store 健壮性 —— 看板乐观更新不回滚、answer 失败丢问题卡挂起 agent、send finally 无流守卫、connect 不 reload
severity: P2
area: frontend
status: fixed
origin: 既有实现
files:
  - src/stores/workItemStore.ts:88
  - src/stores/workItemStore.ts:121
  - src/stores/chatStore.ts:242
  - src/stores/chatStore.ts:249
  - src/stores/hubStore.ts:31
created: 2026-07-14
---

## 问题

1. **`workItemStore.move`（121-125）** 乐观改列后 `await updateWorkItem`，**无 try/catch、失败不回滚** → 卡片视觉换列但服务器没更新，直到 reload 才纠正；调用方 `void move(...)` 还产生 unhandled rejection。对比 `automationStore.toggle` 都做了回滚。
2. **`workItemStore.add/update`（88-112）** `await` 后直接 `set`，**无 `projectId` 守卫**（`load` 有）→ 切项目后迟到响应写错项目看板；且无 try/catch，`void update` 失败即 unhandled rejection。
3. **`chatStore.answer`（249-254）** 先 `set({pending:null})` 再 `api.answer(...).catch(()=>{})`，失败则问题卡消失且**永不恢复**，后端 agent 仍挂在 `asyncio.Event` 上。
4. **`chatStore.send` finally（242）** 无条件 `set({streaming:false,abort:null,pending:null})`，无 `onEvent` 那样的 `get().abort===controller` 守卫 → 被 stop 后旧 send 的 finally 可清掉新流的状态（竞态防御缺口）。
5. **`hubStore.connect`（31-36）** 换了 app token（切了后端识别身份）却不 `reload`，各 per-user store 残留旧身份数据（`authStore.login/logout` 都 reload）。

## 触发场景

拖卡遇后端抖动/只读项目 → 卡片跳回 + 控制台 unhandled rejection；答 ask_user 时后端瞬断 → 问题卡消失、agent 挂死；连接 Hub 后 projects/notifications 仍是旧身份数据。

## 影响

P2：看板/服务器失步、卡片错项目、agent 挂起、陈旧数据。均本地抖动/切换即触发。

## 建议修法

1. `move`：`const prev = 原 status; try { const wi = await update; set(替换) } catch { set(回滚 prev); toast }`。
2. `add`/`update`：落库前记 `pid = get().projectId`，`set` 前 `if (get().projectId===pid)`；`update`/`remove` 统一 try/catch + toast。
3. `answer`：`set({pending:null})` 移到成功后；`.catch` 里 `set({pending})` 还原 + 提示重试。
4. `send` finally 状态复位：`set(s => s.abort===controller ? {streaming:false,abort:null,pending:null} : {})`（loadSessions 仍照常）。
5. `connect` 成功后 `window.location.reload()`（对齐 authStore）。

## 验证

- `tsc`。
- 拖卡失败回滚 + 有 toast、无 unhandled rejection；answer 失败问题卡恢复；连接 Hub 后数据刷新为新身份。
- 回归：正常拖拽/答题/连接仍顺畅。

## 处理记录（2026-07-14）

- 改动：
  - `src/stores/workItemStore.ts`：`import { toast }`；`move` 记 prev + try/catch 回滚 + toast；`add`/`update`/`rename`/`remove` 加 `projectId` 守卫（落库前记 pid，`set` 前判仍在同项目）+ try/catch + toast；`remove` 失败恢复 prev 列表。
  - `src/stores/chatStore.ts`：`import { toast }`；`answer` 的 `.catch` 里 `set({ pending })` 还原问题卡 + toast；`send` 的 `finally` 状态复位改 `set(s => s.abort===controller ? {…} : {})`（迟到帧守卫同源）。
  - `src/stores/hubStore.ts`：`connect` 成功后 `window.location.reload()`（对齐 authStore，换身份后各 per-user store 重取）。
- 验证：`npx tsc --noEmit` 过。
- commit：未提交（待用户确认）。
