---
id: WB-015
title: 同一 session 并发 run 串道（_stop_events/_answers 按 session 共享）
severity: P2
area: backend
status: open
origin: 🏚 既有实现
files:
  - backend/agent/runtime.py:217
  - backend/agent/runtime.py:333
  - backend/agent/runtime.py:392
created: 2026-07-06
---

## 问题
`_stop_events` / `_answers` 两个字典均以 `session_id` 为键，隐含「每 session 只有一个活跃 run」，但无处强制。第二个 run 覆盖第一个的 stop/answer 通道；先结束的 run 在 `finally` 里 `pop` 掉的是对方的条目。

## 触发场景
会话处于 `waiting`（ask_user 挂起）时用户对同一 session 再发一条消息；或断线重连并发。结果：run1 的 `await ev.wait()`（`:336`）永远等不到（其 `_answers` 条目被 run2 覆盖，`/answer`、`/stop` 都只命中 run2），run1 永久挂起直至客户端断开；stop 也会作用到错误的 run。

## 影响
边角并发 bug；ask_user 挂起 + 再发消息时可复现挂死。

## 建议修法
为每次 run 生成唯一 `run_id`，字典按 run_id 存；或在启动新 run 前拒绝/取消同 session 的在跑 run。

## 验证
ask_user 挂起时对同一 session 再发消息 → 不出现永久挂起；stop/answer 命中正确的 run。
