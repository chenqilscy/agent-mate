---
id: WB-083
title: 目录运营中心 —— 连接器 类型化 CRUD（launch spec 编辑器）
severity: P2
area: frontend
status: open
origin: WB-078 epic
files:
  - hub/web/console.html
created: 2026-07-08
---

## 问题

连接器目录只能裸 JSON 编辑，launch spec（内置服务 / 第三方 stdio / 凭据变量名）结构复杂，手写易错。

## 触发场景

平台管理员想登记一个新连接器（内置或第三方 npx）—— 需要正确拼 `builtin_server` 或 `command/args/secret_env/requires`。

## 影响

P2：目录运营中心第二块。

## 建议修法

在 WB-082 框架上加**连接器**类型（`CONNS` + `CONN_META`）结构化编辑器：
- icon / 名称 / 状态（rdy 内置即用 / tok 需凭据）。
- launch spec 编辑器：二选一
  - **内置**：`builtin_server`（下拉：notes/clock/search/telegram/kdocs…）+ 可选 `requires`/`requires_bin`。
  - **第三方 stdio**：`command` / `args[]` / `secret_env`（**仅环境变量名**，绝不填值，铁律 4）/ `requires`。
- 生成的 JSON 与 `catalog_seed.BUILTIN_CONNECTORS` 逐字同构，客户端 pull 后可真接入。

## 验证

新增内置/第三方连接器→`GET /catalog` launch 结构正确→客户端 pull 后 App 连接器可选、可真启动（内置即用；第三方需本机凭据）。
