---
id: WB-115
title: PM 细化之三 协作联动 —— 按负责人工作量视图（前端）+ 任务级评论（Hub 后端 + 控制台）
severity: P2
area: fullstack
status: fixed
origin: WB-112f PM 细化四方向「协作联动」
files:
  - hub/web/console.html
  - hub/db.py
  - hub/routers/comments.py
created: 2026-07-10
---

## 背景

PM 细化四方向之④。本片两件：**工作量视图**（纯前端，按负责人聚合现有任务）+ **任务级评论**（复用 Hub 项目级 comments 延伸到 work_item）。

## 建议修法

### A. 按负责人工作量视图（纯前端，`hub/web/console.html`）
- 视图切换器加第 4 项「负载」。`pmViewWorkload`：按 assignee（+未指派）聚合当前筛选后的根任务，每人一卡：总数 / 各状态计数 / 完成率进度 / 逾期数（红）+ 状态分布堆叠条。

### B. 任务级评论（Hub 后端 + 控制台）
- Hub `comments` 表加 `work_item_id TEXT DEFAULT ''`（幂等补列）；`work_item_id` 空 = 项目级（现状不变）。
- Hub 路由 `hub/routers/comments.py`：加 `GET/POST /projects/{pid}/work-items/{wid}/comments`（access-gated；复用现有 comment 落库/校验，按 wid 过滤/写入）。
- 控制台任务抽屉 `pmOpenTask` 加「评论」区：载 + 发（@提及沿用现有）。
- 数据分层规范：任务评论属协作实体 → Hub 权威（更新总表一行）。

## 验证

- 工作量视图：隔离/本机 :8100 CDP，按负责人聚合数与实际一致、逾期标红、堆叠条正确；0 报错。
- 任务评论：隔离 Hub TestClient/scratch DB 断言任务级评论只挂该任务、项目级不受影响；控制台抽屉发/载评论真落库。
- Hub 后端改 → 重启 :8100 激活。App 端（React 任务评论）另作后续。

## 处理记录

2026-07-10：
- **A 工作量视图 done**（`hub/web/console.html`）：视图切换器加「负载」；`pmViewWorkload` 按 assignee(+未指派) 聚合当前筛选根任务，每人一卡（头像+名+总数 pill+状态分布堆叠条+待办/进行/完成·完成率+逾期红）。实测本机 :8100：demopm 1 项·100%、未指派 7 项·完成2/29%·逾期1，堆叠条正确，0 报错。纯前端、无需重启。
- **B 任务评论 done**：Hub `comments` 加 `work_item_id`（CREATE + 幂等补列，''=项目级）；`db.add_comment/list_comments` 带 work_item_id 分流；`hub/routers/comments.py` 抽 `_post_comment` 共享（含 @提及通知），加 `GET/POST /projects/{pid}/work-items/{wid}/comments`（`_require_item` 校验任务属项目）；控制台抽屉 `pmOpenTask` 加「评论」区（读+发，所有成员可参与，置于 ro 早退之前）。
  - 验证：隔离 Hub TestClient/scratch DB —— 任务评论只挂该任务(count=1)、项目级评论不混入、@bob2 得 mention 通知、坏 wid→404；重启 :8100 后控制台抽屉发「…@demopm」即时渲染 + API 确认为任务级评论；0 控制台报错。
  - 运行中 :8100 已重启激活（迁移补列 + 新端点）。App 端 React 任务评论另作后续。
