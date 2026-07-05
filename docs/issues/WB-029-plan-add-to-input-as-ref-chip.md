---
id: WB-029
title: 计划 · 「添加到输入框」应作为独立引用 chip 显示，而非混入正文文本
severity: P2
area: ui
status: fixed
origin: 🆕 近期改动
files:
  - src/components/project/ProjectWork.tsx
  - src/components/composer/Composer.tsx
  - src/stores/loadoutStore.ts
  - src/stores/uiStore.ts
created: 2026-07-06
---

## 问题

WB-026 落地的待办详情「＋ 添加到输入框」当前把 `标题+描述` 直接**塞进 Composer 文本域**
（经 `uiStore.composerPrefill`）。纯文本混进 textarea 后，与用户自己敲的内容**无法区分**，
也不能单独移除。目标设计里，添加进来的待办应显示成一枚**独立的引用 chip**（见截图：
`🔖 test`、`🔖 tefddsafdasdfsafadsst`），与正文和其它 chip 有明显区分。

## 触发场景

项目 → 计划 → 点卡片 → 待办详情「＋ 添加到输入框」：内容以纯文本形式落入输入框正文，
和已输入文字连成一片，无独立标识、不可单独删。

## 影响

P2：可用性/可读性缺口。用户分不清哪些是「加进来的待办」、哪些是自己打的字，也无法只撤掉待办。

## 建议修法

- 复用 Composer 既有的**引用（refs）机制**（`loadoutStore.refs` + `.cloadout` chip），
  让「添加到输入框」调用 `addRef` 而非写入文本域：`addRef({ name: 标题, content: 标题+描述, kind: 'todo' })`。
  refs 已在发送时真实注入 LLM 输入并于成功后清空（`chatStore` line 214/226，WB-006），是本需求的正确语义。
- `AttachedRef` 增可选 `kind?: 'file' | 'todo'`；Composer 的 refs chip 按 kind 换图标
  （todo → 🔖，file → 📎，默认 file，保持 RefPicker/添加文件 不变）。
- 移除本功能不再使用的 `uiStore.composerPrefill`/`setComposerPrefill` 与 Composer 里对应的消费 effect（避免死代码）。
- 视觉零重设计：沿用 `.np-chip`/`.cloadout`，暗色随既有覆盖。

## 验证

- `npx tsc --noEmit` 过。
- 浏览器实测：点「添加到输入框」→ Composer 出现 `🔖 待办标题` chip，与正文/文件 chip 有区分、可单独 × 删除；
  发送后 chip 随 refs 清空；待办内容真实进入本轮 LLM 输入。明暗双主题 chip 可读。

## 处理记录（2026-07-06）
- 改动：`loadoutStore.AttachedRef` 增可选 `kind?: 'file'|'todo'`；`Composer` refs chip 按 kind 换图标（todo→🔖、file→📎）并加 `.ref-todo` class；`ProjectWork.TodoDetailModal.addToInput` 改为 `addRef({name:标题, content:标题+描述, kind:'todo'})`（不再写文本域）；移除 WB-026 引入、现已无用的 `uiStore.composerPrefill`/`setComposerPrefill` 及 Composer 消费 effect；`app.css` 加 `.cloadout .np-chip.ref-todo` 品牌色调样式。
- 验证：`npx tsc --noEmit` 过；Playwright 实测点「添加到输入框」→ Composer 出现独立 `🔖 待办标题` 品牌色 chip，与正文/文件引用区分、可单独 × 删除，文本域不再被污染；随 refs 于发送后清空、真实进入本轮 LLM 输入（chatStore:214/226）；明暗双主题 chip 均可读。
- commit：（待提交）
