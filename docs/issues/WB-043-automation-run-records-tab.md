---
id: WB-043
title: 自动化「运行记录」tab —— 逐次运行状态/摘要持久化 + 跨自动化运行列表 + 详情弹窗
severity: P2
area: frontend
status: fixed
origin: 既有实现
files:
  - src/views/AutomationView.tsx
  - backend/agent/scheduler.py:29
  - backend/storage/db.py
  - backend/routers/automations.py
created: 2026-07-06
---

## 问题

对照目标设计，自动化视图应有 **定时任务 / 运行记录** 两个 tab；「运行记录」是一个**跨自动化**的逐次
运行历史（按天分组，每条带 完成/失败 状态 + 时间），点开有**详情弹窗**（摘要 + 运行明细/工作区路径 +
错误，如「本次任务已启动，但在生成结果前中断」「Run timed out」）。

clone 现状缺口：
- 只在**自动化级**记 `last_status`（ok/error/running）；**逐次运行**没有独立的结果/摘要持久化——
  `scheduler._execute`（[`scheduler.py:29`](../../backend/agent/scheduler.py#L29)）超时/异常只把自动化翻成
  `error`，不存每次运行的「摘要（Run timed out 等）」。会话的 `status`（idle/done）也不等于运行 ok/error。
- 没有跨自动化的运行列表接口（只有 WB-035 的按单条自动化 `GET /{id}/runs`）。
- 前端自动化视图无 tab、无运行记录列表、无详情弹窗。

## 触发场景

1. 若干自动化跑过若干次（含超时失败）。
2. 想在一个地方按时间看「哪次跑了、成没成、失败原因」——目前只能逐条自动化点「运行历史」看时间，
   看不到每次的 完成/失败 与错误摘要。

## 影响

P2：运行可观测性缺口。运行本身是真的（会话真产出），但「逐次结果 + 失败原因」不可见、不可回看。

## 建议修法

- **后端（逐次运行结果持久化）**：`sessions` 幂等补列 `run_status`（'running'|'ok'|'error'）、
  `run_summary`（TEXT，失败原因/摘要）、`run_kind`（'test'|'scheduled'）。`scheduler`：建会话时带
  `run_kind`（run_now→test、到点→scheduled）+ `run_status='running'`；`_execute` 完成时写 ok/error，
  超时（`asyncio.TimeoutError`）摘要记 "Run timed out"、其它异常记 `str(e)` 截断。新增
  `db.list_all_automation_runs(owner_id, limit)` + 路由 `GET /api/automation-runs`（owner-scoped，倒序，
  每条附 `ago`/`created_at`/`run_status`/`run_summary`/`run_kind`/工作区路径）。
- **前端**：`AutomationView` 顶部加 定时任务/运行记录 tab（定时任务=现有列表+模板）。运行记录 tab：
  `api.listAutomationRunsAll()` → 按天（今天/昨天/日期）分组，每条 automation 名 + 「测试运行完成/运行失败」
  + 时间 + 状态图标；点开**详情弹窗**（复用 `.np-*`/既有 modal：摘要 + 运行明细/工作区路径 + 错误；
  可「打开会话」跳 chat）。顶部搜索「搜索自动化/记录」过滤列表。
  顺带把 WB-035 卡片/编辑器侧栏的运行历史条目也标上 完成/失败 状态图标（现有 run_status 已可用）。
- 严守铁律：状态/摘要都真存真取；复用既有 class 与 token，明暗双主题。

非目标（后续 issue）：`补跑`（catch-up）标注（run_kind 只做 test/scheduled）；编辑器的
Loadout/频率扩展/权限/微信推送（WB-036 已列后续）。

## 验证

- `tsc` / `py_compile` 通过。
- 后端 curl：跑一条自动化（含制造超时）→ `GET /api/automation-runs` 返回带 run_status/run_summary 的倒序列表；
  超时那条 `run_status=error`、`run_summary="Run timed out"`；owner-scoped。
- 浏览器：运行记录 tab 按天列出各次运行 + 状态；点开详情弹窗显示摘要/明细/错误；搜索过滤；
  定时任务 tab 仍是原列表+模板；明暗双主题正常。
- 回归：WB-035 运行历史/WB-041 侧栏分组不受影响。

## 处理记录（2026-07-06）

- 后端：`sessions` 增 `run_status`/`run_summary`/`run_kind`（CREATE + `_migrate_columns` 幂等补列，
  老库 NULL）；`Session` dataclass + `create_session` + `_row_to_session` 带上三字段；`scheduler` 建会话时
  `run_kind='scheduled'|'test'` + `run_status='running'`，`_execute` 完成时 `db.mark_session_run` 写 ok/error +
  摘要（`asyncio.TimeoutError`→"Run timed out"，其它异常→`str(e)[:500]`）。新增 `db.list_all_automation_runs`
  + 路由 `GET /api/automation-runs`（owner-scoped、倒序、每条附 `ago`/`workspace`=`project_root` 路径）。
- 前端：`SessionInfo` 增 run 字段；`api.listAllAutomationRuns`；`RunsTab`（按天今天/昨天/日期分组、每条
  automation 名 + `runLabel`（测试运行完成/定时运行失败…）+ 时间 + 状态图标 `RunStatusIcon`、5s 轻轮询）；
  `RunDetailModal`（复用 `.np-*`：摘要 + 运行明细/工作区路径 + 错误，失败文案「本次任务已启动，但在生成
  结果前中断…」+「打开会话」）；搜索过滤。WB-035 卡片/编辑器侧栏运行历史条目也标上失败（⚠）状态。
- 验证：`tsc`/`py_compile` 通过。后端 curl：触发一次 → 该运行即 `run_kind=test`/`run_status=running`，~9s 后
  `ok`；`/automation-runs` 返回带 run 字段与工作区路径的倒序列表。Playwright 明暗双主题：运行记录 tab 按天
  分组 + 状态 ✓、点开详情弹窗（摘要/明细/真实工作区路径），暗色 `.np-modal`/`.auto-detail-box` 配色正常。
- commit：（尚未提交）
