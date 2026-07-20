---
id: WB-042
title: 侧栏「更多」弹出菜单位置脱离按钮（固定 bottom:118px，飘到侧栏右下角）
severity: P2
area: ui
status: fixed
origin: 🏚 迁移遗留
files:
  - src/styles/app.css:352
  - src/components/layout/Sidebar.tsx:384
  - src/components/layout/Sidebar.tsx:257
created: 2026-07-06
---

## 问题

「更多」是 `.nav` 里**靠上**的一个 `nav-item`（`src/components/layout/Sidebar.tsx:257`），
但它的弹出菜单 `.more-menu` 用了写死的绝对定位 `position:absolute; left:250px; bottom:118px`
（`src/styles/app.css:352`），即「贴侧栏右缘、距底部 118px」。

菜单在 DOM 里是 `.sidebar` 的最后一个子节点（`Sidebar.tsx:384`），与按钮无任何锚定关系。
原型 `docs/tencent-agentmate-reference.html` 里侧栏结构简单、这套坐标勉强能落在按钮附近；迁移到真实应用后，
侧栏中部多了 `.sb-scroll`（任务/空间/自动化）等大块内容、且「更多」固定在顶部，
于是 `bottom:118px` 把菜单甩到了**侧栏右下角**，离触发它的「更多」按钮很远（见用户截图）。

搜索框展开（`.sb-search`）会把 `.nav` 再往下推，写死坐标只会更不准 —— 这类固定坐标本身就不稳。

## 触发场景

1. 侧栏点击顶部的「更多」。
2. 弹出的「我的文件 / 腾讯文档 / ima知识库 / 灵感」菜单出现在侧栏**右下角**，
   而不是在「更多」按钮旁边，视觉上与按钮完全脱节。

## 影响

P2：纯视觉/交互定位缺陷，不影响数据正确性；但菜单与其触发点脱节，用户不易把两者关联，
是首屏可见的观感问题。

## 建议修法

把菜单锚定到「更多」按钮，别再用写死的视口坐标：

- `Sidebar.tsx`：用一个 `position:relative` 的包裹层（如 `<div className="more-wrap">`）
  同时包住「更多」`nav-item` 和条件渲染的 `.more-menu`，把菜单从 `.sidebar` 末尾移进来。
- `app.css`：`.more-wrap { position: relative }`；`.more-menu` 的定位由
  `left:250px; bottom:118px` 改为相对包裹层的 flyout —— `left: calc(100% + 6px); top: 0;`
  （其余 `width/background/border/shadow/padding/z-index` 及 `.open` 动画保持不变，视觉零重设计）。
- 顺带把点击外部关闭的 `mousedown` 判定里的 `.closest('.more-menu')` 放宽到 `.closest('.more-wrap')`，
  让再次点「更多」能正常收起（当前按钮不在忽略集合里，存在 mousedown 关→click 又开的抖动）。

## 验证

- `npx tsc --noEmit` 通过。
- Playwright 实测：点「更多」，菜单出现在按钮正右侧、顶端与按钮对齐；搜索框展开后再点，
  菜单仍紧贴按钮（不因 `.nav` 下移而错位）。
- 点菜单项（我的文件/灵感）能正常切视图并收起；点菜单外/再点「更多」能收起。
- 明暗双主题都看一眼：`body.dark .more-menu` 背景覆盖仍生效，无深底深字。
- ≤900px 抽屉态下侧栏打开时菜单位置仍紧贴按钮。

## 处理记录（2026-07-06）

- 改动：
  - `src/components/layout/Sidebar.tsx`：把「更多」`nav-item` 与条件渲染的 `.more-menu`
    一起包进 `<div className="more-wrap">`（菜单从 `.sidebar` 末尾移进来，紧跟按钮）；
    点击外部关闭的 `mousedown` 判定由 `.closest('.more-menu')` 放宽为 `.closest('.more-wrap')`，
    使再次点「更多」能正常收起（消除按钮不在忽略集合导致的 mousedown 关→click 又开抖动）。
  - `src/styles/app.css`：新增 `.more-wrap { position: relative }`；`.more-menu` 定位由写死的
    `left:250px; bottom:118px` 改为相对包裹层的 flyout `left: calc(100% + 6px); top: 0`。
    其余 `width/background/border/shadow/padding/z-index` 及 `.open` 动画一字未动（视觉零重设计）。
- 几何核对：`.more-wrap` 宽 = `.nav` 内容宽 232px、左缘在 x=10（`.sidebar` padding）；
  `left: calc(100%+6px)` → 菜单左缘 x=248（侧栏右缘 252 内 4px），`top:0` 与「更多」按钮顶端对齐。
  即菜单紧贴按钮右侧弹出，取代原来甩到右下角（`bottom:118px`）的坐标。
- 验证：`npx tsc --noEmit` 通过；改动经 Vite HMR 已推入用户正在运行的窗口。
  Playwright 截图未能新起——浏览器 profile 被用户当前运行的 App 窗口占用（SingletonLock），
  未强杀以免打断用户；用户可在已打开的窗口直接点「更多」确认（明暗双主题、≤900px 抽屉态）。
  暗色背景由 `tokens.css:61` 的 `body.dark .more-menu` 覆盖，未被本次定位改动触及。
- commit：（待提交）
