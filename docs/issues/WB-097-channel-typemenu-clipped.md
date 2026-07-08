---
id: WB-097
title: 助理「新增渠道」类型菜单被滚动容器裁切（顶部项看不见）
severity: P2
area: ui
status: fixed
origin: 🆕 近期改动
files:
  - src/components/channel/AssistantChannels.tsx
  - src/styles/app.css
created: 2026-07-09
---

## 问题

WB-088 的渠道 tab 里「＋新增渠道」类型菜单用绝对定位 `.asst-typemenu`（`bottom: 100%` 向上展开），
外层 `.asst-pane` 是 `overflow-y:auto`——菜单向上溢出被滚动容器裁掉，顶部的 Telegram/邮件项看不见
（截图：只露出「邮件」半行 + 两个占位项）。同类问题见 WB-042。

## 触发场景

助理 → 渠道 tab → 点「＋新增渠道」→ 菜单顶部被 pane 顶边裁切，选不到 Telegram/邮件。

## 影响

P2：新增渠道入口不可用（选不到可用类型）。

## 建议修法

复用项目现成的 `Popover`（`components/ui/Popover.tsx`，`position:fixed` 按 anchor 定位、视口内 clamp，
不受 overflow 裁切）替换 `.asst-typemenu` 绝对定位 div；菜单项用既有 `.pop-item` / `.pop-empty` 类
（天然暗色）。移除不再用的 `.asst-typemenu` CSS。

## 验证

- `tsc` / `vite build` 通过。
- 渠道 tab 点「＋新增渠道」，四个类型项（Telegram/邮件可用 + 企业微信/WhatsApp 敬请期待）完整可见、
  不被裁切；点可用项打开对应表单。明暗双主题看。

## 处理记录（2026-07-09）

- 改动：`AssistantChannels.tsx` 用 `Popover`（`position:fixed`、按 anchor 定位、视口内 clamp、不被 overflow
  裁切）替换绝对定位的 `.asst-typemenu` div；菜单项改用既有 `.pop-item`/`.pop-empty` 类（天然暗色）；
  `app.css` 删除不再用的 `.asst-typemenu` 规则。
- 验证：`tsc`/`vite build` 通过；复用全站验证过的 Popover 组件（同 ChatView 分享/历史、侧栏更多菜单）。
  浏览器实时截图 profile 被占用未跑；Popover 定位机制已在他处验证。
- commit：（尚未提交）
