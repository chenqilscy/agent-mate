---
id: WB-381
title: ask_user 断流泄漏等待对象且无法恢复待回答检查点
severity: P2
area: backend
status: in-progress
origin: 既有实现
files:
  - backend/agent/runtime.py:1198
  - backend/agent/runtime.py:1380
created: 2026-08-03
---

## 问题
_answers 仅在正常回答后 pop；断流时内存条目残留，问题内容也未持久化为可恢复检查点。

## 触发场景
ask_user 等待中关闭页面或网络断开 → Run paused，但问题无法重新展示/回答，同进程还残留等待对象。

## 影响
P2。长任务交互恢复不完整并造成内存泄漏。

## 建议修法
finally 清理等待对象；把 questions 写入 Run checkpoint；历史/重试 API 返回 pending question，并允许恢复后的 answer 或明确重新执行。

## 验证
断流后 _answers 无残留、Run checkpoint 保留问题；重新打开会话能显示待恢复信息并安全重试。
