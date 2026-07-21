---
id: WB-271
title: 重名附件被静默丢弃却仍提示添加成功
severity: P3
area: frontend
status: fixed
origin: 🏚 迁移遗留
files:
  - src/stores/loadoutStore.ts:10
  - src/components/composer/Composer.tsx:82
created: 2026-07-22
---

## 问题
附件仅以展示名去重，两个不同来源的同名文件会丢弃第二个，但调用方仍显示“已添加”。若直接放开重名，现有按名称删除和 React key 也无法区分两个 chip。

## 触发场景
先后选择两个都叫 `notes.md`、内容不同的本地文件，第二次仍出现成功 toast，但输入区只有第一个附件。

## 影响
P3。用户可能误以为第二份资料已经提供给模型。

## 建议修法
为每个附件生成内部唯一 ID；只去重名称、内容、类型、关联项均相同的重复引用，并让 `addRef` 返回是否加入。所有入口据此显示真实反馈，删除改按 ID。

## 验证
- 同名不同内容的两个附件都保留且 ID 不同。
- 完全相同附件第二次加入返回 false，数量不增加。
- 删除其中一个重名附件不影响另一个。
- `npx tsc --noEmit` 通过。

## 处理记录（2026-07-22）
- 改动：附件增加内部 UUID；完全相同的引用才去重，`addRef` 返回真实加入结果；本地文件、工作区文件、待办三个入口按结果显示成功或“已添加过”，chip 按 ID 单独删除。
- 验证：`npx tsc --noEmit` 通过；真实 Chromium/Vite 页面调用 store，两个同名不同内容附件返回 `[true,true]` 且 ID 不同，完全重复返回 `false`，删除第一个后第二个仍保留。
- commit：本提交。
