---
id: WB-035
title: 自动化产出的会话除「上次运行」外全部不可达（无运行历史入口）
severity: P2
area: frontend
status: fixed
origin: 既有实现
files:
  - src/components/layout/Sidebar.tsx:65
  - src/views/AutomationView.tsx:37
  - backend/agent/scheduler.py:52
  - backend/storage/db.py:196
created: 2026-07-06
---

## 问题

自动化到点/立即运行都会产出一条**真实持久化**的会话（`kind='automation'`，有真实消息），
但用户几乎无法找到这些会话：

- 侧栏「任务」列表**显式**过滤掉自动化会话（[`Sidebar.tsx:65`](../../src/components/layout/Sidebar.tsx#L65)
  `s.kind !== 'automation'`）—— 这是**刻意设计**，避免频繁计划把任务列表刷屏，不改。
- 自动化页只提供「打开上次运行」（[`AutomationView.tsx:37`](../../src/views/AutomationView.tsx#L37)
  `openRun` → `openSession(a.last_session_id)`），因为后端每条自动化只记 `last_session_id`
  （[`scheduler.py:90`](../../backend/agent/scheduler.py#L90) / `db.mark_automation_run`）。
- 于是**只有最近一次**运行能打开；更早的运行会话真实躺在库里却**无处可达**——既不进侧栏，
  卡片也不追踪，成了孤儿会话（用户为其付了真实 LLM 调用）。

根因是数据模型缺一条**反向关联**：`sessions` 行不知道自己属于哪条自动化，只能靠自动化单向指向
最近一次（`last_session_id`）。带项目的自动化其会话反而会出现在「空间」对应项目下
（`sessionsOf` 未过滤 kind），但经模态框创建的自动化默认无项目，故普遍受影响。

附带：[`models.py:47`](../../backend/storage/models.py#L47) 的 `Session.kind` 注释写的是
`"chat" | "assistant" | "projexec"`，漏了实际存在的 `"automation"`。

## 触发场景

1. 「自动化」页对某任务点「⋯ → 立即运行」两次（或等其按计划触发多次）。
2. 每次都真产出一条会话（可用 SQLite 核实 `sessions` 表新增行）。
3. 卡片「打开上次运行」只能打开**最后**那条；此前几条无任何入口可达。
4. 侧栏「任务」也看不到它们（设计如此）。

## 影响

P2：功能实际是好的（会话真产出、有真实内容），但除最近一次外的历史运行结果**不可回看**，
用户会误以为「执行完的会话丢了」。不涉及数据丢失或安全，只是可达性缺口。

## 建议修法

给会话补一条**反向关联**并在自动化页开一个**运行历史**入口，保留「侧栏不刷屏」的设计：

- 后端：`sessions` 表增 `automation_id TEXT`（`_migrate_columns` 幂等补列 + 索引；老库把已知
  `last_session_id` 回填一次，让升级后至少能看到最近一次）。`db.create_session` 增
  `automation_id` 参数；`scheduler.py` 两处建会话时传 `automation_id=auto.id`。
- 新增 `db.list_automation_runs(automation_id, owner_id)` + 路由 `GET /api/automations/{id}/runs`
  （owner-scoped，按 `created_at` 倒序，返回带 `ago` 的 session 视图）。
- 前端：`api.listAutomationRuns`；`AutomationView` 卡片菜单加「运行历史」，点开用**既有** `Popover`
  + `.pop-item.hist-item` / `.pop-item.pop-empty` 模式（对话页「历史提问」已在用）列出各次运行，
  逐条点开 → `openSession` + 切到 chat。**不新增 CSS、不改侧栏过滤。**
- 顺带把 `Session.kind` 注释补上 `"automation"`。

非目标：不把自动化会话塞回侧栏；不做逐次运行的 ok/error 状态（当前只在自动化级记 `last_status`）。

## 验证

- `npx tsc --noEmit` 通过；`py_compile` 改动的后端文件通过。
- 后端手测：对一条自动化 `POST /run` 两次 → `GET /automations/{id}/runs` 返回 2 条，倒序、owner-scoped。
- 浏览器实测：卡片「⋯ → 运行历史」列出多条运行，点其一 → 打开对应会话正文；明暗双主题下
  Popover 配色正常（复用既有 class）。
- 回归：普通对话/项目执行会话仍照常出现在侧栏；老库启动不报错、最近一次运行被回填进历史。

## 处理记录（2026-07-06）

交接时代码已完整、静态自洽、编译通过但未实测（原「交接备注·未关闭」）；本次随 WB-036 一并**补做运行时验证并关闭**。

已改动：
- 后端（全部完成）：
  - `backend/storage/db.py`：`sessions` 表加 `automation_id`（CREATE TABLE + `_migrate_columns`
    幂等补列 + `idx_sessions_automation` 索引 + 老库用 `last_session_id` 回填最近一次，幂等）；
    `create_session` 加 `automation_id` 参数（仅入表，不上 `Session` dataclass）；新增
    `list_automation_runs(automation_id, owner_id)`（owner-scoped，`created_at` 倒序）。
  - `backend/agent/scheduler.py`：`_fire_guarded` 与 `run_now` 两处建会话都传 `automation_id=auto.id`。
  - `backend/routers/automations.py`：新增 `GET /api/automations/{auto_id}/runs`（owner-scoped，
    每条附 `ago`=`_ago(created_at)`）。
  - `backend/storage/models.py:47`：`Session.kind` 注释补 `"automation"`。
- 前端（全部完成）：
  - `src/lib/api.ts`：`listAutomationRuns(id)` → `GET /automations/{id}/runs`。
  - `src/views/AutomationView.tsx`：卡片菜单加「运行历史」项；新增 `histId`/`histRuns` state 与
    `openHistory`（先拉取再开，避免闪空态）/`openRunSession`（`openSession`+切 chat）；复用既有
    `Popover` + `.pop-h` + `.pop-item.hist-item` / `.pop-item.pop-empty` 渲染，未新增 CSS、未改侧栏过滤。

验证（本次补做，均通过）：
- `npx tsc --noEmit` 无报错；`py_compile db.py/scheduler.py/automations.py/models.py` OK。
- 后端 `GET /api/automations/{id}/runs`：两条已运行的自动化各返回 **2 条**、`created_at` **倒序**（校验通过）；
  路由 owner-scoped（`current_user` + `list_automation_runs` 的 `WHERE owner_id=?` + 非本人 automation 404，
  沿用 WB-013 模式）。
- 浏览器实测：卡片「⋯ → 运行历史」弹出「运行历史（2）」并列出两次运行（「10分钟前 / 51分钟前」，倒序），
  复用 `.pop-item.hist-item`；点条目可 `openSession` 跳会话正文。同一 `api.listAutomationRuns` 也被 WB-036
  编辑器右侧「运行历史」侧栏消费，明暗双主题下 `.pop` 系配色正常（与 WB-036 一并核过）。
- 回归：普通对话/项目会话仍照常进侧栏；侧栏对 `kind==='automation'` 的过滤未改（设计如此）。

注意：本 issue 与 WB-034（视图级轮询）并发改同一 `AutomationView.tsx`，二者均已落地、互不冲突
（本 issue 只加菜单项+历史 Popover，未触碰轮询 effect 与 `runNow`）。WB-036 的全屏编辑器又在此基础上叠加，
二者同源、本次同一提交落地。

- commit：（随 WB-036 同一提交）
