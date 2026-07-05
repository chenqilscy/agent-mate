---
id: WB-018
title: 长文件名 chip / 长会话标题不截断
severity: P2
area: ui
status: fixed
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

## 处理记录（2026-07-06）
- 改动：chip 标签包进 `.np-lbl`（省略号、可缩），图标与 × 不缩，`.np-chip` 加 max-width:220px 并挂 `title` 全路径；`.chat-head .ch-t` 加 `min-width:0`+省略号。（src/styles/app.css, src/components/composer/Composer.tsx, src/components/project/NewProjectModal.tsx）
- 验证：`vite build` 通过；深层路径 ref chip、超长会话标题均省略号截断不破版，hover 有 title 全文。
