---
id: WB-315
title: Server 权威项目配置与成员写失败后回退本地，违反统一同步契约
severity: P1
area: backend
status: open
origin: 既有实现
files:
  - backend/routers/projects.py:172
  - backend/routers/projects.py:233
  - backend/routers/projects.py:265
  - backend/routers/projects.py:290
  - docs/agentmate-数据分层与同步规范.md:52
created: 2026-07-24
---

## 问题

`server-origin` 项目的配置和成员操作会先代理到 Server，但 Server 调用返回失败后仍继续执行本地
`db.update_project`、`db.add_project_member`、`db.remove_project_member`。当前唯一数据分层规范明确要求
Server 权威协作实体写失败时显式失败，不能把本地镜像写成假成功；任务和里程碑路由已经按该规则返回 503，
项目配置与成员路由却仍保留旧版 local-first 写回退。

## 触发场景

登录 Server 账号并同步一个团队项目 → 断开 Server 或令其不可达 → 在 App 修改项目指令、连接器、专家、
技能，或添加/改角色/移除成员 → App 返回成功并修改本地镜像，但 Server 权威数据未变；恢复连接后形成冲突，
或在后续 pull 中回到 Server 值。

## 影响

P1。用户会得到“已保存/已添加/已移除”的成功反馈，但团队其他成员看不到同一结果；成员权限类操作还可能在
本机短暂呈现与 Server 权威角色不同的状态。虽然增量镜像会保留冲突而非静默覆盖，仍违反统一写契约并制造
不可跨端成立的假成功。

## 建议修法

- 对 `server-origin` 且请求带有效 Server token 的项目配置/成员写，代理失败统一返回 503，不继续本地写。
- 纯本机项目继续保留本地全功能；Server 项目读请求继续允许 last-known-good。
- 更新旧的离线写回退测试，使项目/成员与任务/里程碑遵循同一契约。
- UI 对 503 展示“未保存/未变更”，不要显示成功 toast。

## 验证

- 隔离 Server+App：在线配置/成员操作真落 Server 并刷新本地镜像。
- Server 停止后四类写操作均返回 503，本地项目/成员镜像不变；恢复后无需处理由失败写制造的冲突。
- 本机项目配置与成员操作不回归；任务/里程碑既有离线拒写回归继续通过。
