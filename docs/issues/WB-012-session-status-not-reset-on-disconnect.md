---
id: WB-012
title: 客户端断开后会话状态永久停在 running/waiting
severity: P1
area: backend
status: fixed
origin: 🆕 近期改动
files:
  - backend/agent/runtime.py:391
  - backend/agent/runtime.py:418
created: 2026-07-06
---

## 问题
`run_chat` 的 `finally`（`runtime.py:391`）只清理 `_stop_events` / `_answers` / `mcp_stack`，**不重置 session 状态**。正常结束时 `touch_session(status="done")` 在 `:418`，但取消路径（`CancelledError`，客户端断开）不会走到那里；异常路径只在 `except`（`:379/:386`）里置 `idle`，而 `CancelledError`（`BaseException` 子类）不进 `except Exception`。

## 触发场景
SSE 传输中或 ask_user 等待中关闭浏览器标签。侧栏该会话永远显示「运行中/等待」。

## 影响
会话状态与实际不符，侧栏出现假「运行中」。

## 建议修法
`finally` 里兜底：若本 run 未正常 `done`，则 `touch_session(status="idle")`（或更精确地捕获 `CancelledError` 后置状态再重新抛出）。注意与 WB-007（前端 finalize）区分——这是服务端状态。

## 验证
发消息生成中直接关标签 → 重开应用，该会话状态不再是「运行中」。

## 处理记录（2026-07-06）
- 改动：run_chat 把「注册 run 之后」的全部逻辑（含 status running、连接器 spawn await、主循环）纳入同一 try；finally 用 `finished_ok` 兜底：未正常完成（客户端断开→CancelledError/GeneratorExit）则 `touch_session(idle)`。连接器 open 进 try 连带修 WB-023「mcp_stack 在 try 外」泄漏。（backend/agent/runtime.py）
- 验证：verify_runtime.py「cancelled run reset to idle」「run unregistered on cancel」PASS。
