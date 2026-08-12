---
id: WB-524
title: 发布回归契约漂移且 main 分支推送不触发 CI
severity: P1
area: misc
status: in-progress
origin: 🏚 迁移遗留
files:
  - .gitea/workflows/quality.yml:6
  - scripts/validate-v1-rc.ps1:41
  - backend/tests/integration/test_wb112_server_backend_http.py:35
  - backend/tests/regression/test_wb517_server_workspace_companion.py:55
created: 2026-08-12
---

## 问题

质量工作流只监听 `master`，仓库实际开发/远端分支为 `main`。回归集仍引用已删除的 Desktop 业务 View，集成测试仍通过已经明确废止的环境变量配置 Server 地址；完整门禁因而无法作为当前架构的发布证据。

## 触发场景

- 直接推送 `main`：push workflow 不运行。
- 跑 Local Agent 回归：出现 18/19 failures 与 2 errors。
- 跑集成测试：4 项中 3 项因 Server 未配置失败。

## 影响

P1：坏提交可能绕过 CI；本地发布脚本持续红灯，真实回退和过期断言混在一起。

## 建议修法

工作流对齐 `main`；按 WB-517～521 后的新可达边界更新或删除陈旧回归；集成测试通过真实设备设置数据库配置 Server；保持未跟踪测试门禁。

## 验证

- 完整 `validate-v1-rc.ps1` Engineering lane 通过。
- `main` push 触发 workflow。
- 回归与集成测试连续运行结果稳定。
