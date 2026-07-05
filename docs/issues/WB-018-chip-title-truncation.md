---
id: WB-018
title: 长文件名 chip / 长会话标题不截断
severity: P2
area: ui
status: open
origin: 🆕 近期改动
files:
  - src/styles/app.css:515
  - src/components/composer/RefPicker.tsx:43
  - src/views/ChatView.tsx:69
  - src/styles/app.css:129
created: 2026-07-06
---

## 问题
两处溢出：
1. **loadout chip**：`RefPicker` 用完整路径作 chip 名（`RefPicker.tsx:43` `addRef({name: f.path})`），`.np-chip`（`app.css:515`）无 `max-width`/省略号 → 深层路径撑出很宽的 chip，在 `.cloadout` 里独占一行。
2. **会话标题**：`.ch-t`（`app.css:129`）无 `min-width:0`/省略号，`.chat-head` 无 flex-wrap → 超长标题挤压/贴近右侧头部按钮。

## 影响
视觉溢出，低危。

## 建议修法
```css
.np-chip { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ch-t { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
```
或 ref chip 只显示 `f.name`（title 属性挂全路径）。

## 验证
引用深路径文件 / 打开超长标题会话 → chip 与标题省略号截断，不破版。
