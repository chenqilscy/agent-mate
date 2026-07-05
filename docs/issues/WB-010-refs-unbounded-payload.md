---
id: WB-010
title: refs 无数量/总量上限、name 不截断、/chat 无请求体上限
severity: P1
area: backend
status: open
origin: 🆕 近期改动
files:
  - backend/agent/runtime.py:204
  - backend/routers/chat.py:15
created: 2026-07-06
---

## 问题
每个 ref 正文截断到 8000 字符（`runtime.py:204`），但：
- **refs 个数无上限**；
- `name`（`runtime.py:208`）完全不截断；
- `ChatBody.refs: list[dict]` 与 `text` 都无大小校验，应用层也无请求体上限。

N×8000 + 任意大的 name/自由字段可撑爆上下文/内存。

## 触发场景
前端一次引用很多文件，或恶意/异常客户端提交超多/超大 refs。

## 影响
上下文膨胀、token 浪费、潜在内存压力。

## 建议修法
限制 refs 数量（如 ≤10）、总字节数（如 ≤32KB）并截断 `name`（如 ≤120 字符）；给 `/chat` 加请求体大小上限（中间件或校验）。

## 验证
提交 50 个大 ref → 被拒或被安全截断，不影响其它会话。
