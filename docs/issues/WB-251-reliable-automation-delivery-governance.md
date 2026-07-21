---
id: WB-251
title: 自动化缺少真实失败判定、持久幂等重试、DLQ、成本上限与结果投递
severity: P1
area: backend
status: fixed
origin: WB-239 R2
files:
  - backend/agent/scheduler.py:1
  - backend/routers/automations.py:1
  - backend/storage/db.py:312
  - backend/storage/models.py:235
created: 2026-07-21
---

## 问题

自动化调度器只要 `run_chat` 的异步生成器正常结束就记为 `ok`，但 LLM/工具错误会在 runtime 内转成 SSE 并
返回，导致真实失败被误报成功。`_running` 只是进程内集合，重启或多进程没有持久 fire key；没有按策略重试、
死信、成本上限和结果投递，失败只能靠用户进入运行记录偶然发现。

## 触发场景

定时任务遇到 LLM 401、超时或工具错误，Run 已保存 `failed`，自动化 session/last_status 却可能显示 `ok`；
应用在调度点附近重启可能重复执行。连续失败既不重试/入 DLQ，也不发 App 通知，token 消耗没有上限。

## 影响

P1：无人值守任务不能长期托管，外部写可能重复，失败不可见且成本不可控；R2“无重复写、可告警、可重跑、
可追溯”的退出条件无法成立。

## 建议修法

- 新增持久 `automation_fires`，以 automation + planned_at/manual key 唯一标识一次逻辑触发，记录 attempt、
  Run/session、状态、错误、token、下一重试、投递和审计；
- 调度器以真实 Run 终态判定成功/失败，按固定上限和指数退避重试，每次重试关联 `retry_of`；
- 超过次数/成本/超时进入 DLQ，可通过 owner-scoped API 幂等重跑或忽略；
- 自动化配置增加 timeout、max_attempts、backoff、max_total_tokens、并发策略和 App 通知投递；
- 失败/恢复/成功按配置写真实消息中心通知，项目任务同时写允许上云的时间线摘要。

## 验证

- runtime 内部 LLM error 被调度器识别为失败，session/Run/fire/automation 状态一致；
- 同一 fire key 并发/重启只执行一次；失败按策略产生关联重试，最终进入 DLQ；
- token 或时间超限停止后续重试并可追溯，owner 可重跑 DLQ 且重复请求不产生重复 fire；
- 成功/失败通知只投递一次，不含 prompt、secret 或文件正文；
- 连续调度回归、真 API 和生产构建通过。

## 处理记录

- 2026-07-21：新增持久 `automation_fires`、稳定 fire key、原子 claim 与进程中断恢复；调度器以真实
  Run 终态判定结果，失败按指数退避生成 `retry_of` 关联，耗尽后进入 owner-scoped DLQ。
- 2026-07-21：自动化增加超时、最大尝试、退避、token 上限、通知和并发策略；runtime 在下一次工具执行前
  以累计 token 停止并留下 `token_budget_exceeded` Run 证据。失败/恢复通知原子去重且不带 prompt/正文。
- 2026-07-21：增加异常队列 UI（重跑/忽略）和可靠性配置；68 条 backend regression、TypeScript、Vite
  production build 通过。隔离真 API 调用在 LLM error 正常结束 SSE 的情况下仍得到
  `fire=dead_letter / session=error / run=failed`，证明不再误报成功；临时数据库、工作区与进程已清理。
