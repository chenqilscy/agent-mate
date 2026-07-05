---
id: WB-002
title: 工具同步执行阻塞事件循环，期间 /stop 失效、全部会话 SSE 卡死
severity: P0
area: backend
status: open
origin: 🏚 既有实现
files:
  - backend/agent/runtime.py:368
  - backend/agent/tools.py:154
  - backend/agent/skills.py:25
created: 2026-07-06
---

## 问题
`run_tool()`（`runtime.py:368`）是**同步调用**，直接跑在 `run_chat` 异步生成器所在的事件循环线程上。其中：
- `run_command` 的 `subprocess.run(timeout=30)`（`tools.py:154`）
- `web_fetch` 技能的同步 `httpx.get(timeout=15)`（`skills.py:25`）
- `read_file`/`write_file` 的文件 IO

全部会阻塞整个 event loop。

## 触发场景
任一工具执行期间（命令最长 30s、抓网页 15s），**其余所有会话的 SSE 流全部冻结**；更糟的是循环被占住 → 此间 `/stop` 请求根本无法被处理，「停止」在长命令上失效（与 WB-001 的「停不掉」叠加）。

## 影响
服务器级停摆 + stop 失效。单用户下偶发，多标签/多会话下明显。

## 建议修法
- `outcome = await asyncio.to_thread(run_tool, tool, args)`。
- `web_fetch` 改用 `httpx.AsyncClient` 的 `await client.get(...)`。
- 确认所有工具执行点都不再有同步阻塞调用直接落在事件循环上。

## 验证
起一个 `run_command sleep 10`（或长抓取）的会话，同时在另一会话发消息 → 后者应正常流式、不被前者卡住；长命令期间点「停止」应能中断。
