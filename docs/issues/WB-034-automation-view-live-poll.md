---
id: WB-034
title: 自动化看板不反映「到点自动触发」的运行 —— 视图级自适应轮询
severity: P3
area: frontend
status: fixed
origin: 既有实现
files:
  - src/views/AutomationView.tsx:35
  - src/stores/automationStore.ts:60
created: 2026-07-06
---

## 问题

WB-033 修好了「手动立即运行」后卡片不刷新的问题，但只覆盖手动路径。若用户**停留在自动化页**时某条任务**到点被 scheduler 自动触发**（`backend/agent/scheduler.py` 每 `SCAN_SECONDS=20` 扫一次），后端会把该任务置为 `running` 再到 `ok/error`，而前端 `AutomationView` 只在挂载时 `load()` 一次、无常驻刷新（`src/views/AutomationView.tsx:35`），于是这次自动运行的「运行中 → 上次成功」全过程用户看不到，卡片一直是旧态，直到手动刷新或切页重进。

同时，WB-033 在 store 层 `runNow` 里加的定向轮询（`src/stores/automationStore.ts:60`）与本增强要加的视图级轮询会重叠（两套循环都调 `load()`），宜合并成一套。

## 触发场景

1. 打开「自动化」页并停留。
2. 某条启用中的间隔任务到点被 scheduler 自动触发。
3. 卡片不出现「运行中」、也不更新「上次成功 · 刚刚」/「下次 …」，需手动刷新才更新。

## 影响

P3：纯观感/实时性，功能与数据均正确（后端照常执行、状态照常持久化）。相对时间标签（「下次 X 分钟后」「上次成功 Y 分钟前」）也会随之保持新鲜。

## 建议修法

在 `AutomationView` 加一个视图级**自适应轮询** effect：视图挂载期间定时 `load()`，有任务处于 `running` 时用较快节奏（~3s）以尽快反映完成，空闲时用较慢节奏（~15s）以捕捉到点触发与刷新相对时间标签；卸载时清掉定时器。

顺带将 WB-033 在 `runNow` 里的定向轮询**收敛掉**：`runNow` 只保留一次即时 `load()`（给出即时「运行中」反馈），后续刷新交给视图级轮询统一处理——避免两套重叠循环。`runNow` 仅从该视图触发，视图必然在场，故行为不回退。

## 验证

- `npx tsc --noEmit` 通过。
- 浏览器实测（手动路径回归）：点「立即运行」→ 卡片「运行中」→ 无需手动刷新自动变「上次成功 · 刚刚」，与 WB-033 效果一致。
- 到点触发路径：可将某任务间隔设为 1 分钟并停留在页面，观察其自动进入「运行中」再转「上次成功」而无需手动刷新（或以 SQLite 侧 `last_run_at` 变化佐证前端确有刷新）。
- 明暗双主题 chip 正常；切走再切回、删除任务无报错、定时器随卸载清理无泄漏。

## 处理记录（2026-07-06）

- 改动：
  - `src/views/AutomationView.tsx` —— 新增视图级自适应轮询 effect：`anyRunning = items.some(last_status==='running')`，`setInterval(load, anyRunning ? 3000 : 15000)`，依赖 `[anyRunning, load]`，卸载 `clearInterval`。挂载期间常驻刷新，有任务运行时提速到 3s。
  - `src/stores/automationStore.ts` —— 将 WB-033 在 `runNow` 里的定向轮询收敛为单次 `load()`（即时「运行中」反馈），后续刷新统一交给视图轮询，消除两套重叠循环。
- 验证：`npx tsc --noEmit` 通过。Playwright 明色主题实测两条路径：
  - 到点触发路径（关键）：**不经前端**，直接 `POST /api/automations/{id}/run` 外部触发「每日 5 个英语单词」（等价于 scheduler 自动触发），页面**未做任何操作**，卡片在一次轮询后由「上次成功 · 23分钟前」自动刷新为「上次成功 · 刚刚」。
  - 手动路径回归：与 WB-033 一致，点「立即运行」→「运行中」→ 自动转「上次成功」。
  - 无新增 console 错误（仅既有 favicon 404）。
- commit：（尚未提交）
