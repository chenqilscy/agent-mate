---
id: WB-024
title: 侧栏头部三个图标按钮（收起/搜索/筛选）仅弹 toast、未实现
severity: P2
area: frontend
status: fixed
origin: 🏚 迁移遗留
files:
  - src/components/layout/Sidebar.tsx:135-145
created: 2026-07-06
---

## 问题
侧栏头部（`WorkBuddy v5.2.3` 右侧）的三个 `sb-ico` 图标按钮全是桩：`onClick` 只调 `toast(...)`，无任何真实行为（`Sidebar.tsx:135-145`）。

- **收起侧栏**（`:136`）→ `toast('收起侧栏')`。`uiStore` 里没有「停靠侧栏折叠」状态——只有 `navOpen`（`uiStore.ts:20`，那是 ≤900px 的移动抽屉开关），宽屏下侧栏无法折叠。
- **搜索**（`:139`）→ `toast('搜索任务')`。没有任务/会话列表搜索能力（`ChatSearch` 只做单条对话内查找，见 WB-007）。
- **筛选**（`:142`）→ `toast('筛选')`。完全没有筛选逻辑。

这三个是头部最显眼、看起来最像可交互的控件，却只给一个「假成功」的 toast 反馈——与铁律 #1「不硬编码、不模拟 / 可真实运行」的取向相悖（区别于 腾讯文档 / ima知识库 / 消息中心 / 发现 那类明显的第三方占位入口）。

## 触发场景
1. 打开应用，侧栏头部可见三个图标。
2. 点「收起侧栏」→ 弹 toast「收起侧栏」，侧栏不折叠。
3. 点「搜索」→ 弹 toast「搜索任务」，无搜索框、任务列表无变化。
4. 点「筛选」→ 弹 toast「筛选」，任务列表无变化。

## 影响
P2：无崩溃、有 toast 反馈，但三个显眼控件「看着能用、点了没用」，误导用户、暴露未完成感；且属于本地纯前端可自足实现的核心 UX（折叠/搜索/筛选任务列表），不像第三方集成需外部依赖。

## 建议修法
按投入从小到大，可分批做，也可先做价值最高的一两个：

- **收起侧栏**：在 `uiStore` 加 `sidebarCollapsed`（宽屏停靠态折叠），`sb-ico` 点击 toggle；`aside.sidebar` 加折叠态 class 控制宽度/隐藏内容。与 `navOpen`（移动抽屉）区分开、别混用。样式复用既有 token，别引入不协调宽度。
- **搜索任务**：给「任务/空间」列表加即时过滤——点击展开一个输入框，按 `session.title` / `project.name` 客户端过滤 `adhoc` 与 `projects`。纯前端、数据已在 store。
- **筛选**：定义清晰的筛选维度（如按状态 running/idle、按是否属于项目、按时间）后再做；维度没定清前，此项可标注为待设计，别为凑功能造无意义筛选。

若某一项决定暂不做，应从「假 toast」改为**明确的未启用态**（disabled / 不渲染 / tooltip 注明），避免继续「假成功」。改动务必明暗双主题都看（`sb-ico` 用 `var(--text-3)`/`--chip`/`--text`，注意 WB-004/008 类翻转坑）。

顺手发现的其它 toast 桩（消息中心、发现、腾讯文档等）不夹带进本 issue——如需跟踪另开。

## 验证
- 收起：宽屏点击后侧栏真折叠/展开，`navOpen`（≤900px 抽屉）行为不受影响（回归 WB-021）。
- 搜索：输入关键词后任务/空间列表实时过滤，清空后恢复。
- 筛选：按选定维度过滤生效；若暂缓则呈现未启用态而非假 toast。
- `npx tsc --noEmit` 通过；Playwright 明暗双主题各看一遍，`sb-ico` 图标与 hover 态在两主题下均清晰。

## 处理记录（2026-07-06）
三个图标全部实装为真功能，去掉 toast 桩：

- **收起侧栏**（宽屏停靠态折叠）：`uiStore` 新增 `sidebarCollapsed` + `setSidebarCollapsed`；`App.tsx` 给 `.shell` 加 `sidebar-collapsed` class，并在窗口收窄过 900px 时重置该状态（与 WB-021 同源思路，避免折叠态泄漏进抽屉世界）。CSS 用 `@media (min-width:901px) .shell.sidebar-collapsed .sidebar{display:none}` 限定为宽屏概念。折叠后菜单栏汉堡按 `.mb-burger.show` 强制显形（`MenuBar.tsx`），点击即展开——汉堡在窄屏仍走 `navOpen` 抽屉、宽屏折叠态走展开，二义合一。
- **搜索**：`Sidebar.tsx` 内置搜索框（`.sb-search`），按 `session.title` 过滤「任务」、按 `project.name` 或子会话标题过滤「空间」；命中子会话的项目在搜索时自动展开且只显命中子项，仅项目名命中则保持收起。Esc/清空按钮复位，关闭搜索时清空 query 以免留下隐形过滤。
- **筛选**：图标下拉小菜单（`.sb-fmenu`，复用 `.more-item`）提供「全部 / 进行中」按真实 `status==='running'` 过滤；菜单项用原生 `<button>`（原生键盘可达，规避 activate 的 role 覆盖）；选择或点击外部关闭。搜索/筛选生效时对应图标加 `.on`（brand-soft）态，避免「任务凭空消失」。

- 改动文件：`src/stores/uiStore.ts`、`src/App.tsx`、`src/components/layout/MenuBar.tsx`、`src/components/layout/Sidebar.tsx`、`src/styles/app.css`、`src/styles/tokens.css`（`.sb-fmenu` 暗色面 #22272D，因 `--card` 在暗色仍为白）。
- 验证：`npx tsc --noEmit` 通过；`npx vite build` 通过。Playwright 实测（含 18 任务/4 项目真数据）：
  - 搜索 `hello` → 任务 18→2、空间→「无匹配空间」；搜索 `咖啡` → `便签测试` 经子会话命中自动展开、`咖啡创业` 经项目名命中保持收起，两种匹配模式均正确。
  - 筛选「进行中」→ 无运行会话时两列均「无匹配」并回「全部」恢复。
  - 收起 → 侧栏消失+汉堡现身；点汉堡复原。宽屏折叠后收窄到 800px：`sidebar-collapsed` 自动清除、侧栏转为 off-canvas 抽屉（`translateX(-260px)`）、汉堡改回驱动 `navOpen`，点汉堡抽屉滑入——无「卡死隐藏」回归。
  - 明暗双主题各看一遍：筛选菜单暗色为 #22272D 抬升面、搜索框暗色 chip 底浅字、`.on`/`sel` 均清晰，无白底白字/深底深字翻车。
- commit：（待提交）
