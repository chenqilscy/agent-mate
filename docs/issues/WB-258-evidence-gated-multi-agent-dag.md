---
id: WB-258
title: 专家团仍是多 persona 同时注入，缺少独立 Run、DAG、审稿预算和对照评测
severity: P1
area: fullstack
status: fixed
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

- 先按目录中的稳定团队角色生成最小互补 DAG，并保留 schema/依赖校验作为未来自适应路由的准入边界；每个节点使用独立 Session/Run/上下文和稳定身份；
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

## 处理记录（2026-07-21）

- 新增持久化编排、节点和尝试表；幂等发起、进程恢复、取消、节点成本汇总和每次尝试的 Run 均可追溯。
- 新增确定性目录角色路由与受校验 DAG。早期真实评测表明由 LLM 自适应拆解会额外消耗一次调用且可能生成未知 slug，因此当前生产默认选择两名互补专家并行、目录 lead 审稿；`validate_plan` 继续拒绝未知专家、未知依赖和环，为未来自适应模式保留硬边界。
- 每个节点使用独立 Session/Run，瞬态 429/5xx 按尝试退避；并行限流后顺序恢复，reviewer 也有独立恢复轮次，所有失败尝试与 token 成本保留。
- 最终审稿输出写入 Markdown Artifact，并附角色、Run、尝试与 token 追溯；API/UI 提供发起、轮询、取消、节点状态、成本和最终输出。
- 真实模型准入使用 `@zhipu:glm-4.7-flash` 的事故复盘与产品策略两个冻结场景。单/多专家均为 16/16、18/18；多专家 token 比为 4.024×、3.437×，低于 5×上限。完整摘要见 `docs/evaluations/WB-258-multi-agent-admission.md`。
- 验证通过：86 个后端回归、`npx tsc --noEmit`、`npx vite build`，以及专家团页面明暗主题和 860px 窄宽浏览器验收。
