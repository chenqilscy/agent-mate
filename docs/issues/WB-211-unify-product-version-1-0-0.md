---
id: WB-211
title: 产品版本在侧栏显示 v5.2.3 且发布配置仍为 0.1.0
severity: P2
area: fullstack
status: fixed
origin: 🏚 迁移遗留
files:
  - src/components/layout/Sidebar.tsx:205
  - package.json:4
  - src-tauri/tauri.conf.json:4
  - src-tauri/Cargo.toml:3
  - backend/main.py:46
  - server/main.py:55
created: 2026-07-20
---

## 问题

侧栏仍直接显示腾讯参考版本 `v5.2.3`，而 AgentMate 的前端包、Tauri 桌面包和两套 FastAPI 服务仍标为早期开发版本 `0.1.0`，产品版本信息不一致。

## 触发场景

启动 AgentMate 后查看左上角品牌区，会看到 `v5.2.3`；检查安装包元数据或 OpenAPI 信息时又会看到 `0.1.0`，均不符合当前要求的 `v1.0.0`。

## 影响

P2：不影响核心功能，但会误导用户、安装包升级判断和接口文档，发布版本缺少单一口径。

## 建议修法

- 将侧栏版本改为 `v1.0.0`。
- 将前端包、Tauri 配置/Cargo 包以及 App API、Server API 的产品版本统一为 `1.0.0`。
- 腾讯 WorkBuddy 参考原型和历史 issue 中的 `v5.2.3` 作为来源记录保留。

## 验证

- 浏览器中左上角显示 `v1.0.0`。
- `package.json`、Tauri 配置/Cargo 包、App API 和 Server API 均报告 `1.0.0`。
- TypeScript 检查和生产构建通过。

## 处理记录（2026-07-20）

- 改动：侧栏显示改为 `v1.0.0`；`package.json`、Tauri 配置、Cargo 包以及 App API / Server API 的版本统一为 `1.0.0`，并增加跨端版本一致性回归测试。
- 验证：回归测试 11/11、TypeScript、Vite 生产构建、Python 编译和 `cargo check` 均通过；浏览器实测侧栏显示 `v1.0.0`，重启后的两套 OpenAPI 均报告 `1.0.0`。
- commit：随本提交。
