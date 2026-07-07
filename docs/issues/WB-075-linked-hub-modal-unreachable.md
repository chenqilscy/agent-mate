---
id: WB-075
title: 已连接 Hub 后无入口打开连接弹窗，导入/通知/断开成为不可达死代码
severity: P2
area: frontend
status: fixed
origin: WB-067 Slice 2 缺陷（真机 E2E 发现）
files:
  - src/components/hub/HubCommentsPanel.tsx
created: 2026-07-08
---

## 问题

`HubConnectModal` 的「已连接」分支（展示账号 + 导入本地项目到 Hub + 团队通知 + 断开）只能由
`HubCommentsPanel` 里那个「连接 Hub」按钮打开，而该按钮**仅在未连接（`!linked`）时**渲染。
一旦连接成功，讨论面板切到评论视图，再无任何入口能打开弹窗 → **导入/通知/断开三项永远点不到**，
成了不可达死代码；用户想断开只能手动清 localStorage。

## 触发场景

真机 E2E：登录 Hub 后，项目「讨论」tab 只有评论区，找不到「断开」「导入本地项目」「团队通知」。

## 影响

P2：一大块已实现 UI 不可达；断开连接无正常入口。

## 建议修法

在讨论面板已连接态加一行轻量管理头：「已连接 Hub · <账号>」+「管理」按钮，点开同一个
`HubConnectModal`（此时展示已连接分支）。保持视觉零重设计（复用 .btn-line）。

## 验证

- 真机：已连接态讨论面板显示「已连接 Hub · alice」+「管理」→ 点开弹窗见 账号/导入/通知/断开；断开后回到连接引导。
