---
id: WB-047
title: 「动态」tab 中执行计划项的记录只显示随手指令（如「执行它」），看不出执行的是哪个计划项
severity: P2
area: frontend
status: fixed
origin: 既有实现
files:
  - src/views/ProjectHomeView.tsx:90-94
  - src/views/ProjectHomeView.tsx:139-151
  - src/components/project/ProjectWork.tsx:234-241
  - src/stores/loadoutStore.ts:10-17
created: 2026-07-06
---

## 问题

项目工作台「动态」tab 逐条列出本项目的执行会话，每行只渲染 `s.title`（+ 发起人 + 时间），
不含任何其它信息（`src/views/ProjectHomeView.tsx:139-151`）。

而一次项目执行的标题在 `launch` 里取自 composer 里**随手输入的文本**
（`src/views/ProjectHomeView.tsx:90-94`：`startProject(project.id, text.slice(0,26))`）。

执行计划项的路径是：`待办详情`→「＋ 添加到输入框」把待办作为**引用 chip（🔖）** 注入
（`src/components/project/ProjectWork.tsx:234-241`，`addRef({ name: item.title, …, kind:'todo', itemId })`），
用户再在输入框敲一句短指令（如「执行它」）发送。按项目约定，ref**只注入本轮 LLM 输入、不进持久化的 user 消息**，
自然也不进标题（见 `CLAUDE.md` loadout/refs 铁律、`src/stores/loadoutStore.ts:10-17`）。

结果：`session.title` = 那句随手指令「执行它」，计划项的真名（如「b1-调查AI短剧行业现象」）**从未进入标题**。
动态 feed 于是显示成一串「执行它」「执行它」——既看不出执行的是哪个计划项，也没有结果/状态等其它相关信息。

## 触发场景

1. 进入某项目工作台，切到「计划」，有待办 `b1-调查AI短剧行业现象`、`b2-调查AI视频生成的方案`。
2. 点开 `b1` 待办详情 →「＋ 添加到输入框」→ 回到 composer，输入「执行它」→ 发送。
3. 对 `b2` 重复一次。
4. 切到「动态」tab → 两行都显示「执行它」，无法区分执行的是 b1 还是 b2，也没有其它信息。

## 影响

「动态」tab 是项目里「谁执行了什么」的活动流（M7 C3）。计划项执行是它最主要的内容来源，
却退化成一串无意义的短指令，用户无法从 feed 认出执行对象、追溯或点回正确的会话。
不崩、可绕开（点进去看），故 P2；但让该 tab 对计划执行基本失去信息价值。

## 建议修法

核心：让执行计划项时的会话标题能反映**计划项本身**，而不是随手指令。

- 在 `launch`（`src/views/ProjectHomeView.tsx:90-94`）里读 `useLoadoutStore.getState().refs`，
  找 `kind==='todo'` 的 ref；若存在，用其 `name`（即计划项标题）作为会话标题传给 `startProject`
  （截断沿用现有 26 字规则），否则退回现有 `text` 逻辑。用户敲的那句指令仍作为首条 user 消息正文，不丢。
- 效果：动态 feed 行显示「b1-调查AI短剧行业现象」而非「执行它」；无 todo ref 的普通执行行为不变（不回归）。

次要/可另开 issue（本 issue 不含）：动态 feed 行补一行副文本（状态/摘要），
像自动化「运行记录」那样落 `run_summary`——那需要 session 侧持久化摘要，属更大改动。

## 验证

- 复现「触发场景」：执行 b1、b2 后，「动态」tab 两行分别显示 `b1-…`、`b2-…`，可区分、可点回对应会话。
- 回归：不加待办 ref、直接在项目 composer 输入普通指令发送 → 标题仍是该指令文本（行为不变）。
- `npx tsc --noEmit` 通过；浏览器实测明暗双主题下 feed 行渲染正常、标题不溢出（沿用 WB-018 截断）。

## 处理记录（2026-07-06）

- 改动：`src/views/ProjectHomeView.tsx` 的 `launch`——发起执行前先取 `useLoadoutStore.getState().refs`
  里第一条 `kind==='todo'` 的 ref，若有则以其 `name`（计划项标题）作会话标题（沿用 26 字截断），
  否则退回原 `text` 逻辑。用户敲的指令仍作首条 user 消息，`send(text)` 不变。标题经
  `startProject` → `send` 的 `title:` 字段 → 后端 `chat.py:58` `title=(body.title or text)[:26]` 落库，
  正是「动态」feed 读的 `s.title`。
- 验证：`npx tsc --noEmit` 通过。浏览器实测（测试项目，真实后端+LLM）：
  - 新建待办「验证WB047标题-调查AI短剧」→ 待办详情「＋ 添加到输入框」→ composer 输入「执行它」发送 →
    面包屑与「动态」feed 首行均显示「验证WB047标题-调查AI短剧」（而非「执行它」），首条消息正文仍是「执行它」，
    agent 也正确识别到关联待办。旧的几条 feed 仍显示当初的随手指令（修复前遗留），对照鲜明。
  - 回归：不加待办 ref、直接输入「回归测试：无待办的普通执行」发送 → 标题仍为该文本，行为不变。
- commit：随本次提交（master，标题带 WB-047）。
