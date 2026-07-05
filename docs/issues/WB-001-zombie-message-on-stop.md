---
id: WB-001
title: 停止/连接失败后助手消息永久卡在「执行中…」
severity: P0
area: frontend
status: fixed
origin: 🆕 近期改动
files:
  - src/stores/chatStore.ts:224
  - src/lib/sse.ts:30
  - src/lib/sse.ts:75
  - src/components/chat/MessageList.tsx:24
created: 2026-07-06
---

## 问题
两条不同路径都会留下永久「执行中…」的僵尸助手气泡，根因相同：**没有 `done` 事件时消息不会被 finalize**。

1. `stop()`（`chatStore.ts:224`）只 `abort()` + 置 `streaming:false`，从不把当前 bot 消息的 `status` 从 `'running'` 改成 `'done'`。abort 让 `sse.ts` 读循环抛的 `AbortError` 被静默吞掉（`sse.ts:75-78`），不再派发 `done`。而 `MessageList` 的 `running = msg.status === 'running'`（`:24`）与 `streaming` 无关。
2. `await fetch()` 在 try 之外（`sse.ts:30`，try 从 `getReader()` 之后才开始）。后端未启动/网络失败时 `fetch` reject 直接穿出 `streamChat` → 穿出 `send`（`chatStore.ts` 的 `send` 只有 `try/finally`，无 `catch`）→ 调用点是 `void send()` / 不 await 的 `onSend`，形成**未处理的 Promise rejection**，且该 bot 消息从未收到 `error`/`done`。

## 触发场景
- 发一条较长任务 → 生成中点「停止」→ 气泡永久 spinner「执行中…」，无 BotActions，直到切走再切回（`openSession` 从后端拉取时 status 被写成 `done`）才恢复。
- 后端 down 时发送；或在响应头到达前点停止（abort 让 fetch reject `AbortError`，同样走未捕获路径）。

## 影响
高频、易复现，界面出现无法操作的卡死气泡 + 控制台未处理拒绝。

## 建议修法
- `stop()` 里对当前 botId `patchBot(status:'done')`（可加 `stopped` 标记）。
- `sse.ts` 把 `await fetch` 纳入 try，失败/abort 分支向上层 `onEvent({type:'error'})` + `onEvent({type:'done'})`（AbortError 至少发 `done`）。
- `send` 加 `catch` 兜底 finalize（与 WB-006 一并处理 refs 清空时机）。

## 验证
发长任务→点停止：气泡立即变「已完成」+ 出现操作按钮，无 spinner；关掉后端再发送：气泡显示错误、无卡死、控制台无未处理拒绝。

## 处理记录（2026-07-06）
- 改动：sse.ts 把 `fetch` 纳入 try（网络/HTTP 失败→error+done，AbortError 静默不发 done）；chatStore.stop() 把所有 status==='running' 气泡 finalize 成 done；send 增加 catch 兜底 finalize，streamChat 不再向上抛出。（src/lib/sse.ts, src/stores/chatStore.ts）
- 验证：verify_runtime.py 驱动真实 run_chat（stub LLM）：done 事件正常、stop 后气泡立即 finalize；`npx tsc --noEmit` 与 `vite build` 均通过。
