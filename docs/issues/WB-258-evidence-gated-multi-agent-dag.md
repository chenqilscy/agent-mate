---
id: WB-258
title: 专家团仍是多 persona 同时注入，缺少独立 Run、DAG、审稿预算和对照评测
severity: P1
area: fullstack
status: open
origin: WB-239 R5
files:
  - backend/agent/orchestrator.py:1
  - backend/routers/orchestrations.py:1
  - backend/storage/orchestration_store.py:1
  - backend/tests/evaluation:1
created: 2026-07-21
parent: WB-239
---

## 问题

“专家团”当前只把多个专家人格合并进同一个 system prompt，所有成员共享一条 Session/上下文和一次 Run；
没有团长拆解、依赖 DAG、独立成员执行、并行、审稿汇总、总预算、失败边界或相对单 Agent 的评测证据。

## 触发场景

用户选择深度研究团队或产品战略团队后，界面看似挂载多个角色，但运行时仍是单模型单上下文。成员无法独立
检索/分析，某一步失败不能单独重试，最终答案也无法指出来自哪个成员 Run；增加 token 后是否真的提高质量未知。

## 影响

P1：把当前展示称为多 Agent 会误导用户，R5“可编排”退出条件不成立；盲目并行还会放大成本和外部写风险。

## 建议修法

- 团长先基于目标和可用成员生成受 schema 约束的 DAG；每个节点使用独立 Session/Run/上下文和稳定身份；
- 调度器按依赖并行，只读为默认，限制最大节点/并发/总 token/超时并支持取消与单节点失败可追溯；
- 审稿节点读取成员产出，给出冲突、缺口和最终综合结论，最终 Markdown 作为可验收 Artifact；
- API 提供发起、状态、节点 Run、成本、失败和取消；幂等重试不得重复创建编排；
- 建立至少两个目标场景的单 Agent 对照评测，只有质量收益达到门槛且成本边界清楚才允许标记完成。

## 验证

- DAG 拒绝环、未知依赖和越界预算；依赖满足后并行，节点各自关联真实 Session/Run；
- 一个节点失败时依赖节点明确跳过或由审稿人降级说明，不伪装成功；取消能停止活动 Run；
- 总 token、并发、节点数和输出注入均有硬上限，默认不开放外部写；
- 最终 Artifact 能追溯成员 Run/角色/成本并可下载验收；
- 两个真实 LLM 场景相对同模型单 Agent 达到预设质量提升门槛，记录质量、token、耗时和失败证据。
