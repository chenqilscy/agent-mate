---
id: WB-356
title: 长期记忆嵌入在对话事件循环中同步执行
severity: P1
area: backend
status: open
origin: 既有实现
files:
  - backend/agent/runtime.py:369
  - backend/agent/memory.py:159
  - backend/agent/mem_embed.py:37
created: 2026-08-03
---

## 问题

`run_chat` 直接同步构造记忆提示，路径可能加载本地模型、执行推理、联网请求或回填旧向量，占用 FastAPI 事件循环。

## 触发场景

首次启用本地 embedding、在线 GLM 延迟或存在待回填记忆时发起聊天，其他请求与停止操作被同步工作阻塞。

## 影响

P1。单个用户的记忆检索可拖慢全部会话。

## 建议修法

将同步 embedding/检索整体移入 `asyncio.to_thread`，保持 owner/contextvar 语义；限制回填并建立降级测试。

## 验证

- 定向异步测试证明 embedding 不在事件循环线程执行；
- embedding 失败仍诚实回退；
- 后端完整回归通过。
