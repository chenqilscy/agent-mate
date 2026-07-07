---
id: WB-080
title: 门户项目管理面 —— 配置编辑（指令 + 连接器/专家/技能 picker）
severity: P2
area: frontend
status: fixed
origin: WB-078 epic
files:
  - hub/web/console.html
created: 2026-07-08
---

## 问题

门户项目详情只有 成员/邀请/讨论/在线/时间线，缺 App 项目的**配置**：指令、连接器、专家、技能。
（`Project` 模型已含这些字段，`PATCH /projects` 已支持写，仅门户 UI 缺。）

## 触发场景

打开某项目 → 想改项目指令、增删连接器/专家/技能 —— 门户里没有入口。

## 影响

P2：项目管理与 App 对齐的核心缺口（可管理部分）。

## 建议修法

项目详情加「配置」区：
- **指令**：多行编辑 → `PATCH /projects/{id}` `{instruction}`。
- **连接器 / 专家 / 技能**：从**目录**（`GET /catalog/{CONNS|EXP_GRID|SK_GRID}`，含本地兜底名单）多选，写回
  `PATCH /projects/{id}` `{connectors|experts|skills}`（字符串名数组，与 App 一致）。
- Viewer 只读；Admin/Owner 可改。
- 保留既有 成员/邀请/讨论/在线/时间线。

## 验证

改指令→持久化；勾选连接器/专家/技能→`PATCH` 后重开仍在；客户端 pull 后 App 项目配置一致；Viewer 不可改。

## 处理记录（2026-07-08）

`console.html` 项目详情顶部加全宽「配置」卡：指令 textarea + 连接器/专家/技能 三个 chip 编辑器
（当前项为可删 chip；输入框带 `datalist` 建议——从 Hub 目录 `NP_CONNS`/`EXP_GRID`/`SK_GRID` 取名，目录空时允许自由输入；
名字须与本地 backend 内置定义一致才真生效）。「保存配置」一次 `PATCH /projects/{id}` 提交 instruction+三数组，回读刷新。
Viewer（`project.role==='Viewer'`）只读、无保存按钮（后端 can_write 亦兜底 403）。**验证**：Playwright 登录 alice→打开项目→
配置卡指令预填→加专家「创业伙伴」→保存→`GET /projects/{id}` 显示 `experts:['创业伙伴']`、指令持久化。
