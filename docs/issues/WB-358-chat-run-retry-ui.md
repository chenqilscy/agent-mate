---
id: WB-358
title: App 未暴露失败和暂停 Run 的重试恢复入口
severity: P1
area: frontend
status: open
origin: 既有实现
files:
  - src/stores/chatStore.ts:41
  - src/lib/sse.ts:28
  - backend/routers/chat.py:72
created: 2026-08-03
---

## 问题

后端和 SSE 客户端支持 `retry_of`，但聊天 store 与消息界面没有重试动作，用户无法恢复失败、取消或断连暂停的 Run。

## 触发场景

运行中断或失败后打开会话，只能重新输入，无法建立可审计的 Run 重试关系。

## 影响

P1。长任务恢复闭环未完成。

## 建议修法

为符合状态的 assistant 消息显示重试入口，复用原用户消息和 loadout/refs 边界，将原 `runId` 作为 `retryOf` 发送。

## 验证

- failed/cancelled/paused 可重试，completed 不显示；
- 新 Run 保存 `retry_of`；
- TypeScript、回归和明暗主题浏览器验证通过。
