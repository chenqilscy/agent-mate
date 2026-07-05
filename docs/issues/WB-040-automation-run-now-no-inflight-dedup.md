---
id: WB-040
title: 「立即运行」不与在飞的运行去重，连点/与到点触发并发会重复跑同一自动化
severity: P3
area: backend
status: fixed
origin: 既有实现
files:
  - backend/agent/scheduler.py:79
created: 2026-07-06
---

## 问题

`scheduler.run_now`（[`scheduler.py:79`](../../backend/agent/scheduler.py#L79)）不检查该自动化是否已有
在飞的运行：每次调用都新建会话、`_running.add`、后台 `_execute`。于是——

- 连点两次「立即运行」→ 两次并发运行（两条会话、两次 LLM 调用）。
- 用户在某条**到点自动触发**正跑时点「立即运行」→ 再并发一次。

不会引发扫描循环的**重复到点触发**（`_loop` 触发前已把 `next_run_at` 预留到未来，且 `_running` 判重），
故属良性双花，但连点/手动叠到点会白跑一次、`last_session_id` 也可能互相覆盖。

## 触发场景

1. 对一条自动化快速连点两次「立即运行」（或在它自动触发时点）。
2. 后端起两条并发 `_execute`，各产一条会话、各花一次 LLM。

## 影响

P3：无数据损坏/安全问题（各自独立会话），但重复消耗 + 状态指示可能短暂错乱。

## 建议修法

- `run_now` 开头判重：若 `auto_id in _running`，说明已有在飞运行，直接返回其当前会话
  （`auto.last_session_id`）而**不新起**一次，避免连点/叠到点的双花；前端拿到同一 session 照常显示。
- 保持到点触发路径不变。

## 验证

- 连点两次「立即运行」→ 只起一条会话（第二次返回同一 session_id）；SQLite 侧 `sessions` 只增 1。
- 单点仍正常起一条；运行完成后再点又能起新的一条。

## 处理记录（2026-07-06）

- 后端：`scheduler.run_now` 开头判重——`if auto_id in _running: return auto.last_session_id`，已有在飞运行时
  返回其会话而不新起，避免连点/叠到点双花；到点触发路径不变。
- 验证：后端 curl——对一条自动化快速连发两次 `/run`，两次返回**同一** session_id，`/runs` 只 +1（非 +2）。
- commit：（尚未提交）
