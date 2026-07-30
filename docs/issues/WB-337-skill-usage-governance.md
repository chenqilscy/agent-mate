---
id: WB-337
title: Skill 只有 release 聚合结果，缺少用户侧使用价值与陈旧治理
severity: P2
area: backend
status: open
origin: 既有实现
files:
  - backend/agent/runtime.py:490
  - server/db.py:246
  - server/routers/catalog.py:540
created: 2026-07-31
---

## 问题

现有指标按 release 聚合安装和运行成败，不能区分候选、实际加载、最后使用时间、用户停用和
任务价值，也无法对长期未使用、重复或低成功率 Skill 给出治理建议。

## 触发场景

- 安装大量 Skill 后无法判断哪些从未实际加载。
- 某 Skill 被加入项目但每次任务都无关，运行总数仍不能反映实际价值。
- 清理只能由用户逐个回忆，或冒险自动删除。

## 影响

P2：Skill 库持续膨胀，发现噪音、上下文成本和维护成本增加。

## 建议修法

- 分别记录发现、加载、成功、失败、最后使用、停用和人工评价，保持最小化且不上传正文参数。
- 提供确定性的陈旧/低价值建议；默认只建议停用，不自动删除。
- LLM 合并或生成 umbrella Skill 必须显式开启并走候选发布流程。

## 验证

- 只有实际 `skill_view` 或显式激活才计加载。
- 指标按 owner/release 正确隔离，离线时本地可用且同步失败不影响 Run。
- 治理建议可解释、可忽略、可恢复，不会自动删除用户内容。
