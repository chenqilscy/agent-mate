---
id: WB-019
title: 迟到 SSE 事件污染新会话（onEvent 不校验当前流）
severity: P2
area: frontend
status: open
origin: 🏚 既有实现
files:
  - src/stores/chatStore.ts:128
  - src/stores/chatStore.ts:59
created: 2026-07-06
---

## 问题
`onEvent`（`chatStore.ts:128`）只靠 `botId` 匹配保护 `patchBot`；但 `session`/`usage`/`ask_user` 用裸 `set()`。切会话时 `openSession` 先 `stop()`（abort 异步生效），已 resolve 但尚未派发的最后一个 chunk 里的帧仍会同步派发。

## 触发场景（时序窄）
会话 A 流式中切到 B，A 的迟到 `session` 事件把 `activeId/title` 覆盖回 A（而 messages 已是 B），或迟到 `ask_user` 在 B 里弹出无关提问卡。

## 影响
低概率错乱，难复现但真实存在。

## 建议修法
`send` 里捕获 `controller`，`onEvent` 每次比对 `get().abort === controller`（或用 run 序号）再落库；非当前流的事件丢弃。

## 验证
A 流式中快速切 B → B 不出现 A 的标题/提问卡。
