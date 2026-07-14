---
id: WB-155
title: 助理多渠道共享 session —— 并发 run 交错 + before 快照把他人回复当自己的返回（跨用户串信）
severity: P1
area: backend
status: fixed
origin: 既有实现
files:
  - backend/channels/manager.py:63
  - backend/channels/manager.py:150
  - backend/channels/manager.py:389
created: 2026-07-14
---

## 问题

`ensure_assistant_session` 让一个助理的 App + 所有渠道**共写一份 transcript / 一个 session**。但并发去重 `_busy` 只按 `channel_id:chat_id`（`manager.py:150/237`），`say()`（389）**无任何守卫**。`_run_agent`（63-92）先 `before = {msg ids}` 快照，跑完后返回「最新一条 id∉before 的 assistant 消息」。

## 触发场景

同一助理绑两个渠道（Telegram + 邮件），或 App `say` 与入站消息并发，在**同一 session** 上并发跑 `run_chat`：Run A 的 `_run_agent` 扫到的「最新 assistant 消息」可能是 Run B 刚插入的回复 → 把**用户 B 的答复发给用户 A**（机密串信），且两个 run 的 LLM 历史相互交错污染。

## 影响

P1：跨用户/跨渠道机密泄漏 + transcript 交错。多助理·多渠道（WB-086~089）正是为并发渠道设计，触发面真实。

## 建议修法

按 `session_id` 串行化 `_run_agent`：模块级 `_session_locks: dict[str, asyncio.Lock]`，`_run_agent` 全程（含 before 快照→drive→扫回复）`async with _session_lock(session_id)`。三个入口（`_handle_tg_update`/`_handle_email`/`say`）都经 `_run_agent`，锁放里面即全覆盖。串行后 before/after diff 能正确归属本 run 的回复。单进程单事件循环，`asyncio.Lock` 足矣。

## 验证

- `py_compile`。
- 同 session 并发发两条不同消息 → 两条回复各自对应各自输入、不串；transcript 顺序正确（user A→assistant A→user B→assistant B，而非交错）。
- 回归：单渠道单聊、App say 单发仍正常。

## 处理记录（2026-07-14）

- 改动：`backend/channels/manager.py` 加 `_session_locks: dict[str, asyncio.Lock]` + `_session_lock(session_id)`；`_run_agent` 全程（before 快照 → `_drive` → 扫回复）`async with _session_lock(session_id)`。三个入口（Telegram/邮件/`say`）都经 `_run_agent`，锁在里面即全覆盖。
- 验证：py_compile 过。串行化后同 session 的并发运行不再交错，before/after diff 正确归属本 run 的回复。（真实双渠道并发需 live bot，未 E2E；逻辑与 asyncio.Lock 语义明确。）
- commit：未提交（待用户确认）。
