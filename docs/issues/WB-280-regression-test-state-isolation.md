---
id: WB-280
title: 回归测试泄漏 DB 与安全上下文导致顺序相关失败
severity: P2
area: test
status: fixed
origin: 🆕 近期改动
files:
  - backend/tests/regression/test_skill_market_boundary.py:19
  - backend/tests/regression/test_tool_execution_policy.py:16
created: 2026-07-22
---

## 问题
Skill market 路由测试直接调用需要当前用户的 handler，却没有初始化隔离 DB；工具执行策略测试没有清空前序 runtime 留下的 security owner context。两者依赖发现顺序和其他测试副作用。

## 触发场景
全量 discover 时分别报 `no such table: users`、`no such table: user_settings`；工具策略文件独立模块运行还因未自行加入 backend 路径而 import 失败。

## 影响
P2。产品行为无误，但回归门禁不确定且无法独立复现。

## 建议修法
Skill market 测试建立/销毁独立 DB；工具执行策略测试自行设置 backend import path，并在每例前后清空 security context。

## 验证
- 两个测试文件均可独立运行。
- 全量 backend regression 不再出现 users/user_settings 缺表。

## 处理记录（2026-07-22）
- 改动：Skill market 测试每例创建并关闭独立 SQLite；工具执行策略测试自行加入 backend import path，并在 setUp/tearDown 清空 security owner context。
- 验证：两个文件编译通过；`test_skill_market_boundary` + `test_tool_execution_policy` 6/6 独立通过。
- commit：本提交。
