---
id: WB-245
title: Skill 已安装指令与实时工具绑定可形成混合版本且 Run 缺少不可变快照
severity: P0
area: fullstack
status: fixed
origin: 既有实现
files:
  - server/db.py:925
  - backend/agent/skills_store.py:314
  - backend/agent/skills.py:426
  - backend/agent/runtime.py:453
created: 2026-07-21
---

## 问题

Server 目前用可变 `catalog_items` 行同时保存 Skill 展示信息和运行定义，`version` 只是在更新 `data`
时递增；App 安装快照只落盘 `SKILL.md`、文件和基本版本元数据，没有保存工具绑定、权限、内容哈希与
工具契约。运行时读取本机旧 `SKILL.md`，却从最新 `catalog_skills` 实时解析工具，因此 Server 修改工具
后，未升级的客户端会执行“旧指令 + 新工具”。Run 的 `permission_snapshot` 也只记录 slug 与工具名，
无法重现某次运行实际使用的发布内容。

## 触发场景

1. App 安装带只读工具的 v1 Skill。
2. Console 修改该 Skill 指令并新增写工具，Server 目录版本变成 v2。
3. App 完成目录 pull 但用户没有升级本机 Skill。
4. 运行 v1 本机指令时取得 v2 工具绑定；历史 Run 不能证明使用了哪个原子版本。

## 影响

P0：权限可在用户未确认升级时扩大，运行内容不可复现，审计和回滚均缺少可信边界。

## 建议修法

- 为 AgentMate Skill 建立不可变 release manifest，原子包含 instructions、files、tools、permissions、
  release/version、内容哈希和工具契约版本。
- 安装/升级完整落盘 manifest；运行时只从已安装 manifest 解析指令和工具，不再混用最新目录定义。
- Run 固化 release id/version/hash、工具契约和权限快照；同一次 Run 不受后续目录更新影响。
- 保持旧安装包兼容：没有 manifest 时按旧元数据构造保守快照，但不得获得安装后新增的工具。

## 验证

- 安装 v1 后发布 v2 工具变更，未升级运行仍只获得 v1 工具；升级后原子切换到 v2。
- 篡改任一已安装文件会触发 hash 校验失败，Skill 不进入运行时。
- Run API 能返回完整 Skill release 快照，重试仍沿用相同版本。
- 旧格式本机 Skill 可继续作为纯指令 Skill 使用。

## 处理记录（2026-07-21）

- 改动：AgentMate 目录技能安装/升级时生成 `_agentmate_release.json`，用 SHA-256 原子覆盖
  `SKILL.md`、附件、工具绑定、权限和工具契约；运行时只从已安装且校验通过的 manifest 解析工具，
  legacy 安装保守降级为纯指令；详情返回 release/hash/完整性，Run 固化 `skill_releases` 快照。
- 验证：新增 v1→Server v2 未升级仍使用 v1 工具、升级后切换 v2、文件篡改拒绝、Run 快照持久化回归；
  `py_compile` 通过，相关 Python 回归 19/19 通过。
- commit：见本次 WB-245 提交。
