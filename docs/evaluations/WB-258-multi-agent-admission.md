# WB-258 多专家编排准入证据

评测时间：2026-07-21（Asia/Shanghai）

门禁：`multi-agent-admission-v1`

模型：`@zhipu:glm-4.7-flash`

## 准入规则

- 单专家基线低于 0.90 时，多专家质量至少提升 0.10 且多命中 2 项；
- 单专家基线达到 0.90 时采用天花板规则：多专家至少 0.98 且不得退步；
- 多专家总 token 不得超过单专家的 5 倍；
- 两边都必须真实完成，失败或零 token 结果不能通过。

## 结果

| 场景 | 单专家质量 | 单专家 token | 单专家耗时 | 多专家质量 | 多专家 token | 多专家耗时 | token 比 | 结果 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 事故复盘 | 16/16 | 2,978 | 50.002s | 16/16 | 11,984 | 86.602s | 4.024× | 通过 |
| 产品策略 | 18/18 | 3,475 | 24.289s | 18/18 | 11,942 | 310.456s | 3.437× | 通过 |

两条基线均超过 0.90，因此按天花板规则验收；多专家均为满分且未退步。耗时是模型执行耗时，续跑只重做供应商瞬态失败的分支，不包含等待人工检查的时间。

## 多专家 Run 追溯

### 事故复盘

- 资料检索员：Run `e6064e29-5b01-4c84-bd54-40e0c02118fd`，3,262 tokens，1 次尝试；
- 数据分析师：Run `8a529c2e-5c2a-4ed9-b729-94824d03247a`，3,166 tokens，第 3 次尝试完成；前两次 429 作为失败 Run 保留；
- 研究主编：Run `274c5545-2327-41d5-96bb-167046991243`，5,556 tokens，1 次尝试。

### 产品策略

- 需求分析师：Run `d85bf629-4ddd-4e72-94bb-acc9e1ffb94b`，3,520 tokens，第 2 次尝试完成；首次 500 保留；
- 用户研究员：Run `52b5031b-7c32-431c-831a-c4d66e2d9dd0`，3,190 tokens，第 4 次尝试完成；前三次 429 保留；
- 产品总监：Run `596235f3-3d2e-4aa1-a3d4-535296cf81a8`，5,232 tokens，1 次尝试。

## 复现

```powershell
$env:PYTHONPATH='backend'
backend\.venv\Scripts\python.exe backend\tests\evaluation\run_multi_agent_benchmark.py --output scratchpad\wb-258-multi-agent-benchmark.json
# 若只有供应商瞬态失败，保留已完成分支并续跑：
backend\.venv\Scripts\python.exe backend\tests\evaluation\run_multi_agent_benchmark.py --output scratchpad\wb-258-multi-agent-benchmark.json --resume
```

评测报告包含完整输出、逐项命中、节点状态、每次尝试的 Run ID、错误和 token；报告位于被 Git 忽略的 `scratchpad`，避免把大段模型输出作为产品源码提交。上述摘要保留准入所需的稳定证据。
