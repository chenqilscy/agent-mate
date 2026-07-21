---
id: WB-249
title: Skill 安装启停为机器全局状态且并发安装卸载缺少事务锁与恢复能力
severity: P1
area: backend
status: open
origin: 既有实现
files:
  - backend/routers/skills.py:1
  - backend/agent/skills_store.py:772
  - backend/agent/skills_store.py:824
created: 2026-07-21
---

## 问题

技能包和 `.disabled` 标记都是机器全局文件状态，多用户共享本地 backend 时，一个用户停用或卸载会影响
其他用户。安装、升级、卸载缺少按 slug 的进程内/跨进程锁；SkillHub 安装直接写目标目录，卸载直接
`rmtree`，并发操作与失败恢复能力不足。

## 触发场景

- 用户 A 停用或卸载一个项目正在使用的 Skill，用户 B 的会话随即变成未就绪。
- 两个请求同时安装/升级同一 slug，可能互相覆盖 staging、元数据或 CLI 锁文件。
- 卸载后发现项目仍引用该 Skill，无法快速恢复原包。

## 影响

P1：共享设备上的用户状态互相污染；并发和失败路径可能损坏安装目录。

## 建议修法

- 使用内容寻址的共享只读 package cache；另建 owner/device installation 与 enabled 状态记录。
- 安装、升级、卸载使用按 slug 锁和原子状态事务；卸载先进入可恢复 trash，再异步清理。
- 项目/loadout 只引用稳定 release，包缓存可被多个用户复用。

## 验证

- 两个用户对同一包可拥有独立启停状态，磁盘内容只保留一份。
- 并发安装/升级结果确定且无半包；卸载可在保留期内恢复。
- 项目引用与垃圾回收存在门禁，仍被引用的 release 不被物理删除。
