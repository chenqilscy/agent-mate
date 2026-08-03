---
id: WB-380
title: 同步线程工具超时取消后仍可能继续产生副作用
severity: P2
area: backend
status: in-progress
origin: 既有实现
files:
  - backend/agent/tool_execution.py:121
created: 2026-08-03
---

## 问题
取消 asyncio.to_thread 的包装 task 不会终止底层线程，非 subprocess 工具可能在上层报告取消后继续写入。

## 触发场景
同步工具阻塞并超过 deadline → Run 返回 timeout/cancelled → 工作线程继续完成文件或外部系统副作用。

## 影响
P2。用户看到的状态与真实副作用不一致，重试可能重复写入。

## 建议修法
引入协作式 cancellation token；有写副作用且不支持协作取消的工具使用可杀子进程或拒绝运行；完成副作用边界前不报告已取消。

## 验证
可取消线程工具收到 token 后停止且无迟到写入；不支持安全取消的有副作用工具被策略拒绝；只读兼容路径不回归。
