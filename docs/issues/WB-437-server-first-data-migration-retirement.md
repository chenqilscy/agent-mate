---
id: WB-437
title: 存量业务数据迁移与旧同步机制退役
severity: P1
area: misc
status: open
origin: 🏚 迁移遗留
files:
  - backend/storage/db.py:1
  - backend/server_sync.py:1
  - backend/server_client.py:1
  - backend/routers/server.py:1
  - scripts:1
created: 2026-08-08
---

## 问题

父项：[WB-431](archive/2026/WB-400-499.md#wb-431)，依赖 WB-432～WB-436。现有用户数据仍分布在本地业务表和 Server 镜像表；直接删除旧路径会丢数据，长期双写又会保留双权威复杂度。

## 触发场景

Server-first 客户端启用后，旧客户端或旧本地数据库仍可能创建 sessions、projects、automations 等记录；若没有幂等导入和版本门禁，会重新产生分叉。

## 影响

P1：这是迁移收口与删除旧同步代码的最终门槛。

## 建议修法

- 建立本地只读预检、迁移 manifest、源/目标 ID 映射、内容 hash、失败清单与幂等重试。
- 按实体/账户/设备分批切换写权威，切换后通过最低协议版本阻止旧客户端继续本地写。
- 保留加密只读备份和观察期，不做长期双写；回滚只能暂停写或使用兼容 adapter。
- 验收后删除 `origin/server_dirty/server_updated_at/server_sync_conflicts`、通用 `/server/pull`、业务镜像/outbox 和本地业务表。

## 验证

- 对项目、会话、消息、Run、自动化、助理、频道、任务和资产完成数量/hash/关系对账。
- 重复导入无重复；中断恢复可续跑；失败批次不影响已提交批次审计。
- 备份恢复、跨设备读取、旧客户端拒绝、回滚演练和全量回归通过后才能执行删除。
