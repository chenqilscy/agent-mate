---
id: WB-365
title: 项目治理活动流在同时间戳下排序不稳定
severity: P2
area: backend
status: open
origin: 既有实现
files:
  - server/db.py:2182
  - server/tests/test_wb350_project_governance.py:61
created: 2026-08-03
---

## 问题

`list_project_governance_activity` 仅按浮点 `created_at DESC` 排序，没有稳定的次级顺序。同一测试进程中快速连续写入时，`updated` 与随后 `deleted` 可能取得相同时间戳，SQLite 可先返回 `updated`。

## 触发场景

完整 Server 测试套件快速连续创建、更新、删除治理记录后，断言最新活动为 `deleted`；本次统一门禁曾一次读到 `updated`，随后单例与全套重跑通过。

## 影响

P2。活动流偶发次序错误并造成质量门禁不稳定；不影响记录持久性，但会误导最新操作展示。

## 建议修法

为活动记录引入可单调排序的序列，或至少在时间戳相同时使用明确且符合写入顺序的稳定次级键；补充固定相同时间戳的回归测试。

## 验证

- 强制多条活动使用同一 `created_at` 时仍严格按写入顺序倒序返回；
- Server 全套测试重复运行稳定通过。
