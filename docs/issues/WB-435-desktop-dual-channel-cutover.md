---
id: WB-435
title: Desktop UI 切换 Server 业务通道与 Local Agent IPC
severity: P1
area: frontend
status: open
origin: 🏚 迁移遗留
files:
  - src/lib/api.ts:1
  - src/stores:1
  - src/platform:1
  - src-tauri/src/lib.rs:1
created: 2026-08-08
---

## 问题

父项：[WB-431](archive/2026/WB-400-499.md#wb-431)，依赖 WB-432、WB-433、WB-434。Desktop UI 当前把本地 backend `/api` 作为唯一入口，业务状态和本机能力没有明确通道边界。

## 触发场景

项目、会话、Run、文件选择和本机权限都经同一个 API client/store 访问，导致 Server 数据必须先经过本地代理和镜像才能展示。

## 影响

P1：前端不切换就无法删除本地业务 CRUD，也不能真实验证跨设备恢复。

## 建议修法

- 建立 Server API client（业务/认证/SSE）和 Local Agent client（IPC/设备/文件/权限）两套明确接口。
- 项目、会话、消息、任务、Run、自动化、目录和资产 store 改读写 Server。
- 本机文件选择、working copy、权限确认、credential 和设备诊断改走 Local Agent。
- UI 显示 Server 离线只读、设备离线、WAL 积压和 capability mismatch，不制造假成功。

## 验证

- 换设备或重装桌面端后，登录即可恢复完整业务数据。
- Local Agent 停止时仍可浏览 Server 数据，但执行和本机操作明确不可用。
- Server 停止时缓存只读、写操作明确失败；明暗主题和窄屏状态提示通过实测。
