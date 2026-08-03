---
id: WB-384
title: 长会话摘要失败静默丢弃旧上下文且无降级状态
severity: P2
area: backend
status: in-progress
origin: 既有实现
files:
  - backend/agent/session_context.py:272
created: 2026-08-03
---

## 问题
摘要异常被静默吞掉，当前轮仍丢弃超预算旧消息；没有事件、Run 元数据或确定性事实提取提示模型/用户进入降级状态。

## 触发场景
摘要模型超时/失败 → 新一轮请求只得到旧 summary 与近期窗口 → 关键约束或任务无提示丢失。

## 影响
P2。长程对话出现难以解释的上下文失忆。

## 建议修法
返回 compaction_degraded 元数据与 SSE 提示；降级时保留受限的确定性关键消息摘录；记录失败原因和下轮重试。

## 验证
注入摘要失败后上下文有有界关键摘录，Run/事件标记 degraded；成功路径成本与 cursor 推进不回归。
