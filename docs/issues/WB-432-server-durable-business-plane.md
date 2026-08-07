---
id: WB-432
title: Server 补齐持久业务模型与统一 API
severity: P1
area: backend
status: open
origin: 🏚 迁移遗留
files:
  - server/db.py:1
  - server/main.py:1
  - server/routers:1
  - backend/storage/db.py:142
created: 2026-08-08
---

## 问题

父项：[WB-431](archive/2026/WB-400-499.md#wb-431)。Server 已管理账号、组织、项目和主要协作实体，但 sessions/messages/runs/assistants/channels/automations/assets 等持久业务数据仍以本地 backend SQLite 为权威，Desktop UI 无法把 Server 作为完整业务入口。

## 触发场景

用户换设备、通过 Console 查看执行历史，或本地数据库丢失时，会话、Run、自动化和助理等状态不能从 Server 完整恢复。

## 影响

P1：这是 Server-first 迁移的基础依赖；未完成前，Local Agent 无法收缩为纯执行节点。

## 建议修法

- 在 Server 建立 sessions/messages/runs/run_steps/assistants/channels/automations/assets 等版本化 schema、权限和审计。
- API 覆盖现有桌面核心流程，写入支持 idempotency key，分页/实时读取有稳定游标。
- 明确 account/org/project 权限、数据保留、删除和导出契约。
- 兼容迁移期只允许 Server 写权威，不做长期双写。

## 验证

- 两台客户端使用同一账号可读取一致的项目、会话、消息、Run、自动化和助理状态。
- 非成员、Viewer、跨组织和已撤权账号的读写门禁通过。
- 重复写请求不生成重复记录；备份恢复后业务关系、审计和对象引用完整。
