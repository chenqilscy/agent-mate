---
id: WB-230
title: Agent 运行缺少 Langfuse 可观测链路
severity: P2
area: backend
status: fixed
origin: 既有实现
files:
  - backend/agent/runtime.py:498
  - backend/agent/llm.py:43
  - backend/config.py:62
created: 2026-07-21
---

## 问题

AgentMate 目前只把面向用户的执行 trace 持久化到本地消息，并通过 SSE 回放；每轮模型请求、工具调用、
首 token 延迟、模型错误与 token 用量之间没有独立的 LLM 可观测链路，无法在不改 UI 契约的前提下按会话、
模型和工具分析延迟、错误与成本。

## 触发场景

一次对话经过多轮 `stream_chat` 和工具调用后，只能从消息表与前端 trace 卡片看到有限的执行结果；
当模型调用慢、工具失败或 token 消耗异常时，无法还原每一轮 generation 与 tool 的父子关系和耗时。

## 影响

P2：不阻断聊天主流程，但会显著增加模型质量、性能、成本和工具故障的定位成本，也缺少后续自动评估的数据基础。

## 建议修法

- 在本地 backend 增加默认关闭、配置不完整时 no-op 的 Langfuse v4 客户端封装。
- 每次 `run_chat` 建一个 agent 根 observation，每轮模型请求建 generation，真实工具/MCP 调用建 tool。
- 记录模型、耗时、首 token 时间、token 用量和错误状态；默认不上传系统提示词、文件正文、reasoning 与原始工具输出。
- Langfuse 故障不得改变 SSE、消息持久化或离线 local-first 行为；应用退出时安全 shutdown。
- 密钥只从后端配置读取，并纳入通用子进程环境剔除规则。

## 验证

- 未配置或关闭 Langfuse 时无外部请求，聊天与既有测试零变化。
- 使用 fake client 验证 agent → generation/tool 层级、usage、错误与取消路径均正常结束。
- 本地 Langfuse 可达时，真实多轮对话能看到同一 session 下的根 trace、模型轮次和工具调用。
- trace 默认不包含系统提示词、refs 文件正文、reasoning、密钥或原始工具结果。
- Langfuse 不可达时仍能完成 SSE 回复；退出时执行 shutdown。

## 处理记录

- 处理日期：2026-07-21
- 实现：新增 fail-open Langfuse v4 封装；为每次聊天建立 agent 根 observation、为每轮模型请求建立
  generation、为本地/MCP/知识库调用建立 tool/retriever 子 observation，并记录模型、TTFT、usage、错误和取消状态。
- 隐私：默认仅上传内容类型与长度摘要，用户 ID 哈希化；只有显式开启 `LANGFUSE_CAPTURE_CONTENT=1`
  才采集正文，且统一递归脱敏。Langfuse 密钥已纳入通用子进程环境剔除。
- 配置与交付：补齐 `.env.example`、健康状态、退出 shutdown、依赖锁定、PyInstaller hidden imports 与部署文档。
- 自动验证：33 条 backend regression 全通过，其中 Langfuse 专项 6 条；改动 Python 文件 `py_compile` 通过；
  sidecar 重新打包成功，并在独立端口启动后通过 `/api/health`。
- 真机验收：本地 Langfuse 3.222.0 健康；两次真实 AgentMate 工具对话均写入同一会话链路，页面/API
  可见 agent → generation/tool 层级、模型与 token 用量；默认 trace 未出现提示词、工具正文或 Langfuse 密钥。
