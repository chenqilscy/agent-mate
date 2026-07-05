---
id: WB-004
title: RefPicker「＋」按钮浅色主题下白字白底不可见
severity: P0
area: ui
status: open
origin: 🆕 近期改动
files:
  - src/components/composer/RefPicker.tsx:78
  - src/styles/app.css:536
  - src/components/project/NewProjectModal.tsx:177
created: 2026-07-06
---

## 问题
`.ckc`（`app.css:536`）未选中态是透明背景 + `color:#fff`。RefPicker 却常驻渲染白色 `＋`（`RefPicker.tsx:78`：`{busy===f.path ? '…' : '＋'}`）。浅色（默认）主题下模态框是白底 → 白色 ＋ 完全不可见，只剩一圈极浅描边。

对照：同一 `.ckc` 在 `NewProjectModal.tsx:177` 的正确用法是 `{on ? '✓' : ''}` —— 未选中为空，选中才有 brand 底衬托白 ✓。RefPicker 复用时破坏了这个前提。

## 触发场景
浅色主题 / 「引用对话中的文件」弹窗 / 每一行文件右侧的添加图标。暗色主题（深底）下反而正常。整行仍可点击，属可见性/可供性缺陷而非功能阻断。

## 影响
用户看不到「可添加」的可供性，交互引导缺失。

## 建议修法
未选中态给 `.ckc` 设 `color: var(--text-3)`（或去掉常驻 ＋、仅 hover/busy 时显示），让加号在浅底可见。注意别影响 NewProjectModal 里 `.ckc` 的 ✓ 表现。

## 验证
浅色主题打开「引用对话中的文件」，每行右侧应能看到清晰的 ＋（或 hover 显现）。
