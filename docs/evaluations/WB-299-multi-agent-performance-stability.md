# WB-299 多 Agent 性能与稳定性验收

验收时间：2026-07-23（Asia/Shanghai）

门禁：`multi-agent-admission-v2`

模型：`@zhipu:glm-4.7-flash`

## 改进范围

- 默认专家团由 2 个 specialist 提升为 3 个真实并行 specialist，主编保持独立 Run；
- 修复同步 FastAPI 路由在线程池调用 `asyncio.create_task` 导致真实创建接口 500；
- 并行首轮只执行一次，供应商 429/5xx 分支改为顺序恢复，避免同步退避重试风暴；
- specialist 输出上限 2200 tokens，reviewer 为 2800 tokens；每次失败尝试从节点剩余预算扣除，
  后续恢复按编排实时剩余预算分配；
- 空正文不能标记 completed；取消等待父子任务并原子收敛全部活动节点/尝试；
- 编排详情批量加载 attempts，前端由 2 秒全量 GET 轮询改为带心跳、自动重连的 SSE 权威快照。

## 真实模型结果

| 场景 | 单 Agent 质量 | 单 Agent token | 单 Agent 耗时 | 多 Agent 质量 | 多 Agent token | 多 Agent 耗时 | 峰值并行 | token 比 | 结果 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 事故复盘 | 14/16 | 2,908 | 61.229s | 16/16 | 13,367 | 64.142s | 3 | 4.597× | 通过 |
| 产品策略 | 18/18 | 3,318 | 26.306s | 18/18 | 12,763 | 72.764s | 3 | 3.847× | 通过 |

两条场景均满足质量门槛、真实完成、峰值并行至少 3、总 token 不超过单 Agent 5 倍。事故复盘相对
单 Agent 多命中 2 项；产品策略在单 Agent 已满分的天花板场景保持 18/18。

## 稳定性证据

- 真实 `POST /api/orchestrations` 返回 202，并创建 `specialist_1..3` 三个独立 Session/Run；
- `/api/orchestrations/{id}/events` 连续推送运行、尝试、429、token 与节点终态；
- 真实执行中取消后，响应快照为父任务 `cancelled`，已完成成员保持 completed，活动 reviewer 收敛为
  cancelled，没有永久 running 节点；
- 供应商限流时首轮保持 3 路并行，失败分支随后顺序恢复；最终两场景所有 specialist 与 reviewer 均完成；
- 8 个多 Agent 定向回归覆盖事件循环启动、3 成员路由、累计预算、固定查询数、取消收敛和进程恢复；
  全量 147 个后端回归、TypeScript 类型检查与 Vite 生产构建通过。
- 隔离 SQLite 基准使用 10 节点 × 每节点 3 次尝试、连续读取 1000 次：每次权威快照固定 3 条 SELECT，
  attempts 固定 1 条批量 SELECT，平均 0.1593ms、P95 0.2102ms，门禁通过。

## 复现

```powershell
$env:PYTHONPATH='backend'
backend\.venv\Scripts\python.exe backend\tests\evaluation\run_multi_agent_benchmark.py `
  --output scratchpad\wb-299-multi-agent-benchmark.json
backend\.venv\Scripts\python.exe backend\tests\evaluation\run_orchestration_store_benchmark.py `
  --output scratchpad\wb-299-orchestration-store-benchmark.json
```

报告包含完整模型输出、逐项质量命中、节点/尝试 Run、token、耗时和峰值并行；原始 JSON 放在被 Git
忽略的 `scratchpad`，避免把大段模型输出作为产品源码提交。
