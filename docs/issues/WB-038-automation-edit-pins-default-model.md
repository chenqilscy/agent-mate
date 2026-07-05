---
id: WB-038
title: 编辑 model=null（跟随默认）的自动化时，保存会把它悄悄钉死到某个模型
severity: P3
area: frontend
status: fixed
origin: 🆕 近期改动
files:
  - src/views/AutomationView.tsx
created: 2026-07-06
---

## 问题

WB-036 的编辑器把 model 状态初始化为 `auto?.model ?? prefill?.model ?? defaultModel`。对一条
**旧自动化**（`model=null`，语义是「跟随后端默认模型」）点「编辑」，编辑器会用全局 `defaultModel`
（settingsStore）填充；即便只改了名字，「保存」也会把 `model` 显式写成那个值——原本「跟随默认」
被**悄悄钉死**成具体模型。属编辑无关字段的隐性副作用。

## 触发场景

1. 有一条 `model=null` 的自动化（WB-036 之前建的，或将来「跟随默认」的）。
2. 「⋯ → 编辑」，只改名称，保存。
3. 该自动化 `model` 从 `null` 变成当时的全局模型（可用 SQLite / API 回读佐证）。

## 影响

P3：仅隐性改变到点运行所用模型；无数据丢失/安全问题。但「编辑名字顺手换了模型」不符合直觉。

## 建议修法

- 编辑既有自动化时 model 状态初始化用其真实值（可为 `null`）：`auto ? auto.model : defaultModel`
  （新建才默认全局模型）。`null` 时按钮显示「跟随默认模型」（弱化态），模型 Popover 顶部加一项
  「跟随默认模型」可把它设回 `null`。
- 保存时照常把 `model` 放进 payload；配合 WB-037 的后端 `exclude_unset` + 可空列写 `None`，
  `model=null` 能被如实落库（既不误钉死、也支持显式重置回默认）。

## 验证

- 编辑 `model=null` 的自动化只改名保存 → 回读 `model` 仍为 `null`（不再钉死）。
- 显式选某模型 → 落库为该模型；再改回「跟随默认」→ 落库 `null`。
- 新建默认全局模型不受影响。

## 处理记录（2026-07-06）

- 前端：编辑器 model 初始化改为 `auto ? auto.model : (prefill?.model ?? defaultModel)`——编辑保留自动化真实
  model（可为 null），仅新建默认全局模型；null 时按钮显示「跟随默认模型」，模型 Popover 顶部加「跟随默认模型」
  项可设回 null。落库依赖 WB-037 的 `exclude_unset` + 可空列写 None。
- 验证：Playwright——编辑一条已设模型的自动化，按钮显示其真实模型（非强制默认）；模型 Popover 顶部有「跟随
  默认模型」项。后端 curl 已证 model=null 可落库、只改名不误钉死。
- commit：（尚未提交）
