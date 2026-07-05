---
id: WB-021
title: navOpen 跨 resize 残留（窄→宽→窄抽屉自开）
severity: P2
area: frontend
status: open
origin: 🆕 近期改动
files:
  - src/stores/uiStore.ts:55
  - src/App.tsx:69
created: 2026-07-06
---

## 问题
响应式抽屉全靠 `@media(max-width:900px)` 门控，宽屏下即使 `navOpen=true` 也不可见（无残留 scrim）。但 `navOpen` 不会被重置：narrow 打开抽屉 → 拉宽 → 再拉回窄，抽屉**未经用户操作即已打开**。

## 触发场景
在窄屏打开抽屉后放大再缩小窗口。桌面固定窗口下少见，浏览器/分屏下可现。

## 影响
低危、观感问题。

## 建议修法
加 `matchMedia('(max-width:900px)')` 监听，跨过阈值时 `setNavOpen(false)`。

## 验证
窄屏开抽屉 → 拉宽 → 拉回窄：抽屉应为关闭态。
