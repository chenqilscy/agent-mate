---
id: WB-434
title: Local Agent Core 收缩为本机执行与 IPC 服务
severity: P1
area: backend
status: open
origin: 🏚 迁移遗留
files:
  - backend/main.py:1
  - backend/agent:1
  - backend/routers:1
  - backend/storage/db.py:1
  - src-tauri/src/lib.rs:1
created: 2026-08-08
---

## 问题

父项：[WB-431](archive/2026/WB-400-499.md#wb-431)，依赖 WB-433。当前本地 backend 同时包含业务 CRUD、身份代理、同步镜像、Agent Runtime、工具与设备设置，无法作为边界清晰的 Local Agent Core。

## 触发场景

桌面安装包启动 sidecar 后，本地 `:8101` 既能修改业务数据又能执行系统工具；任何业务迁移都要同时修改本地 schema、路由和 Server 代理。

## 影响

P1：职责耦合扩大本机攻击面、迁移面和故障半径。

## 建议修法

- 保留 Agent Runtime、LLM、工具、MCP、credential、working copy、event WAL 与 device control。
- 删除/禁用项目、会话、任务、自动化等业务权威路由和对应写库路径。
- 建立 Tauri IPC/Named Pipe 或受保护 loopback 本机 API，只暴露设备状态、权限、文件选择和运行控制。
- 把本地存储拆分为 secure secret、WAL、working copy 与 disposable cache。

## 验证

- 删除空白环境中的本地业务数据库后，Local Agent 仍可注册设备、领取并完成 Server Run。
- 本机接口不能创建或修改 Server 业务实体，且不向局域网暴露。
- secret 不进入子进程环境、WAL、日志或前端；退出/托盘/重启生命周期正确。
