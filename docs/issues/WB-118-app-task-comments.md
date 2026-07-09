---
id: WB-118
title: App 端 PM 对齐 Manager 片2 —— 任务级评论（App 后端代理 + 任务详情评论区）
severity: P2
area: fullstack
status: fixed
origin: WB-117 App 对齐 epic 之片2；复用 WB-115 的 Hub 任务评论端点
files:
  - backend/hub_client.py
  - backend/routers/hub.py
  - src/lib/api.ts
  - src/components/project/ProjectWork.tsx
created: 2026-07-10
---

## 背景

WB-115 已在 Hub + Manager 控制台做了任务级评论（`GET/POST /projects/{pid}/work-items/{wid}/comments`）。
App 只有项目级评论（讨论 tab，`HubCommentsPanel` 经 `/hub/projects/{pid}/comments` 代理）。本片把**任务级评论**搬到 App 任务详情。
评论是协作实体、Hub 权威、无本地态——仅 hub-origin/已连 Hub 项目可用（与项目级评论一致，符合数据分层规范）。

## 建议修法

- **App 后端**：`hub_client.py` 加 `list_item_comments/post_item_comment`（GET/POST Hub `/projects/{pid}/work-items/{wid}/comments`，guarded）；`routers/hub.py` 加 `GET/POST /hub/projects/{pid}/work-items/{wid}/comments`（同项目级模式，Hub 未接返回 `{hub:false,comments:[]}` / 报错）。
- **App 前端**：`api.ts` 加 `hubItemComments/hubPostItemComment`；`ProjectWork.tsx` 任务详情弹窗加「评论」区（载+发，@提及沿用；Hub 未接则提示"连接 Hub 后可评论"）。

## 验证

- App 后端 HTTP：hub-origin 项目 POST/GET 任务评论经代理落 Hub、只挂该任务；未接 Hub 返回空/报错不崩。
- tsc 过；App :5173 任务详情发/载任务评论（连 Hub 账号）；0 报错。

## 处理记录

2026-07-10 done：
- App 后端：`hub_client.py` 加 `list_item_comments/post_item_comment`（guarded 转发 Hub `work-items/{wid}/comments`）；`routers/hub.py` 加 `GET/POST /hub/projects/{pid}/work-items/{wid}/comments`（同项目级模式，未接 Hub → `{hub:false,comments:[]}` / 400，不崩）。
- App 前端：`api.ts` 加 `hubItemComments/hubPostItemComment`（自动带 wb.token=Hub token）；`ProjectWork.tsx` 任务详情弹窗加「评论」区（挂载载评论 + 输入框回车/按钮发，复用 HubCommentsPanel 的 `msg-row/np-input/btn-dark` 类，未接 Hub 显 `pj-empty` 引导）。
- 验证：tsc 过、backend py_compile 过；重启 :8000 后 `/api/hub/.../work-items/.../comments` 返回 `{hub:true,comments:[]}`（graceful）；App hub_client 直连 Hub :8100 `post_item_comment`/`list_item_comments` 往返成功(count 1)；App :5173 任务详情弹窗见「评论」区(输入框+空态)；0 控制台报错。
- 注：评论 Hub 权威、仅 hub-origin/已连 Hub 项目可发（本地项目任务的 wid 不在 Hub → 发送 404 提示失败，与项目级 讨论 一致）。
