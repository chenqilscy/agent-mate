---
id: WB-378
title: 进程崩溃后普通会话 Run 永久停留在活动状态
severity: P1
area: backend
status: in-progress
origin: 既有实现
files:
  - backend/main.py:106
  - backend/agent/runtime.py:1380
created: 2026-08-03
---

## 问题
普通对话 Run 没有进程实例/租约；硬崩溃绕过 runtime finally，启动时又不对账 planning/running/waiting_approval。

## 触发场景
执行中 kill 后端 → 重启 → 历史 Run 仍显示运行/等待，且 retry 只接受终态或 paused。

## 影响
P1。对话无法恢复，活动统计错误，用户只能新建会话绕过。

## 建议修法
启动时原子把旧活动 Run 迁移为 paused 并写 process_restarted checkpoint；会话置 idle；允许基于已持久消息重试。

## 验证
构造三种活动状态后启动恢复均为 paused、session idle、可 retry；当前进程的正常运行不被误暂停。
