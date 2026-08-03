---
id: WB-385
title: 会话任务列表仅为文本 trace 无稳定状态和恢复能力
severity: P2
area: fullstack
status: in-progress
origin: 既有实现
files:
  - backend/agent/tools.py:448
  - backend/agent/events.py:50
  - src/stores/chatStore.ts:1
created: 2026-08-03
---

## 问题
update_plan 仅接受字符串数组并产生 todo 文本 trace，没有稳定 ID、状态、顺序、依赖或增量版本。

## 触发场景
Agent 更新多步计划、页面刷新或 Run 重试 → 只能显示若干历史文本，无法知道当前项、完成项或精确恢复。

## 影响
P2。长任务列表不是真实状态，项目工作项与会话计划无法可靠衔接。

## 建议修法
建立持久 RunPlanItem 模型和 snapshot/patch SSE；兼容旧字符串输入；支持 pending/in_progress/completed/blocked 与提升为 WorkItem。

## 验证
计划状态持久化并可历史恢复；重复更新幂等；刷新和重试不丢状态；前后端契约测试通过。
