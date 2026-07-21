---
id: WB-278
title: text-3 二级文字对比度低于 WCAG AA
severity: P3
area: ui
status: wontfix
origin: 既有实现
files:
  - src/styles/tokens.css:12
  - docs/WorkBuddy/tencent-workbuddy-reference.html:16
created: 2026-07-22
---

## 问题
浅色主题 `--text-3: #9AA0A6` 对白底对比度约 2.64:1，低于 WCAG AA 普通文字 4.5:1。占位符、时间戳和空态广泛使用该 token。

## 触发场景
浅色主题下阅读使用 `--text-3` 的小字号辅助文字，低视力或低质量显示设备上辨识困难。

## 影响
P3。存在无障碍差距，但不影响数据与执行功能。

## 建议修法
若产品明确把 WCAG AA 提升为高于原型保真的目标，应统一重定浅/暗主题三级文字 token，并做全页面视觉回归；不应在单个组件局部改色。

## 验证
- 核算浅色 token 对白底的对比度。
- 对照参考原型与项目“视觉零重设计”约束确认取舍。
- 若未来重开，需全页面明暗主题视觉验收。

## 处理记录（2026-07-22）
- 结论：当前 `#9AA0A6` 对白底实算约 2.64:1，问题属实；同时该值逐字来自 WorkBuddy 参考原型，且项目铁律要求“视觉零重设计”。单点或擅自全局加深都会违反当前交付契约，因此本轮不改代码，标记 `wontfix`。
- 重开条件：产品明确授权以 WCAG AA 优先于原型保真，并接受浅/暗主题全局三级文字 token 重定与全页面视觉回归。
- 验证：`src/styles/tokens.css` 与 `docs/WorkBuddy/tencent-workbuddy-reference.html` 均为 `#9AA0A6`；sRGB 相对亮度公式核算对白底为 2.6405:1。
- commit：本提交。
