---
id: WB-430
title: AgentMate App 与 Console 的视觉系统和工作台细节不一致
severity: P2
area: ui
status: in-progress
origin: 既有实现
files:
  - src/styles/tokens.css:109
  - src/styles/app.css:88
  - src/styles/antd.css:96
  - src/components/ui/AppThemeProvider.tsx:7
  - src/views/HomeView.tsx:133
  - console/src/App.tsx:157
  - console/src/styles.css:1
  - vite.console.config.ts:14
created: 2026-08-07
---

## 问题
AgentMate App 仍混用了原型阶段的视觉规格：252px 侧栏、14–18px 大圆角、36px 中号 Ant Design 控件，以及项目页常驻的 300px 配置栏和窄幅悬浮输入框。虽然首页已经对齐 Console 色阶，但项目工作台的导航密度、页面表面、边框、圆角、留白和信息布局仍与 Console 的 216px 侧栏、8px 圆角、32px 小号控件及单主画布差异明显，两个系统仍像两套产品。

## 触发场景
在 1280×720 桌面窗口打开 AgentMate 的项目详情页并切换深色主题 → 252px 侧栏和 300px 常驻项目配置共同挤压主画布；想法卡、健康卡和输入框使用不同的大圆角与阴影，输入框仅占中间窄幅，顶栏、内容区和配置区又几乎同色。对照 Console 概览页，密度、表面层次和有效内容宽度均不一致。

## 影响
P2。功能可用，但首页是用户最常进入的工作入口；不稳定的信息层级会降低扫读效率，也让 App 与同产品 Console 呈现出割裂的视觉品质。

## 建议修法
保留 WorkBuddy 既有业务结构、class 和品牌绿，不删除任何项目能力。以 Console 的设计契约统一 App：桌面侧栏收窄至 216px，顶栏和侧栏使用独立表面 token，Ant Design 默认采用 8px 圆角与小号控件；项目配置从常驻栏改为按需抽屉，让项目工作台恢复单主画布；项目页卡片、标签页、提示条和输入区统一 8px 圆角、16/24px 间距及克制边框，移除不必要的悬浮阴影。

## 验证
- `npx tsc --noEmit` 与 `npx vite build` 通过。
- 在 1280×720、900px、390×844 下验证首页无横向溢出、主操作不被遮挡。
- 明暗双主题下确认页面、侧栏、输入区和信息卡片层级清楚，文字对比正常。
- 桌面项目页侧栏为 216px，项目配置默认关闭且可从顶栏打开/关闭；主内容不再被常驻配置栏压缩。
- 项目想法卡、健康卡、配置卡和输入框采用一致的 8px 视觉圆角，项目输入区横向使用完整主画布。
- 验证场景切换、快捷入口、工作空间/权限选择、想法记录与任务进展入口仍可操作；浏览器 warning/error 为 0。

## 当前进展（2026-08-07）
- 已实现 Console 色阶对齐、960px 首页主面板、明暗输入底托修复、移动端触控尺寸与 reduced-motion 适配。
- 重新对照实际 Console 登录页：两端页面底色均为 `rgb(15, 20, 32)`，AgentMate 首页以独立表面、边框、品牌渐变和克制阴影承接同一视觉层级，同时保留 WorkBuddy 原有导航与业务结构。
- 已通过 `npx tsc --noEmit`、`npx vite build`（6101 modules）及 issue archive 一致性检查。
- 真实浏览器验证 1280×720 明暗主题、900px、390×844 和深色项目页；各视口无横向溢出，移动端场景/快捷项为 44px、托盘按钮为 40px。
- 场景切换、“更多”、工作空间、权限弹层均可操作；`prefers-reduced-motion: reduce` 命中且 hover 位移被关闭；浏览器 warning/error 为 0。

