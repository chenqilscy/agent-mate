---
id: WB-430
title: AgentMate 首页与 Console 的视觉层级和内容节奏不一致
severity: P2
area: ui
status: in-progress
origin: 既有实现
files:
  - src/styles/tokens.css:109
  - src/styles/app.css:88
  - src/views/HomeView.tsx:133
created: 2026-08-07
---

## 问题
AgentMate 首页仍沿用原型阶段的 720px 单列堆叠和近乎同色的页面、侧栏、卡片表面（`src/styles/app.css:88-170`），深色主题的背景与面板缺少分层。与当前 Console 已形成的页面背景、面板表面、品牌渐变和宽内容节奏相比，首页首屏显得拥挤且扁平，任务入口、想法收集箱和任务进展之间的主次不够清楚。

## 触发场景
在 1280×720 桌面窗口打开 AgentMate 首页并切换深色主题 → 主内容被限制在 720px，标题、快捷入口、输入区与后续卡片连续堆叠；主区、侧栏和卡片的背景层级接近，无法形成 Console 那样清楚的工作台层次。

## 影响
P2。功能可用，但首页是用户最常进入的工作入口；不稳定的信息层级会降低扫读效率，也让 App 与同产品 Console 呈现出割裂的视觉品质。

## 建议修法
保留 WorkBuddy 既有 DOM、class、品牌绿和功能结构，不引入新的导航或业务组件。参考 Console 的表面层级，将首页扩展为更稳定的内容宽度，使用现有 token 建立页背景、面板和卡片层级；通过受控的品牌渐变、留白、边框与阴影加强任务输入的主入口地位，并保持任务进展为次级信息。

## 验证
- `npx tsc --noEmit` 与 `npx vite build` 通过。
- 在 1280×720、900px、390×844 下验证首页无横向溢出、主操作不被遮挡。
- 明暗双主题下确认页面、侧栏、输入区和信息卡片层级清楚，文字对比正常。
- 验证场景切换、快捷入口、工作空间/权限选择、想法记录与任务进展入口仍可操作；浏览器 warning/error 为 0。

## 当前进展（2026-08-07）
- 已实现 Console 色阶对齐、960px 首页主面板、明暗输入底托修复、移动端触控尺寸与 reduced-motion 适配。
- 重新对照实际 Console 登录页：两端页面底色均为 `rgb(15, 20, 32)`，AgentMate 首页以独立表面、边框、品牌渐变和克制阴影承接同一视觉层级，同时保留 WorkBuddy 原有导航与业务结构。
- 已通过 `npx tsc --noEmit`、`npx vite build`（6101 modules）及 issue archive 一致性检查。
- 真实浏览器验证 1280×720 明暗主题、900px、390×844 和深色项目页；各视口无横向溢出，移动端场景/快捷项为 44px、托盘按钮为 40px。
- 场景切换、“更多”、工作空间、权限弹层均可操作；`prefers-reduced-motion: reduce` 命中且 hover 位移被关闭；浏览器 warning/error 为 0。
