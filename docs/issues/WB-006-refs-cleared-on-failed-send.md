---
id: WB-006
title: 发送失败/被停止时，一次性 refs 仍被清空
severity: P1
area: frontend
status: open
origin: 🆕 近期改动
files:
  - src/stores/chatStore.ts:209
created: 2026-07-06
---

## 问题
`send` 的 `finally` 无条件 `useLoadoutStore.getState().clearRefs()`（`chatStore.ts:209`）。HTTP 失败（走 error+done）、网络失败、或用户点停止后，`finally` 都会清空 refs。

## 触发场景
用户从 ＋ 菜单引用/添加了文件 → 发送因后端错误失败（或被停止）→ 引用的文件被吃掉，重试需重新引用。

## 影响
体验损耗，与 WB-001 同源（都因缺乏「是否真正成功」的判定）。

## 建议修法
仅在确实成功（收到 `done` 且无 `error`）后 `clearRefs()`。可在 `onEvent` 里记录 `ok` 标志，`finally` 中 `if (ok) clearRefs()`。与 WB-001 一并修。

## 验证
引用文件 → 断开后端发送失败 → chip 仍在，可直接重试；成功发送 → chip 清空。
