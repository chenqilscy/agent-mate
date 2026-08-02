---
id: WB-363
title: 数据库升级缺少版本化迁移且架构文档已漂移
severity: P2
area: backend
status: open
origin: 既有实现
files:
  - backend/storage/db.py:121
  - server/db.py:73
  - README.md:22
created: 2026-08-03
---

## 问题

App/Server 数据库由巨型 `db.py` 内联建表和兼容 DDL 驱动，没有明确 schema version/迁移记录；README 与活动 issue 数量不一致，架构文档没有覆盖最近的健康治理和外部接入演进。

## 触发场景

升级旧数据库或多人并行修改 schema 时，无法清楚回答已执行哪些迁移、失败能否重试和当前架构基线。

## 影响

P2。维护冲突、升级回归和审计成本持续上升。

## 建议修法

引入幂等的 `schema_migrations` 记录和顺序迁移 runner，先迁移新增能力并保持旧库兼容；抽出迁移职责，更新架构、外部接入、测试和剩余事项文档。

## 验证

- 空库、当前库和旧 fixture 升级幂等；
- 迁移失败不写成功记录；
- 文档与活动台账、真实启动机制一致。
