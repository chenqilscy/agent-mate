---
id: WB-374
title: 工具权限仅记录未执行门禁且后台外部输入可调用高权限工具
severity: P0
area: backend
status: in-progress
origin: 既有实现
files:
  - backend/agent/tool_execution.py:111
  - backend/agent/scheduler.py:145
created: 2026-08-03
---

## 问题
Tool.permissions 和 Run.permission_snapshot 仅用于声明与记录，execute_tool 未根据运行来源、审批或预授权做执行门禁；Automation/Webhook/Relay 可进入包含 run_command 的 exec 工具集合。

## 触发场景
外部 Webhook 或 Relay payload 含提示注入 → 无人值守 Automation 调用 LLM → 模型选择 run_command → 以后端宿主权限执行。

## 影响
P0。外部不可信输入可能驱动本机任意命令及网络访问，提示文本和字符串黑名单不是授权边界。

## 建议修法
在所有 Tool/MCP 调用前建立统一默认拒绝策略；区分 interactive/background/external 来源；后台高风险权限必须使用与 run/tool/参数/期限绑定的预授权。

## 验证
外部后台运行默认拒绝 process.execute/host.unrestricted/network.unrestricted；明确范围的预授权可通过；交互路径和普通安全工具不回归；审计失败不得放行高风险调用。
