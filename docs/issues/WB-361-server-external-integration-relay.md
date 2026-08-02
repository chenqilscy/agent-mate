---
id: WB-361
title: Server 缺少面向外部系统的服务身份与设备投递中继
severity: P1
area: backend
status: open
origin: 既有实现
files:
  - docs/external-system-integration.md:1
  - server/main.py:32
created: 2026-08-03
---

## 问题

当前 Automation Webhook 仅位于 localhost App；Server 没有 scoped service account、外部事件持久队列、设备拉取/确认和状态查询。

## 触发场景

互联网 CI、监控或 CRM 需要触发离线设备上的本地执行时，只能自行部署隧道，或错误地直接暴露 App backend。

## 影响

P1。外部集成缺少安全、可运维的生产拓扑。

## 建议修法

在 Server 增加哈希存储的 scoped service token、HMAC/幂等事件入站、owner/device 定向的持久 relay、租约拉取和 ack；不得上传会话正文或本机凭据。

## 验证

- service token 权限、轮换、撤销和限速回归通过；
- 重复事件不重复执行，离线后可重投，错误设备不能领取；
- 文档明确本地 poller 与 Server relay 两种模式。
