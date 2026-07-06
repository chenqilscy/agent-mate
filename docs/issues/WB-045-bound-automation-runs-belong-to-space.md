---
id: WB-045
title: 绑定了工作空间的自动化，其运行会话应归入该「空间」而非「自动化」分组
severity: P3
area: frontend
status: fixed
origin: 🆕 近期改动
files:
  - src/components/layout/Sidebar.tsx:70
created: 2026-07-06
---

## 问题

WB-041 为「去重」把**所有**自动化运行会话都放进侧栏「自动化」分组、并从「空间」里过滤掉
（[`Sidebar.tsx:70`](../../src/components/layout/Sidebar.tsx#L70) `sessionsOf` 加了 `s.kind !== 'automation'`）。
结果：一条**绑定了工作空间**的自动化（如「经典电影推荐」绑「咖啡创业」），其运行会话不出现在
「咖啡创业」空间下，而是躺在「自动化」分组里——与「绑了空间就归到那个空间」的直觉不符。

## 触发场景

1. 建一条绑定某工作空间的自动化，运行几次。
2. 侧栏「空间」对应项目下看不到这些运行；它们在「自动化」分组里。

## 影响

P3：可达性没问题（在「自动化」分组能找到），但归类反直觉——绑定空间的运行不在其空间下。

## 建议修法（用户选定：绑定的进空间、未绑定的进自动化）

- `sessionsOf(pid)` 去掉 `&& s.kind !== 'automation'`——绑定空间的自动化会话像项目执行一样**嵌回其空间**。
- `autoRuns` 收窄为**仅未绑定**：`s.kind === 'automation' && !s.project_id`——「自动化」分组只收没有归属
  空间的自动化运行。二者互斥、无重复。
- 更新相应注释；「任务」原过滤（`!project_id && kind!=='automation'`）保持不变。

## 验证

- `tsc` 通过。浏览器：绑定空间的自动化，其运行出现在对应「空间」下、不在「自动化」分组；
  未绑定的自动化运行仍在「自动化」分组；「任务」不含自动化会话。明暗双主题正常。
- 回归：普通对话/项目会话不受影响；WB-043 运行记录 tab 不受影响（走 `/automation-runs`，与侧栏分组无关）。

## 处理记录（2026-07-06）

- `Sidebar.tsx`：`sessionsOf(pid)` 去掉 `&& s.kind !== 'automation'`（绑定空间的自动化会话嵌回其空间）；
  `autoRuns` 收窄为 `s.kind === 'automation' && !s.project_id`（「自动化」分组只收未绑定的）。二者互斥、无重复。
  更新注释。
- 验证：`tsc` 通过。Playwright 实测：「咖啡创业」空间展开后列出「经典电影推荐」的多次运行（3分钟前…），
  与该项目普通会话并列；「自动化」分组由 25 → 14，只剩未绑定的「每日 5 个英语单词」等（含 now-bound 自动化
  在绑定前产生的旧运行——每条运行会话按其当时的工作空间归类，符合预期）。「任务」不含自动化会话。
- 注：控制台的 `/api/notifications 404` 与 `useNotificationStore is not defined` 属并行 M7 C4 通知中心在制品，
  与本 issue 无关。
- commit：（尚未提交）
