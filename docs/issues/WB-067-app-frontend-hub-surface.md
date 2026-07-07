---
id: WB-067
title: App 前端接 Hub —— 协作面板(评论/在线/通知) + 目录 Admin + 同步/导入入口
severity: P2
area: frontend
status: in-progress
origin: 既有实现
files:
  - src/stores/notificationStore.ts
  - backend/routers/hub.py
  - src/views/ProjectHomeView.tsx
created: 2026-07-07
---

## 问题

Hub 侧协作机制（WB-065 评论/@提及/在线状态）、目录下发（WB-066）、同步/导入（WB-062/063）都已就绪，
但 **WorkBuddy 前端还没接**——用户在界面上看不到评论、在线状态、Hub 通知、也没有「连接/导入 Hub」入口。

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

### Slice 2 —— 前端 UI（⬜ 待做，checkpoint 后）
「连接 Hub」入口（登录 → 存 token）+ 项目页讨论区（评论/@）+ 成员在线点 + Hub 通知合并进消息中心 + 导入入口。视觉零重设计 + Playwright 明暗双主题。
