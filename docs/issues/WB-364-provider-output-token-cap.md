---
id: WB-364
title: 动态上下文预算可生成超过模型输出上限的 max_tokens
severity: P1
area: backend
status: open
origin: 🆕 近期改动
files:
  - backend/agent/runtime.py:1042
created: 2026-08-03
---

## 问题

WB-357 在模型未显式传入 `max_output_tokens` 时，把整个剩余上下文窗口作为请求 `max_tokens`。对于上下文窗口大于供应商单次输出上限的模型，请求在生成前被 400 拒绝。

## 触发场景

使用未配置单次输出上限、但上下文窗口较大的 GLM 模型发起普通对话 → AgentMate 发送超出供应商 `[1, 131072]` 范围的 `max_tokens` → LLM 400。

## 影响

P1。普通对话和 Run 重试可稳定失败，是长对话预算改造的发布阻断回归。

## 建议修法

将“模型上下文窗口”与“单次最大输出”分开治理：优先使用模型元数据中的输出上限，未声明时使用保守默认值，同时仍受剩余上下文和 Run token 预算夹紧。

## 验证

- 大上下文模型未配输出上限时，不会传出超范围 `max_tokens`；
- 显式输出上限、上下文剩余与 Run 预算三者取最小值；
- 回归与真实 GLM 请求通过。
