---
id: WB-276
title: 停止生成时 LLM HTTP 流未被立即关闭
severity: P3
area: backend
status: fixed
origin: 🏚 迁移遗留
files:
  - backend/agent/runtime.py:689
  - backend/agent/llm.py:87
created: 2026-07-22
---

## 问题
运行时在停止事件触发后从 `async for stream_chat(...)` 直接 `break`。Python 不保证此时立即 `aclose` 异步生成器，因此 `llm.py` 内的 `httpx.AsyncClient`/响应流可能等到异步生成器回收才退出 `async with`。

## 触发场景
模型仍在流式返回时点击停止，运行时结束本轮循环，但上游 HTTP 连接未同步关闭。

## 影响
P3。短时间占用连接/响应资源；不影响结果持久化正确性。

## 建议修法
使用 `contextlib.aclosing` 管理 `stream_chat` 异步生成器，使正常完成、停止 break、异常三条路径都立即调用 `aclose`。

## 验证
- fake LLM stream 在停止 break 后其 `finally` 已执行。
- run 状态为 cancelled，不残留活动 stop 注册。
- 后端编译和回归测试通过。

## 处理记录（2026-07-22）
- 改动：LLM 每轮流改由 `contextlib.aclosing` 管理；停止、正常完成或异常退出都会立即 `aclose`，从而退出 `llm.py` 的响应与 client `async with`。
- 验证：`runtime.py` 与测试文件编译通过；`test_llm_stream_cleanup` 通过，fake stream 在 stop break 后同步执行 `finally`，Run 为 `cancelled`，session 的 stop 注册已清除。测试中隔离了另行登记的既有 WB-277。
- commit：本提交。
