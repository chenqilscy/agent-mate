---
id: WB-003
title: ad-hoc loadout（专家/技能/连接器）泄漏进项目执行
severity: P0
area: frontend
status: open
origin: 🆕 近期改动
files:
  - src/stores/chatStore.ts:63
  - src/stores/chatStore.ts:98
  - src/stores/loadoutStore.ts
  - src/components/layout/Sidebar.tsx:88
  - src/views/ProjectHomeView.tsx:77
created: 2026-07-06
---

## 问题
`loadoutStore.reset()` 只在 `openSession`（`chatStore.ts:63`）与侧栏「新建任务」（`Sidebar.tsx:88`）调用。`startProject`（`chatStore.ts:98`）、进入 `ProjectHomeView`、`openProject` 均**不**重置。注释声称 loadout「reset on session change」，但从聊天会话导航进项目并发起执行时没有任何重置点。

## 触发场景
在某聊天里从 ＋ 菜单选了专家 X → 点侧栏「项目」→ 进某项目主页 → 直接在项目 composer 里发起执行。上一段聊天的 X 仍在 `loadoutStore`，被 `send` 当作 ad-hoc 专家随首条消息发出，后端再与项目自身 loadout 合并 → 运行了用户没为该项目选的人格。chips 会显示但用户通常不会注意。

## 影响
语义正确性 bug：本次「＋菜单 loadout」改动引入的最实的一个。

## 建议修法
`startProject` 时 `useLoadoutStore.getState().reset()`（或进入 ProjectHomeView 时重置）。明确规则：**进入任何新会话/新执行上下文都清空 ad-hoc loadout**，仅在同一 draft→send 的连续动作里保留。注意别破坏 WB 里已验证的「首页/项目页选完再 send」路径（reset 不能发生在 send 读取 loadout 之前）。

## 验证
聊天里选专家 X → 进项目发起执行 → 该执行的「已加载」轨迹不应含 X（除非项目自身配置了 X）。同时回归：首页选 X 直接发送仍带 X。
