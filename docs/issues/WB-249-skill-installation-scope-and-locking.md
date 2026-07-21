---
id: WB-249
title: Skill 安装启停为机器全局状态且并发安装卸载缺少事务锁与恢复能力
severity: P1
area: backend
status: fixed
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

## 处理记录

- 2026-07-21：新增 `skill_installations` 持久表，把 owner 的安装、启停、软删状态与机器级物理包分离；历史单用户目录首次扫描时仅迁移给 `LOCAL_USER`，共享 Backend 的其他账号不再自动继承。
- 2026-07-21：包引用记录固定 `package_key`、`release_id`、`content_hash`；相同 release 的多用户安装直接复用一份物理包，共享包升级时新 release 使用 hash 后缀目录，其他 owner 继续固定在旧 release。
- 2026-07-21：安装、导入、升级、启停、卸载、恢复统一使用按 slug 的进程内 `RLock` 与跨进程文件锁；安装仍通过 staging + `os.replace` 原子落盘，并发同包请求确定性复用完整结果。
- 2026-07-21：卸载先软删 owner 状态；最后一个活跃引用且无项目引用时才把包原子移动到 `.trash/`，提供 restore API，保留 7 天后按小时惰性清理；项目仍引用或其他 owner 仍使用时不做物理回收。
- 2026-07-21：验证通过：全部 Skill 回归 32 项、相关 Python `py_compile`、`npx tsc --noEmit`；覆盖双用户独立启停、共享单副本、v1/v2 release 并存、并发安装、项目引用门禁、trash 恢复。
