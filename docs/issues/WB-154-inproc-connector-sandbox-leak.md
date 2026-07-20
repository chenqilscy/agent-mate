---
id: WB-154
title: 内置连接器经 os.environ 传 workspace 目录 —— 并发 run 串项目沙箱
severity: P1
area: backend
status: fixed
origin: 既有实现
files:
  - backend/agent/mcp_client.py:181
  - backend/mcp_servers/notes.py:22
  - backend/mcp_servers/search.py:22
created: 2026-07-14
---

## 问题

内置连接器（`本地便签` notes、`工作区检索` search）走 MCP in-process 传输。`mcp_client.py:181-182` 把本轮 workspace 目录写进**进程全局** `os.environ["AGENTMATE_NOTES_DIR"]`；`notes.py:22`/`search.py:22` 在**调用时**读同一全局 env。`asyncio.to_thread`/contextvar 都不隔离 `os.environ`，多个并发 `run_chat` 会互相覆盖。

## 触发场景

两个并发 run_chat 在不同项目工作区、都挂了 `本地便签`（如两个助理渠道、或自动化 + 对话）：Run A 设 env=项目A，Run B 覆盖成项目B；随后 Run A 调 `add_note` 会写进**项目B** 的 `notes.json`。跨项目读写，违反铁律#3 沙箱隔离。

## 影响

P1：跨项目数据串写/串读。in-process 连接器是打包版默认路径（A2.1），并发在多助理/自动化下真实存在。

## 建议修法

不用进程全局 env 传 in-process 服务器的目录。方案：`notes.py`/`search.py` 的目录解析改为「优先读 `os.environ['AGENTMATE_NOTES_DIR']`（spawned 子进程路径，spawn 时注入），否则回退 `agent.sandbox.current_root()`（in-process 路径，逐 run contextvar 快照，天然隔离）」；`mcp_client.py` 去掉第 181-182 行的全局写。in-process 服务器任务在本 run 的 context 下创建 → 读 contextvar 得本 run 的根，各 run 互不影响。

## 验证

- `py_compile`。
- 单元/隔离：设 sandbox root=A 建 in-mem session 调 add_note，再设 root=B 建另一 session 调 add_note，各自 notes.json 落在各自目录（并发不串）。
- 回归：standalone `python notes.py`（env 注入）仍读 env；单 run 项目会话 add_note 仍落本项目。

## 处理记录（2026-07-14）

- 改动：
  - `backend/mcp_servers/notes.py` `_dir()` / `backend/mcp_servers/search.py` `_root()`：目录解析改为「`os.environ['AGENTMATE_NOTES_DIR']` 优先（spawned 子进程），否则 `agent.sandbox.current_root()`（in-process，逐 run contextvar）」。
  - `backend/agent/mcp_client.py`：删掉内置服务器分支里 `os.environ["AGENTMATE_NOTES_DIR"] = ...` 的全局写。
- 验证：py_compile 过；隔离测试脚本模拟两个并发 run（root A/B，交错设 root 后各自 add_note）→ 各 notes.json 落在各自项目目录（`ISOLATION_OK`），证明 contextvar 经 MCP in-memory 传输正确逐 run 隔离，不再串。
- commit：未提交（待用户确认）。
