---
id: WB-103
title: BuddyWebMgr 专业项目管理 + App 数据打通（总纲 / epic）
severity: P1
area: fullstack
status: in-progress
origin: 用户诉求（2026-07-09）
files:
  - hub/db.py
  - hub/routers/work_items.py
  - hub/routers/milestones.py
  - hub/web/console.html
  - backend/hub_client.py
  - backend/routers/work_items.py
  - backend/storage/db.py
  - src/views/ProjExecView.tsx
created: 2026-07-09
---

## 问题 / 目标

用户诉求（2026-07-09）：**BuddyWebMgr 的项目管理要做成一套「专业的项目管理」，然后 App 端的项目管理与门户的功能 + 数据打通。**

现状（够用但不专业）：
- Hub `work_items` 字段仅 `title / status(todo·doing·paused·done) / source / assignee / description / sort`；门户只有一块 4 列看板。
- 项目已有：成员/角色/邀请、讨论/@、时间线、项目配置（指令/连接器/专家/技能）。
- App↔Hub：WB-091 已做 work_items 双向同步（hub-origin 项目读代理+镜像/写代理，前端零改）。

## 已定决策（本 epic 边界；来自 2026-07-09 与用户确认）

1. **范围 = 完整专业 PM**：在看板基础上补 负责人(从成员选)·优先级·截止日期·标签·子任务/清单·**里程碑/迭代**·**活动流**·**列表视图 + 看板 + 甘特/时间线视图** + 筛选/排序。
2. **App 打通 = 本期就接上**：扩展 WB-091 本地⇄Hub 双向同步覆盖新字段 + 里程碑；App 项目工作台读写同一份数据。**保留 local-first**（离线全功能不破坏，铁律#4）——Hub 为团队协作权威源、本地为执行/离线源，二者镜像同步，而非 App 直连 Hub。
3. **不造假**（铁律#1）：所有 PM 数据真持久化（Hub SQLite + 本地 SQLite）；甘特/活动流来自真实字段/事件，无占位假数据。
4. **视觉**：门户沿用 BuddyWebMgr 既有暗色 token 与 class 体系（`.card/.list-item/.pill/.tabs` 等）；不硬套 App 的浅色 class。列表/抽屉/甘特为新 UI，须与门户风格一致，并避免 WB-099 类 grid 溢出（用 `minmax(0,1fr)`）。

## 数据模型（权威源在 Hub；本地镜像对齐）

`work_items` 增列（`ALTER TABLE ... ADD COLUMN`，带默认值、非破坏）：
- `priority TEXT DEFAULT ''`　'' | low | medium | high | urgent
- `due_date TEXT DEFAULT ''`　ISO `YYYY-MM-DD`
- `start_date TEXT DEFAULT ''`　甘特用
- `labels TEXT DEFAULT '[]'`　JSON 字符串数组
- `parent_id TEXT DEFAULT ''`　自引用 → 子任务/清单
- `milestone_id TEXT DEFAULT ''`　→ milestones.id

新表 `milestones`：`id, project_id, name, description, due_date, status(open|closed), sort, created_at, updated_at`。
新表 `work_item_activity`：`id, project_id, work_item_id, actor, kind(created|status|assignee|field|...), detail, created_at`（逐条真实事件）。

## 分片（子 issue，逐片实现 / 验证 / 提交；开工对应片时再建号，避免与并发会话抢号）

- **WB-104 · P1（backend/hub）** ✅：Hub 数据模型 + 迁移（`work_items` 新列 + `milestones` + `work_item_activity` 表；`db.py` CRUD 扩展）。
- **WB-105 · P1（hub）** ✅：Hub API —— `work_items` CRUD 全字段 + 子任务(parent_id) + `milestones` CRUD + 活动 feed 端点。assignee/priority **宽松校验**（保护同步；成员约束交给门户 UI 下拉）。
- **WB-106 · P1（frontend·console）**：BuddyWebMgr 任务专业化 —— 列表视图 + 看板增强(负责人/优先级/截止/标签/子任务计数) + 任务详情抽屉(全字段+子任务+活动) + 筛选/排序。
- **WB-107 · P2（frontend·console）**：里程碑/迭代面板 + 甘特/时间线视图 + 活动流。
- **WB-108 · P1（fullstack）** ✅：App↔Hub 打通 —— 扩展 WB-091 同步覆盖新字段/里程碑；本地 backend `work_items` 模型对齐；App 项目工作台任务 UI 接优先级/标签/里程碑。**108a 后端 + 108b 前端均 ✅**（冒烟 25+12+HTTP E2E、tsc/build、明暗双主题 CDP 实截 全过）。子任务 UI/甘特随门户期（WB-106/107）。

> 用户 2026-07-09 决策：先做 App 端打通（WB-108），门户 UI 期（WB-106/107，重写 console.html）等并发会话落地后再做，避免同文件写冲突。

## 影响

P1：把门户项目管理从「演示级看板」升级为可用的团队 PM，并让 App 与之共享数据——是「多人协同」主线的关键能力。跨 5 层改动，须逐片非破坏、保证离线/未登录纯本地全功能不受影响。

## 验证（epic 级）

- 每片按其子 issue 「验证」核对；`tsc` / `vite build` / `py_compile` 全过。
- Hub 隔离实例（:8100，验收账号 alice/alice123）建项目 → 建里程碑 → 建任务(带负责人/优先级/截止/标签/子任务) → 列表/看板/甘特三视图正确 → 活动流有真实事件。
- App 端登录 Hub、打开该项目工作台：任务与门户**双向可见**（门户建的任务 App 看得到、App 改状态门户看得到），新字段同步。
- 断网/未登录：App 纯本地 work_items 全功能照常（离线兜底不破坏）。
- 明暗（门户仅暗色）/窄视口过一遍；各 grid 不横向溢出。
