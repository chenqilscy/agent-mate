---
id: WB-387
title: 线程工具超时后无界等待导致 Run 与关闭永久阻塞
severity: P1
area: backend
status: in-progress
origin: 🆕 近期改动
files:
  - backend/agent/tool_execution.py:64
  - backend/tests/regression/test_tool_execution_policy.py:102
created: 2026-08-04
---

## 问题
WB-380 为避免线程工具在取消后迟到写入，改成 timeout/stop 后等待 executor 线程完成；但等待没有第二道上限，`timeout_seconds` 只决定最终分类，不再约束真实返回时间。

## 触发场景
同步线程工具永久阻塞或底层 I/O 不返回 → deadline、用户停止或 SSE 断流已经发生 → runtime 仍永久等待线程，Run、请求清理和进程关闭全部卡住。

## 影响
P1。单个不可控工具可长期占用 Run 和后台并发槽，并阻断断流清理；与 UI 展示的超时契约不一致。

## 建议修法
区分只读线程兼容路径与有副作用工具：有副作用且不能协作取消的工具必须使用可杀子进程隔离或拒绝执行；线程兼容路径在 deadline 后立即返回且只能承载无副作用工具。测试必须验证真实 wall-clock 上限和无迟到写入。

## 验证
永久阻塞工具不会超过有界清理窗口；有副作用线程工具不能进入不可杀路径；run_command 进程树取消、MCP async 取消与正常只读工具不回归。
