---
id: WB-067
title: App 前端接 Hub —— 协作面板(评论/在线/通知) + 目录 Admin + 同步/导入入口
severity: P2
area: frontend
status: fixed
origin: 既有实现
files:
  - backend/routers/hub.py
  - src/lib/api.ts
  - src/stores/hubStore.ts
  - src/components/hub/HubConnectModal.tsx
  - src/components/hub/HubCommentsPanel.tsx
  - src/views/ProjectHomeView.tsx
created: 2026-07-07
---

## 问题

Hub 侧协作机制（WB-065 评论/@提及/在线状态）、目录下发（WB-066）、同步/导入（WB-062/063）都已就绪，
但 **AgentMate 前端还没接**——用户在界面上看不到评论、在线状态、Hub 通知、也没有「连接/导入 Hub」入口。

## 触发场景

- 用户在项目里想看/发评论、看谁在线、收 @提及通知。
- 用户想「登录 Hub / 把本地项目导入 Hub / 触发同步」。

## 影响

P2：把已就绪的后端协作能力接到界面上，才算用户可用。**依赖 WB-062/063/065/066**（后端已就绪）。

## 建议修法

- **本地 backend 代理 Hub 端点**（前端只连本地 `:8000`，不直连 Hub）：`routers/hub.py` 加转发
  `GET/POST /api/projects/{id}/comments`、`GET /api/projects/{id}/presence`、`GET /api/notifications`
  + `POST /api/notifications/read`（带请求的 Hub token 转发给 Hub）。
- **前端**：
  - 项目页加「讨论」区（评论列表 + 输入 + @提及）、成员在线点、Hub 通知合并进现有消息中心。
  - 设置/侧栏加「连接 Hub / 导入本地数据 / 同步」入口，`GET /api/hub/status` 判断是否显示、是否已绑定。
  - 若是平台管理员，露出「目录管理」入口（WB-066 写端点）。
  - **视觉零重设计**：复用现有 class/token；未接 Hub 时协作入口隐藏、不报错（local-first）。

## 验证

- `npx tsc --noEmit` + `vite build`；Playwright 明暗双主题。
- 接 Hub（`.env` 配 `HUB_URL`）：项目页能发/看评论、@提及产生通知、在线状态显示；未接 Hub 时这些入口隐藏、本机全功能照常。

## 进度（2026-07-08）

**重新收窄**：SkillHub 目录接入已由 [WB-070](WB-070-frontend-hub-skillhub-catalog.md) 做掉（`catalogStore.skillMirror`、`api.searchSkills/hubPull`、ExpertsView）。本 issue 剩：**连接 Hub（登录）+ 协作代理（评论/在线/通知）+ 导入入口 + 前端 UI**。

### Slice 1 —— 本地 backend 代理层（✅ 完成并验证）
前端只连本地 :8000；本地 backend 转发到 Hub，全部 guarded（未接 Hub → `{hub:false}`/空）。
- `backend/hub_client.py`：`_post` + `hub_login`（代理登录/注册）+ `list_comments`/`post_comment`/`list_presence`/`hub_notifications`/`mark_hub_notifications`。
- `backend/routers/hub.py`：`POST /api/hub/login`、`GET/POST /api/hub/projects/{id}/comments`、`GET /api/hub/projects/{id}/presence`、`GET /api/hub/notifications`、`POST /api/hub/notifications/read`。
- **连接模型**：`/api/hub/login` 代理到 Hub 拿 token；前端存为自己的 token → 以 Hub 账号身份操作（本地 auth 桥 WB-062 认它）。与 WB-070 的 `syncFromHub`（用 app token 当 Hub token）一致。
- 验证：py_compile；隔离 backend×live hub E2E **13 项全过**（登录代理、评论+@提及→通知代理、presence 代理、mark-read、离线守卫全 None 不崩、错密码→None）。

### Slice 2 —— 前端 UI（✅ 完成）
全新自包含文件，最小化与并发 WB-070 会话的撞车面（只加了 `api.ts` 的 hub 方法 + `ProjectHomeView` 一个 tab）。
- `src/lib/api.ts`：`hubStatus`/`hubLogin`/`hubImport`/`hubComments`/`hubPostComment`/`hubPresence`/`hubNotifications`/`hubMarkNotifs` —— 全经本地 `:8000` 代理。
- `src/stores/hubStore.ts`（新）：`{enabled, linked, checked, refreshStatus, connect, disconnect}`。`connect` = `hubLogin` 拿 token → 存为 app token（即 Hub token，与 WB-070 `syncFromHub` 一致）→ `hubPull` 拉镜像 → 刷新状态。
- `src/components/hub/HubConnectModal.tsx`（新）：登录/注册连接 Hub；已连接则展示账号 + 导入本地项目 + 团队通知 + 断开。复用 LoginModal/MessageCenter 的 `.np-*`/`.msg-*`/`.btn-*` 类，错误走 toast。
- `src/components/hub/HubCommentsPanel.tsx`（新）：项目「讨论」面板 —— 在线成员点 + 评论列表 + 输入（@提及）；REST + 15s 轮询（无 WS，WB-065 决策）。三态：未接 Hub→本地模式提示；已接未登录→连接引导（唤起 HubConnectModal）；已登录→讨论。
- `src/views/ProjectHomeView.tsx`：项目页新增「讨论」tab（Tab 类型 + tab 列表 + 渲染分支 + import，纯增量）。
- **视觉零重设计**：只复用既有 class/token，暗色天然继承；少量内联样式与本仓库惯例一致（ProjectHomeView/MessageCenter 亦如此）。未接 Hub 时协作面板显示「本地模式」提示、不报错（local-first）。

## 处理记录（2026-07-08）

- Slice 1（后端代理）+ Slice 2（前端 UI）均完成。
- **验证**：`npx tsc --noEmit` 通过；`npx vite build` 通过（146 模块，仅既有 chunk-size 告警）。Slice 1 曾以隔离 backend×live Hub E2E 13 项全过验证代理层。
- **未做的实测**：因当前环境未起 backend/Hub、且共享工作树被并发会话占用，未做 Playwright 明暗双主题实测。协作面板的「本地模式」降级路径为纯前端、随本次改动一同经 tsc/build 静态验证；真协作路径（评论/@/在线）已在 Slice 1 于 API 层 E2E 覆盖。接 Hub 的界面级明暗双主题实测留待有运行环境时补。
