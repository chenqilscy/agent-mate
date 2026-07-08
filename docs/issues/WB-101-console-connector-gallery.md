---
id: WB-101
title: BuddyWebMgr 连接器目录只有 CRUD 管理，缺主应用那样的「浏览橱窗」
severity: P3
area: ui
status: fixed
origin: 既有实现
files:
  - hub/web/console.html:404
  - src/views/ExpertsView.tsx:583
created: 2026-07-09
---

## 问题

BuddyWebMgr 管理台（`hub/web/console.html`）目录运营中心的「连接器」tab 只有一个
**管理 CRUD**（`connectorsCat`，hub/web/console.html:404）：新增/编辑/停用/删除连接器
定义（`CONN_DEFS`）。而主应用桌面 App 的连接器页（`ConnectorsPane`，
src/views/ExpertsView.tsx:583）是一个**浏览橱窗**：图标 + 名称 + 状态徽章 + 简介的
双列卡片网格，带搜索与详情。管理台里管理员看不到一个「所见即客户端所得」的连接器
橱窗，只能对着一行行表单/列表项，缺乏和 App 一致的浏览体验。

> 注：兄弟任务 WB-100 由并发会话把「专家/专家团」升级为 App 橱窗（改同一 console.html
> 的 catalog center）。本条只动「连接器」，用 `cg-` 前缀 CSS + 只在 `connectorsCat`
> 内加子切换，尽量与其不撞。

## 触发场景

平台管理员登录 BuddyWebMgr → 目录运营中心 → 连接器 → 只能看到「新增连接器」表单
和一串 `.list-item` 管理列表；想像 App 那样「浏览一遍现有连接器橱窗长什么样」时
没有对应视图。

## 影响

P3 体验类：管理台连接器管理可用但不直观，缺少与主应用一致的橱窗浏览视图。无功能
性缺陷。

## 建议修法

在 `connectorsCat` 的「连接器」tab 顶部加一个子切换：**浏览橱窗 | 目录管理**
（模块级状态 `CONNSUB`，仿 `CATVIEW`）：

- **浏览橱窗**（新增，默认）：读同一份 `GET /catalog/CONN_DEFS?all=true`，把每条
  `data = {icon,name,desc,status,launch}` 渲染成 App 风格的双列卡片
  （icon 块 + 名称 + `status`→徽章 rdy/tok + 简介）。顶部一个搜索框按 name/desc 过滤。
  点卡片 → 只读详情浮层（icon/名称/状态/完整简介/launch 摘要「内置·<server>」或
  「stdio·<command>」）+「编辑此连接器」按钮跳到目录管理并载入该项。管理台无会话/
  loadout/OAuth，所以**不搬** App 的「添加到本会话 / 去试试 / 连接授权」交互。
- **目录管理**（保留现状）：即现有 `connectorsCat` 的表单 + 列表 CRUD。

视觉沿用 console 自有暗色 token（`--panel/--chip/--brand`），卡片布局对齐 App 的
`.conn`（src/styles/app.css:407）。新增 CSS 用 `cg-` 前缀避免与并发会话（WB-086/WB-100
也在改 console.html）撞类名。

## 验证

- 启动 Hub（`:8100`）+ 打开 `console.html`，以平台管理员登录（alice/alice123）。
- 目录运营中心 → 连接器：默认见「浏览橱窗」双列卡片；子切换到「目录管理」见原
  CRUD；来回切换状态不丢。
- 橱窗搜索按名称/简介过滤；点卡片出只读详情；「编辑此连接器」跳目录管理并载入该项。
- 目录空时橱窗显示空态提示；rdy/tok 徽章配色在深色下清晰（不出现深底深字）。
- 不回归：原 CRUD 的新增/编辑/停用/删除照常工作。

## 处理记录（2026-07-09）

- 改动（仅 `hub/web/console.html`，纯 vanilla、无后端/构建改动）：
  - 新增 `cg-` 前缀 CSS（卡片网格/徽章 rdy·tok·off/详情浮层），套 console 暗色 token，
    对齐 App `.conn` 布局；`cg-` 前缀避免与并发会话（WB-086/WB-100 同改此文件）撞类名。
  - 新增模块级状态 `CONNSUB`（gallery/manage）与 `CONN_EDIT_ID`（橱窗→管理带项编辑）。
  - `connectorsCat` 改为**分发器**：顶部子切换「浏览橱窗 | 目录管理」；原 CRUD 抽为
    `connectorsManage`（逐字保留，仅改 3 处自递归调用名 + 加载 items 后消费 CONN_EDIT_ID
    自动 `fill`）。新增 `connectorsGallery`（读同一 `GET /catalog/CONN_DEFS?all=true`，
    App 风格双列卡片 + 名称/简介搜索）与 `connectorDetail`（只读浮层：简介/启动摘要/
    所需凭据 +「编辑此连接器」跳目录管理）。管理台无会话/loadout/OAuth，故不搬 App 的
    添加会话/去试试/连接授权。
- 验证：
  - `node --check` 内嵌脚本语法通过；对真实 CONN_DEFS（门户便签 rdy·builtin、门户GitHub
    tok·stdio·GITHUB_TOKEN）在 Node 里跑卡片/详情字符串构建无运行时错误。
  - 隔离 headless Chromium（自建 playwright-core，不抢并发会话的 MCP 浏览器）以 alice/
    alice123 实测：子切换默认橱窗、渲染 2 卡、rdy/tok 徽章、搜索 github→1、点卡出只读详情
    （启动摘要 `stdio · npx …` + GITHUB_TOKEN）、「编辑此连接器」跳目录管理并把门户GitHub
    载入表单、原 CRUD 表单/列表仍在——全部 ✅；无页面 JS 报错（一次性 favicon 404 与本改动
    无关，复测不复现）。暗色双图核对徽章/浮层配色清晰，无深底深字。
- commit：未提交（用户未要求；此文件为并发会话共享，按纪律不整文件 add）。