## 用户复核与扩展处理（2026-08-07）
- 用户以 App 项目详情和 Console 概览的同尺寸截图复核后指出：上一轮仅完成首页与色板优化，两个系统的 UI 细节仍相差过大。
- 本轮将 WB-430 从“首页视觉层级”扩展为 App 全局设计契约与项目工作台细节对齐；保留上一轮结果，并补齐侧栏、Ant Design 组件规格、项目主画布、配置抽屉和底部输入区的验收。
- 已将 App 与 Ant Design 的核心契约统一为 Console 色阶、8px 基础圆角、32px 小号控件，并把桌面侧栏从 252px 收窄为 216px；项目配置由 300px 常驻栏改为 320px 按需抽屉，保留独立关闭按钮和遮罩关闭能力。
- 项目页顶栏/侧栏/页面分别使用 `#151B2A`、`#111827`、`#0F1420` 深色表面；想法卡、健康卡、配置卡与执行输入区均收敛为 8px 圆角和无悬浮阴影的边框层级，输入区横向填满项目主画布。
- `npx tsc --noEmit`、`npx vite build`（6101 modules）与 `python scripts/archive_issues.py --check` 通过。
- 真实浏览器 1280×720 读取：侧栏 216px、主画布 1064px、项目配置默认位于画布外、想法/健康/输入框圆角均为 8px；配置抽屉可打开及从内部关闭。
- 明亮主题的页面/侧栏/卡片为 `#F4F6F8` / `#FFFFFF` / `#FFFFFF`，深色主题恢复为测试前状态；900px 和 390×844 均无横向溢出，移动端 320px 配置抽屉可打开关闭；浏览器 warning/error 为 0。

## 双系统双主题 CSS 审查（2026-08-07）
- 用户补充要求对 AgentMate App 与 Console 的浅色/深色 CSS 做整体审查，不以项目详情单页验收替代全局主题一致性。
- 静态核实发现 Console 虽定义了 `--console-*` 双主题变量，但 `ConfigProvider` 仍只设置品牌色和圆角；Ant Design/Pro Components 的页面、卡片、弹层与边框继续使用算法默认色，未与 Console 自己的 `#F4F6F8/#FFFFFF` 和 `#0F1420/#161C2B` 契约绑定。
- App 仍有上一套暗色表面 `#1F242A/#2A2F36` 残留在按钮、弹窗和消息桥接层，并有少数浅色 hover/error 背景未通过 token 或 `body.dark` 覆盖，切到深色时会出现亮块或表面层级漂移。
- 本轮验收增加：两端 Ant Design 主题 token 与 CSS 变量逐项一致；App 不再出现已确认的浅色表面泄漏；App 与 Console 的首页/项目或登录页在浅色和深色下均检查计算样式、文字对比、横向溢出和浏览器 warning/error。
- 已新增 `src/theme/palette.ts` 作为 App/Console 共用的 Ant Design 表面契约，统一 page/container/elevated/header/sidebar/text/border；两端继续各自保留 CSS 变量，但组件库不再回落到算法默认黑灰。
- App 已移除按钮、弹窗、消息、原生 select、hover、禁用态中的旧暗色/浅色表面残留；错误与警告组件改用双主题语义 token。浅色三级文字由 `#98A2B3` 调整为 `#667085`，深色由 `#667085` 调整为 `#7D899F`，在对应面板上的对比分别提升到约 4.97:1 和 4.82:1。
- Console 登录页新增可见的浅色/深色切换入口；主题 class 与原生 `color-scheme` 在绘制前同步，未登录用户也能选择主题。
- 构建验证：`npx tsc --noEmit`、`npx vite build`（6102 modules）、`pnpm build:console`（5964 modules）和 issue archive 一致性检查通过。
- 真实浏览器计算样式：深色两端 page/panel/border 均为 `#0F1420/#161C2B/#2A3348`；浅色均为 `#F4F6F8/#FFFFFF/#E6E9EF`，正文为 `#1D2939`。App 与 Console 均完成真实主题切换、恢复深色，并在桌面和 390px 验证无横向溢出；浏览器 warning/error 为 0。
- Console 生产构建复核同时修正 `manualChunks` 对标准 `@ant-design/pro-components` 路径匹配失效的问题，避免主题产物重新出现 Pro Components 跨 chunk 循环执行顺序警告。
