---
id: WB-225
title: 技能稳定 slug 可改删导致本地引用和安装快照失联
severity: P1
area: fullstack
status: fixed
origin: 技能功能复查
files:
  - server/web/console.html:2007
  - server/routers/catalog.py:336
  - backend/storage/db.py:1702
  - backend/agent/skills.py:376
created: 2026-07-21
---

## 问题

编辑弹窗把 slug 标为“稳定身份”，但输入框仍可直接修改。Server 只在该 slug 被推荐位引用时禁止改名/删除，
无法迁移分布在各 App 本机的项目、助理、会话 loadout 和已安装目录快照。下次全量下行会删除旧目录定义并插入新 slug，
旧引用最多退化为只读本地 SKILL.md，失去 Server 管理定义及工具绑定，或直接被运行时报告为未就绪。

## 触发场景

对一个未进入推荐位的技能执行编辑，将 slug 从 A 改为 B 可以保存成功；2026-07-21 使用临时技能浏览器实测复现。
此前已经安装或持久化 A 的 App 不会收到 A→B 的迁移关系。整项删除同样只检查推荐位，不检查客户端引用。

## 影响

P1：slug 是技能三层身份主键，任意改写会破坏目录、loadout 与磁盘快照的一致性，且 Server 无法在分布式 local-first 客户端上原子修复。

## 建议修法

- 创建后将 slug 设为不可编辑；改名只允许修改展示名称。
- 若业务确需迁移，设计显式 alias/tombstone 与客户端幂等迁移协议，而不是普通 PATCH。
- 已被发布或安装的技能优先“停用/归档”，删除前展示影响说明并保留可解析的身份记录。

## 验证

- 编辑已有技能时 slug 只读，直接 PATCH 改 slug 也被 Server 拒绝。
- 展示名、描述、指令与文件仍可正常编辑；停用技能不会破坏既有项目引用。
- 如实现 alias 迁移，旧 slug 在多次 pull 后稳定归一到新 slug，工具绑定和安装快照不丢失。

## 处理记录（2026-07-21）

- 改动：已有技能 slug 在 Console 只读，Server PATCH 无条件拒绝改写；技能 DELETE 改为保留条目的安全归档，slug 身份可重新启用，不再物理删除。
- 验证：浏览器确认编辑态 slug 只读；Server 回归确认直接 PATCH 改 slug 返回冲突、归档后记录仍在且 disabled、排序/启停不改变技能包版本。
- commit：本次 WB-207/WB-224～229 合并提交。
