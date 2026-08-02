---
id: WB-357
title: 长对话摘要与模型上下文未纳入统一硬预算
severity: P1
area: backend
status: open
origin: 既有实现
files:
  - backend/agent/session_context.py:163
  - backend/agent/runtime.py:975
  - backend/storage/model_governance.py:84
created: 2026-08-03
---

## 问题

摘要 LLM usage 未计入 Run；主模型在生成结束后才检查预算；历史窗口未按当前模型上下文动态收缩；缓存命中 Token 未进入成本估算。

## 触发场景

长会话触发摘要、选择较小上下文模型或 Run 接近 Token 上限时，实际调用可能超限，成本账单不完整。

## 影响

P1。成本控制不是硬门禁，且可能触发模型上下文错误。

## 建议修法

摘要返回 usage 并计入 Run；每轮按剩余预算和模型上下文夹紧输出；上下文构造接收动态预算；解析并保存缓存 Token。

## 验证

- 摘要、缓存和主调用 Token 均进入 Run；
- 首轮无法超过硬预算；
- 小上下文模型会预留系统、工具与输出空间；
- 相关成本与上下文回归通过。
