---
id: WB-194
title: 连接器卡「添加到本会话」是真状态但假用处 —— 用户一导航去用它就被 reset 清掉
severity: P2
area: frontend
status: fixed
origin: 既有实现
files:
  - src/views/ExpertsView.tsx:646
  - src/stores/chatStore.ts:70
  - src/components/layout/Sidebar.tsx:171
created: 2026-07-17
---

## 问题

连接器橱窗卡的 ＋（`ExpertsView.tsx` 的 `ConnAddBtn`）：

```tsx
useLoadoutStore.getState().toggle('conn', n)
toast((added ? '已移除 · ' : '已添加到本会话 · ') + n)
```

状态是**真的**（进了 `loadoutStore`），但 **loadout 是会话级的，两条通往 composer 的路都会清空它**：

- `chatStore.ts:70` `openSession()` → `useLoadoutStore.getState().reset()`
  （注释：*"opening a different existing session resets in openSession"*）
- `Sidebar.tsx:171` `newTask()` → `useLoadoutStore.getState().reset()`
  （注释：*"a genuinely fresh start — drop any ad-hoc loadout"*）

两处 reset **本身是对的**（WB-003 修的就是 loadout 泄漏跨会话）。问题在于：连接器页停留在原地 toggle，
用户加完之后**必须导航**才能去用它 —— 而一导航就没了。于是它是「真状态、假用处」：
toast 说「已添加到本会话」，用户去到 composer 一看，什么都没有。

对比：本 app 已有正确范式 —— **summon 系**（设 loadout → `startDraft`（**不 reset**）→ `setView`）：
- 专家「召唤」`ExpertsView.tsx:30-43`
- 技能详情「去试试」`SkillDetail.tsx:60-65`
- 技能「推荐」段的 ＋（WB-181 已改成这个范式）

`chatStore.ts:95-98` 的注释把这条设计讲明了：*"startDraft/startProject do NOT reset the loadout"*。

## 触发场景

技能连接器页 → 连接器 → 点某卡的 ＋ → toast「已添加到本会话 · GitHub」→ 侧栏点「新建任务」
（或点任一已有任务）→ composer 的 loadout chips **是空的**，GitHub 没了。

## 影响

P2。不是伪造（状态真进了 store），但用户视角的结果与「假按钮」几乎一样：
提示说加上了，去用时不存在。且它与同页技能段（WB-181 修完后）的行为不一致。

## 建议修法

二选一：

1. **改成 summon 范式（推荐，与专家/技能一致）**：
   `summonConnectors([n])` → `chat.startDraft('对话')` → `setView('home')` + toast「已挂载 · 去试试」。
   `loadoutStore` 需补一个 `summonConnectors`（照 `summonSkills`）。
   代价：点 ＋ 会跳走，不再是原地 toggle。
2. **留在原地 toggle，但让它有意义**：需要 loadout 能跨「进入 composer」存活 ——
   与 WB-003 的隔离设计冲突，除非引入「待挂载暂存区」概念（新机制，成本高）。

倾向 1：与既有三处 summon 一致，零新机制。

## 验证

- 连接器卡点 ＋ → 落到 composer → loadout chip 里**真有**该连接器；
- 发一条消息 → SSE loadout 事件里出现「连接器 X」（或「连接器未就绪 X（原因）」，两者都诚实）；
- 回归：WB-003 的隔离仍在 —— 「新建任务」后 chip 清空、不泄漏进下一段会话。

## 处理记录（2026-07-20）

- 改动：`loadoutStore` 新增 `summonConnectors`；连接器目录卡与详情弹窗统一改为“挂载连接器 → 开新草稿 → 回到输入区”，已挂载状态仍可显式移除。
- 验证：`npx tsc --noEmit` 通过；Playwright + Edge 从 `/connectors` 点击“通达信”卡片加号后返回 `/`，输入区出现真实 `🔗 通达信` loadout chip，页面横向溢出为 0。
- commit：待本轮整体提交
