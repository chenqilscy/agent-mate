---
id: WB-005
title: 启动时用后端默认模型覆盖用户已保存的选择
severity: P0
area: frontend
status: open
origin: 🆕 近期改动
files:
  - src/App.tsx:57
  - src/stores/settingsStore.ts:37
  - src/stores/settingsStore.ts:45
created: 2026-07-06
---

## 问题
`settingsStore` 初始化时从 localStorage 读 `model`（`settingsStore.ts:37`），但 bootstrap 无条件 `setModel(r.default)`（`App.tsx:57`），把用户选择覆盖并重新写回默认值。

## 触发场景
用户选模型 X → 刷新页面 → 变回后端 default。持久化形同虚设。

## 影响
用户偏好丢失，每次刷新都要重选。

## 建议修法
仅当 localStorage 无值时才应用 `r.default`：
```ts
if (r.default && !localStorage.getItem('wb.model')) setModel(r.default)
```
（或让 store 暴露「是否为用户显式设置」标志。）

## 验证
选一个非默认模型 → 刷新 → 仍是所选模型。首次访问（无 localStorage）→ 用后端 default。
