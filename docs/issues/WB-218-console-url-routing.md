---
id: WB-218
title: AgentMate Console 内存态视图改为可直达多页面路由
severity: P1
area: frontend
status: fixed
origin: 既有实现
files:
  - server/web/console.html:293
  - server/main.py:37
created: 2026-07-21
---

## 问题

AgentMate Console 虽然已有概览、项目、组织、目录、用户和通知等独立内容视图，但
`server/web/console.html:293` 仍只靠 `VIEW` / `CATVIEW` / `CUR` 内存变量切换，所有页面地址始终是 `/`。
Server 也只在 `server/main.py:37` 服务根路径，直接访问任何功能路径都会 404。

## 触发场景

登录 Console → 从侧栏进入项目、技能或用户页 → 地址栏不变；刷新回到概览，复制地址无法分享当前页，
浏览器前进/后退也不能恢复页面。直接打开项目详情路径时 Server 返回 404。

## 影响

P1：Console 已是多功能管理端，却没有真实页面边界，无法深链、刷新恢复或使用浏览器导航；
与 AgentMate App 已完成的多页面路由体验不一致。

## 建议修法

- 参考 App 的无额外依赖 History API 路由层，为概览、项目列表/详情、组织、目录各类、用户和通知提供稳定路径。
- 所有侧栏、快速入口、项目打开/返回统一走导航函数并同步 URL；监听 `popstate` 恢复视图。
- Server 为 Console 页面路径返回同一入口 HTML，同时保持未知 `/api/*` 为 404，不遮蔽业务 API。
- 未知页面安全替换回概览；无权限资源仍由现有 API 门禁处理。

## 验证

- 每个一级页面有独立 URL，直接打开、刷新、前进/后退均恢复正确视图与选中态。
- `/projects/{id}` 可直接加载真实项目，返回项目列表后 URL 正确。
- 未知 Console 路径回到概览；未知 `/api/*` 仍返回 404。
- Console 脚本语法检查、Server Python 编译、HTTP 冒烟、浏览器真实登录与深链验证通过。

## 处理记录（2026-07-21）

- 改动：`server/web/console.html` 新增 History API 路由层，概览、项目列表/详情、组织、目录各类、用户、通知均有稳定 URL；侧栏、快速入口和项目打开/返回统一走 URL 导航，监听 `popstate`，未知路径回概览，管理员页面直达保持权限收口。`server/main.py` 增加 Console 深链 HTML 回退，未知 `/api/*` 继续返回 404。
- 验证：脚本 `new Function` 语法检查、`server/main.py` Python 编译、`npx tsc --noEmit`、Server 单测 4/4、`git diff --check` 均通过；硬重启 `:8100` 后验证 8 条深链 200 与未知 API 404。浏览器用真实 alice 管理员账号验证 `/catalog/skills` 前进/后退、`/projects/{uuid}` 刷新恢复、未知页面回 `/`，页面渲染正常。
- commit：本次 WB-218 提交（见 Git 历史）。
