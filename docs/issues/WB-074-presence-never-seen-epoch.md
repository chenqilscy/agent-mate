---
id: WB-074
title: 讨论面板在线状态：从未上线的成员显示「最后活跃 20641 天前」
severity: P3
area: frontend
status: fixed
origin: WB-067 Slice 2 缺陷（真机 E2E 发现）
files:
  - src/components/hub/HubCommentsPanel.tsx
created: 2026-07-08
---

## 问题

`HubCommentsPanel` 的在线状态气泡对离线成员显示 `最后活跃 ${ago(m.last_seen)}`。当成员从未上线
（`last_seen` 为 0/未设，如刚被加成员但没登录过），`ago(0)` 从 Unix 纪元起算 → 显示「最后活跃
20641 天前」（约 56 年），荒谬。

## 触发场景

真机 E2E：项目「讨论」tab，成员 bob 刚被 owner 加入、从未登录 → 在线状态 hover 提示「最后活跃 20641 天前」。

## 影响

P3：纯展示、不影响功能，但明显穿帮。

## 建议修法

在线状态提示对 `last_seen` 为假值时显示「从未上线」而非 `ago(0)`。

## 验证

- 真机：从未上线成员 hover → 「从未上线」；有真实 last_seen 的成员照常显示相对时间。
