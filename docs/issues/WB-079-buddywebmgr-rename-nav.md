---
id: WB-079
title: BuddyWebMgr 品牌更名 + 导航重构（门户骨架）
severity: P2
area: frontend
status: fixed
origin: WB-078 epic
files:
  - hub/web/console.html
  - hub/main.py
created: 2026-07-08
---

## 问题

门户仍叫「AgentMate Hub · 控制台」，导航只有 项目/组织/通知/目录 Admin，不成「管理门户」骨架。

## 触发场景

打开 `:8100/` —— 标题、logo、顶栏、导航都是旧「Hub 控制台」，且没有目录运营中心/SkillHub 入口。

## 影响

P2：更名与骨架是后续各模块的落脚点。

## 建议修法

- `console.html`：`<title>`/logo/顶栏名/文案 → **BuddyWebMgr**；导航重构为 项目 / 目录运营中心 / 组织 / 通知 / 账号
  （目录运营中心 + SkillHub 归平台管理员可见的一块，替掉旧「目录 Admin」入口）。
- 仅改 Web 门户品牌层；**不改** `hub/` 目录、`HUB_URL`、路由 prefix、DB 名等内部标识（见设计 §7）。
- 视觉沿用现有单文件 CSS 变量体系（暗色）。

## 验证

`:8100/` 显示 BuddyWebMgr、新导航；`hub/main.py GET /` 正常服务；登录/退出/各既有页仍工作。

## 处理记录（2026-07-08）

`console.html`：`<title>`→「BuddyWebMgr · AgentMate 管理门户」、logo「B」、顶栏名「BuddyWebMgr」+badge、authView h1、
导航重构为 项目 / 目录运营中心(admin) / 组织 / 通知（「目录 Admin」→「目录运营中心」，提前到第二位）。`main.py` fallback 文案同步。
仅 Web 门户品牌层，未动 `hub/`·`HUB_URL`·路由 prefix 等内部标识。**验证**：py_compile 过；Playwright 登录 alice(admin)→顶栏/导航/平台管理员徽标/项目页均正确。
