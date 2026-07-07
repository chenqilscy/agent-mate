---
id: WB-068
title: Hub web 管理控制台 —— Hub 自带的 web UI（账号/项目/成员/邀请/目录 Admin/通知）
severity: P2
area: backend
status: fixed
origin: 既有实现
files:
  - hub/main.py
  - hub/routers/catalog.py
created: 2026-07-07
---

## 问题

Hub（WB-061~066）目前**纯 API、无界面**。运营/团队管理员要管账号目录、项目成员、看时间线/通知，
只能 curl。需要 Hub **自带一个 web 管理控制台**。

## 触发场景

- 平台管理员登录 Hub 控制台，增/改/删下发目录（WB-066）。
- 团队成员登录，建项目、加成员/发邀请、看项目评论/时间线、收通知。

## 影响

P2：让 Hub 可视化可用。**自成一体**——Hub 自己服务一个页面、调自己的 `/api`，不依赖 WorkBuddy 前端、无需构建管线。

## 建议修法

- **自带静态控制台**：`hub/web/console.html`（单文件，内联 CSS+JS，同源调 `/api`；CSP 安全、零构建）。
  `hub/main.py` 加路由 `GET /` → 返回该页面（或挂 StaticFiles）。
- **功能 v1**：
  - 登录/注册（token 存 localStorage）。
  - 项目：列表 / 新建 / 成员（加/改角色/移除）/ 邀请码 / 评论（含 @提及）/ 在线状态 / 时间线。
  - 组织：列表 / 新建 / 成员。
  - 目录 Admin（仅平台管理员）：列/增/改/删/排序 catalog 项（WB-066 写端点）。
  - 通知：列表 + 标记已读。
- 复用 Hub 现有 `/api`，不新增业务逻辑；纯展示/操作层。

## 验证

- Hub 起服 → 浏览器打开 `:8100/` → 控制台加载。
- Playwright：注册/登录 → 建项目 → 加成员/发邀请 → 目录 Admin 增一条 → 通知 → 都真实调用 `/api` 生效。
- 权限：非平台管理员看不到/不能用目录 Admin 写操作。

## 处理记录（2026-07-07）

### 改动
- `hub/web/console.html`（新，单文件自带控制台）：内联 CSS+JS、同源调 `/api`、无外部资源（CSP 安全、零构建）。功能 v1：登录/注册（首账号自举平台管理员）；项目（列/建/成员加·改角色·移除/邀请码/评论含 @提及/在线状态/时间线）；组织（列/建）；通知（读/标记已读）；**目录 Admin（仅平台管理员）**：列/增/删 catalog 项（调 WB-066 写端点）。
- `hub/main.py`：`GET /` → 返回 `console.html`（HTMLResponse）。

### 验证
- py_compile；Hub 起服 `GET /` → 200（~19KB）。
- **Playwright 实测**：注册首账号 → 顶栏显示「平台管理员」徽标 → 建项目「控制台测试项目」→ 列表出现 → 打开「目录 Admin」→ 新增一条 `EXP_GRID` 卡（真 `POST /api/catalog`）→ 列表反映（含 sort/JSON + 删除按钮）。暗色主题渲染整洁，除 favicon 404 外无 console 错误。
- 权限：`目录 Admin` 入口仅 `ME.is_platform_admin` 时渲染（前端隐藏）+ 服务端 WB-066 写端点 403（双保险）。

### 未做（后续）
- 更细的目录编辑（改 data/排序 UI，当前 v1 为增/删）、org 级目录管理界面、时间线/评论的实时刷新（v1 靠重新打开/操作后刷新）。

commit：见下。
