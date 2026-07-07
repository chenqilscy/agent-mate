---
id: WB-076
title: 连接 Hub 的入口只藏在项目讨论面板内，无项目的新用户无法首次连接
severity: P2
area: frontend
status: fixed
origin: WB-067 真机 E2E 复盘
files:
  - src/components/layout/Sidebar.tsx
created: 2026-07-08
---

## 问题

「连接 Hub」的唯一入口是 `HubCommentsPanel`（项目 → 讨论 tab）里的按钮。于是：

- **没有任何项目的新用户进不去讨论 tab → 无法首次连接 Hub**（本次 E2E 靠预建一个本地引导项目绕过）。
- 连接是个全局态（账号级），却只能从某个项目内触发，语义也别扭。

## 触发场景

全新用户（零项目）打开 App，想连接团队 Hub —— 侧栏/账号菜单里找不到入口。

## 影响

P2：功能可达性缺口。已接 Hub（HUB_URL 配置）时才涉及；纯本地不受影响。

## 建议修法

在侧栏账号弹窗（profile popover）加一行全局入口：`hubStore.enabled` 为真才显示，
未连接→「连接 Hub」、已连接→「已连接 Hub · <账号>」，点开同一个 `HubConnectModal`
（登录或已连接分支）。Sidebar 挂载时若 `!checked` 触发一次 `refreshStatus`，让 `enabled`
在不进项目时也已知。视觉零重设计：复用 `.pf-row`。

## 验证

- 真机：零项目状态下打开账号菜单 → 见「连接 Hub」→ 登录 → 变「已连接 Hub · alice」；
  未接 Hub（HUB_URL 空）时该行不出现。
