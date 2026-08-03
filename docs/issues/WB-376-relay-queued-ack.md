---
id: WB-376
title: Relay 本地执行仅排队时被错误 ACK 为失败
severity: P1
area: backend
status: open
origin: 🆕 近期改动
files:
  - backend/agent/scheduler.py:338
  - backend/agent/scheduler.py:478
created: 2026-08-03
---

## 问题
run_webhook 忽略 _launch 因容量返回 None 的结果，Relay 处理器把 queued fire 当作非成功终态并 ACK failed。

## 触发场景
后台并发槽已满 → 拉取 Relay → fire 持久化为 queued 但未启动 → 立即向 Server ACK failed → 本地稍后仍可能执行成功。

## 影响
P1。Server 和本地形成互相矛盾的终态，破坏幂等重试与运营判断。

## 建议修法
返回 admission 状态；仅对 succeeded/failed/dead_letter 等真实终态 ACK；queued/running 时不 ACK并由租约重投或续租。

## 验证
全局与 per-owner 容量满的 Relay 均不 ACK；真实成功/失败仍精确 ACK；同 event_key 不重复产生副作用。
