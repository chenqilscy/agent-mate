---
id: WB-116
title: PM 细化之四 计划与度量（片1）—— 工时预估与投入（Manager 侧）
severity: P2
area: fullstack
status: fixed
origin: WB-112f PM 细化四方向「计划与度量」，本片取工时基础件（Manager 侧 Hub+console）
files:
  - hub/db.py
  - hub/routers/work_items.py
  - hub/web/console.html
created: 2026-07-10
---

## 背景

「计划与度量」里 Sprint/燃尽/关键路径体量大或需时序历史；先落最扎实的**工时预估与投入**基础件。仅 Manager 侧（Hub + 控制台）；App 端字段对齐随后续 App 对齐一并做（`_hub_view` 暂不透传两字段，App 忽略无害）。

## 建议修法

- **Hub**（`hub/db.py`）：work_items 加 `estimate_h REAL DEFAULT 0`、`spent_h REAL DEFAULT 0`（CREATE + 幂等补列）；`update_work_item` allowed 集加两字段（`_row_to_work_item` 已 `SELECT *` 自动返回；create 走列默认 0）。
- **Hub 路由**（`hub/routers/work_items.py`）：`UpdateBody` 加 `estimate_h/spent_h: float|None`。
- **控制台**（`hub/web/console.html`）：任务抽屉加 预估工时 / 已投入 两输入，保存进 PATCH；工作量视图每人汇总 Σ预估/Σ投入；概览 tab 加度量卡（Σ预估/Σ投入/剩余）。

## 验证

- 隔离 Hub TestClient/scratch DB：PATCH estimate_h/spent_h 落库并回读；create 默认 0。
- 控制台抽屉填工时保存→回读；工作量/概览汇总数正确；重启 :8100 激活；0 报错。
- 无 App 后端改（Manager-only）。

## 处理记录

2026-07-10 done：
- Hub `hub/db.py`：work_items CREATE 加 `estimate_h/spent_h REAL DEFAULT 0` + 幂等补列迁移 + `update_work_item` allowed 集加两字段（`_row_to_work_item` SELECT * 自动返回、create 走默认 0）。
- Hub 路由 `hub/routers/work_items.py`：`UpdateBody` 加 `estimate_h/spent_h: float|None`。
- 控制台 `hub/web/console.html`：抽屉加 预估工时/已投入 数字输入并进保存 PATCH；`pmViewWorkload` 每人汇总 Σ预估/Σ投入；概览 tab 进度卡加「⏱ 预估Xh·投入Yh·Z%」。
- 验证：隔离 Hub TestClient/scratch DB —— create 默认 0.0、PATCH estimate_h=8/spent_h=3.5 落库回读；重启 :8100 后控制台抽屉填 10/4 保存真落库、工作量视图显工时、概览显「预估 10h·投入 4h·40%」；0 控制台报错。Manager-only（App `_hub_view` 暂不透传两字段，App 忽略无害）。

## 后续

Sprint/迭代、燃尽图（需状态变更时序，可基于 work_item_activity 重建）、关键路径（需任务依赖 WB-114 后续项）另立。App 端字段对齐随 App 对齐一并做。
