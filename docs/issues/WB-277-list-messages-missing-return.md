---
id: WB-277
title: list_messages 丢失返回体导致全部对话运行失败
severity: P1
area: backend
status: fixed
origin: 🆕 近期改动
files:
  - backend/storage/db.py:3047
created: 2026-07-22
---

## 问题
WB-255 在 `list_messages` 查询之后插入 `create_work_item_launch` 时，把原有的 Message 行映射和 `return out` 整段挤掉。函数固定返回 `None`，而 `_build_llm_messages` 会立即迭代该结果。

## 触发场景
任意用户发送对话，运行时执行 `for m in db.list_messages(session_id)`，抛出 `TypeError: 'NoneType' object is not iterable`，LLM 调用尚未开始。

## 影响
P1。影响全部 App 对话、项目执行及依赖同一 runtime 的链路，是 WB-255 之后的全局回归。

## 建议修法
恢复原有 Message 映射与返回值；增加空历史和包含 trace/usage 的有序历史回归测试，并让真实 runtime 测试不再 mock `list_messages`。

## 验证
- 空会话返回 `[]`。
- 消息按 `created_at` 返回并正确反序列化 trace/usage。
- WB-276 runtime 测试在不 mock `list_messages` 时通过。
- 后端编译和回归测试通过。

## 处理记录（2026-07-22）
- 改动：恢复 `list_messages` 的 `Message` 映射及 `return out`；保留 WB-255 的 launch 函数为后续独立顶层函数；移除 WB-276 测试对该缺陷的临时隔离。
- 验证：`db.py` 与测试文件编译通过；`test_message_history_contract`、`test_llm_stream_cleanup`、`test_run_artifact_delivery` 共 11 项通过，覆盖空列表、trace/usage 反序列化、消息顺序及真实 runtime/交付链路。
- commit：本提交。
