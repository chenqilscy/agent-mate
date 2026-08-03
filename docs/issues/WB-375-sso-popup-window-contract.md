---
id: WB-375
title: SSO 弹窗使用 noopener 后错误依赖 WindowProxy 返回值
severity: P1
area: frontend
status: open
origin: 🆕 近期改动
files:
  - src/stores/authStore.ts:49
  - console/src/LoginPage.tsx:39
created: 2026-08-03
---

## 问题
App 与 Console 使用 noopener,noreferrer 打开授权页后，把 window.open 返回 null 判定为弹窗被拦截；标准允许在 noopener 时返回 null。

## 触发场景
用户点击 Google/微信/Telegram 登录 → 授权页已打开 → 前端立即报 popup_blocked 并停止轮询。

## 影响
P1。真实 SSO 登录主路径不可可靠使用。

## 建议修法
不依赖授权窗口句柄完成协议；同步创建可检测的本地窗口或打开新页后始终按 attempt ID 轮询，并提供完成授权后的恢复入口。

## 验证
App/Console 单元契约验证 noopener 返回 null 时仍轮询；弹窗真正被阻止时给出可恢复提示；类型检查与构建通过。
