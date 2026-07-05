---
id: WB-033
title: 「立即运行」自动化后状态永久卡在「运行中」（前端只刷新一次、无轮询）
severity: P2
area: frontend
status: fixed
origin: 既有实现
files:
  - src/stores/automationStore.ts:60
  - src/views/AutomationView.tsx:35
created: 2026-07-06
---

## 问题

在「自动化」页对某条任务点「⋯ → 立即运行」后，卡片状态一直显示「运行中」，不会自动变成「上次成功 / 上次失败」。

根因是前端刷新时机与后端运行时序不匹配，与后端无关：

- 后端 `scheduler.run_now`（`backend/agent/scheduler.py:79`）**同步**建 session 并立刻把 `last_status` 置为 `"running"`，随后把真正的 `run_chat` 甩到 `asyncio.create_task` 后台，立即返回 `session_id`。运行结束才由 `_execute` 回写 `ok` / `error`。
- 前端 `automationStore.runNow`（`src/stores/automationStore.ts:60`）在 `api.runAutomation` 一返回就 `get().load()` **仅刷新一次**，此刻后台运行几乎必然还没结束，拉回来的状态就是 `running`。
- 此后 `AutomationView`（`src/views/AutomationView.tsx:35`）只在挂载时 `load()` 一次，**没有任何轮询**，于是「运行中」不再被更新。

到点自动触发（scheduler `_fire_guarded`）同样会经历 `running` 态，若用户正停留在该页，也存在同样「不刷新」的观感问题。

已用 SQLite 核实：两条被手动触发的自动化 `last_status` 最终都是 `ok`，说明**后端运行正常完成**，纯前端不刷新导致。

## 触发场景

1. 进入「自动化」页，对任一启用中的任务点「⋯ → 立即运行」。
2. 卡片出现「运行中」chip。
3. 等待任意时长后台运行早已完成（几秒级），UI 仍显示「运行中」。
4. 手动刷新浏览器（或切走再切回自动化页）→ 变为「上次成功 · 刚刚」。说明是前端刷新问题。

## 影响

P2：功能实际是好的（后端真跑完、session 真产出、可从「打开上次运行」查看），但状态指示长期失真，用户会误以为任务卡死或反复重复触发。不涉及数据丢失或安全。

## 建议修法

在 `automationStore.runNow` 里把「单次 `load()`」换成**有界轮询**：触发后每隔约 2s `load()` 一次，直到该任务 `last_status !== 'running'` 或达到兜底次数上限后停止（后端单次运行上限 `RUN_TIMEOUT=300s`，轮询窗口可取 ~60–90s，够覆盖绝大多数任务；极端超时会由后端翻成 `error`，下次进页面时纠正）。

可选增强（本 issue 不强制）：在 `AutomationView` 里当列表存在 `last_status === 'running'` 的项时做轻量定时刷新，顺带覆盖「到点自动触发」时停留在页面的场景。

注意：轮询用的 `setTimeout` 循环要能安全存活于组件卸载之后（store 层的循环不依赖组件生命周期即可），且不要与 `load()` 的 `loading` 抖动叠加造成闪烁。

## 验证

- `npx tsc --noEmit` 通过。
- 浏览器实测：点「立即运行」→ 卡片先显示「运行中」，数秒后**无需手动刷新**自动变为「上次成功 · 刚刚」。
- 明暗双主题下 chip 颜色正常（复用既有 `.auto-chip.run/ok/err`，不新增样式）。
- 回归：轮询期间切走再切回、或删除该任务，不报错、无悬挂请求异常。

## 处理记录（2026-07-06）

- 改动：`src/stores/automationStore.ts` 的 `runNow` —— 触发运行后由「单次 `load()`」改为**有界轮询**：先 `load()` 一次给出即时「运行中」反馈，随后每 2s `load()` 一次，直到该任务 `last_status !== 'running'` 或达 45 次上限（~90s 窗口，覆盖绝大多数运行；后端 `RUN_TIMEOUT=300s` 会把极端超时翻成 `error`，下次进页面纠正）。轮询逻辑在 store 层，不依赖组件生命周期，切走再切回不受影响。未改后端、未加 CSS。
- 验证：`npx tsc --noEmit` 通过。Playwright 明色主题实测：对「每日一个为什么」点「⋯ → 立即运行」→ chip 先显示「运行中」→ **未做任何手动刷新**，数秒后自动变为「上次成功 · 刚刚」。SQLite 侧此前已核实后端运行本就正常完成（`last_status=ok`），确认问题纯在前端刷新。console 无新增错误（仅既有 favicon 404）。
- commit：（尚未提交）
