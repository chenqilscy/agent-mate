---
id: WB-260
title: WbButton 无边框控件悬浮时被 Ant 补边框导致内容抖动
severity: P1
area: ui
status: fixed
origin: 🆕 近期改动
files:
  - src/components/ui/Primitives.tsx:25
  - src/styles/antd.css:1
  - src/styles/app.css:144
created: 2026-07-21
---

## 问题
`WbButton` 把既有 WorkBuddy 按钮统一包成 Ant Design `Button`。旧视觉类中的无边框按钮
（首页 `.tray-chip` 是已复现样本）常态为 `border: none`，但 Ant 的通用 hover 规则会重新写入
`1px solid` 边框。固定尺寸、`border-box` 的按钮外框不变，内部内容盒却缩小 2px，图标和文字
重新居中移动约 1px；配合 `transition: all`，鼠标移入移出时表现为控件抖动。

## 触发场景
打开首页，把鼠标在 Composer 下方的“选择工作空间”和“默认权限”之间来回移动；两个按钮的
文字与图标在 hover 边界发生位移。其他由 `WbButton` 渲染、常态无边框但没有显式 hover
边框约束的旧视觉类也可能复现。

## 影响
P1：核心首页输入区存在稳定可见的交互抖动，且根因位于共享按钮兼容层，可能影响多个页面。

## 建议修法
在 `WbButton` 兼容层为需要保留旧无边框盒模型的视觉类提供明确语义，并让 Ant 使用无边框
button variant；不要用全局规则移除所有 Ant Button 边框，以免破坏 `.btn-line`、`.ctool` 等
原本需要边框的控件。静态审计所有 `WbButton` class，并在浏览器核对代表性无边框/有边框控件。

## 验证
- 首页两个 tray 按钮 hover 前后外框与所有子元素坐标、宽高完全不变。
- 明暗主题下 hover 反馈清晰，无新增边框、阴影或颜色回归。
- 审计所有 `WbButton` 视觉类，不再存在“常态 0px、hover 1px”的同类盒模型变化。
- `npx tsc --noEmit`、`npx vite build` 和相关回归测试通过。

## 处理记录（2026-07-21）
- 改动：`WbButton` 统一标记 22 个全无边框视觉类，并对助理分段按钮、响应式导航把手两类非对称边框单独保持各边宽度；四处父级 `button` 选择器改成显式视觉 class，避免无 class 按钮漏过兼容层。
- 审计：静态扫描全部 `WbButton` class 与 CSS 边框声明；新增回归门禁，禁止父级/元素 `button` 选择器隐式制造无边框按钮，并要求所有显式零边框 class 都进入共享兼容集合。
- 验证：真实 848px 首页中，“选择工作空间”交互前后边框均为 `0px`，按钮宽高与图标/文字相对坐标逐项完全一致；浅色、深色均保持 0px；运行时无未标记的零边框 Ant Button。`pnpm test:regression` 86/86、TypeScript build、`npx vite build` 均通过。
- commit：本次 WB-260 修复提交。
