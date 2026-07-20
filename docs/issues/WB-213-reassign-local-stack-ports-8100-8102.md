---
id: WB-213
title: 本地三层服务端口统一调整为 8100、8101、8102
severity: P1
area: fullstack
status: fixed
origin: 🆕 近期改动
files:
  - server/config.py:22
  - backend/config.py:68
  - vite.config.ts:9
  - src/lib/api.ts:11
  - src-tauri/tauri.conf.json:8
  - run-stack.ps1:1
created: 2026-07-20
---

## 问题

当前 AgentMate Server 使用 `8100`，但 App 后端和前端仍分别使用 `8000`、`5173`。用户要求三层端口收敛到连续的 `8100 / 8101 / 8102`，现有启动脚本、代理、Tauri 开发地址、CORS、测试和文档仍绑定旧端口。

## 触发场景

按新端口规划启动系统时，App 前端仍监听 `5173` 并代理到 `8000`，Tauri 壳和功能测试也继续访问旧地址，导致三层无法按新拓扑协同工作。

## 影响

P1：端口配置分散在运行时、桌面壳、测试和文档中；只改监听端口会直接造成前端代理、CORS 或测试链路断开。

## 建议修法

- 保持 AgentMate Server 默认端口 `8100`。
- 将 App 后端默认端口改为 `8101`，App 前端开发端口改为 `8102`。
- 同步更新 Vite 代理、Tauri API/开发地址、CORS、启动脚本、功能测试默认地址、示例环境变量与当前文档。
- 更新 issue-tracker 的常用命令示例并重新校验 skill。

## 验证

- `8100 / 8101 / 8102` 分别由 Server、App 后端、App 前端监听，旧 `8000 / 5173` 不再监听。
- 前端可访问，`/api` 经 Vite 正确代理到 App 后端，App 后端保持连接 Server。
- TypeScript、生产构建、Python 编译、回归测试和 skill 校验通过。

## 处理记录（2026-07-20）

- 改动：保留 Server `8100`，将 App 后端默认端口改为 `8101`、Vite 前端改为严格端口 `8102`；同步更新代理、Tauri 地址、CORS、功能测试、启动脚本、环境示例、当前文档和 issue-tracker 常用命令。本机私有 `backend/.env` 同步设为 `PORT=8101` 并连接本地 Server。
- 验证：回归测试 12/12、TypeScript、Vite 生产构建、Python 编译、`cargo check` 与 Skill 校验均通过；真实启动后 `8100/8101/8102` 分别响应 Server、App API 和前端，前端 `/api/server/status` 返回 Server 已启用，旧 `8000/5173` 均未监听。
- commit：随本提交。
