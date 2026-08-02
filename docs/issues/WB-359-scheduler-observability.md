---
id: WB-359
title: Scheduler 扫描与 Server outbox 异常被静默吞掉
severity: P1
area: backend
status: open
origin: 既有实现
files:
  - backend/agent/scheduler.py:287
created: 2026-08-03
---

## 问题

常驻 scheduler 的扫描和 outbox 刷新异常直接 `pass`，没有日志、连续失败状态或健康读数。

## 触发场景

数据库、健康扫描或 Server 同步失败时，循环继续运行但运维侧无法区分正常空闲和持续故障。

## 影响

P1。自动化与协作同步可静默失效。

## 建议修法

记录结构化异常和每类循环的成功/失败时间、连续失败次数，通过只读状态端点暴露，成功后自动恢复。

## 验证

- 注入失败后有日志和持久/内存健康状态；
- 下一轮成功会清零连续失败；
- scheduler、自动化和 Server fallback 回归通过。
