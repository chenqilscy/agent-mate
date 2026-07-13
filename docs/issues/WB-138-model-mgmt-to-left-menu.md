---
id: WB-138
title: 模型管理入口从输入框「配置模型」改到左侧「更多」菜单
severity: P2
area: frontend
status: fixed
origin: 用户反馈
files:
  - src/components/composer/ModelPicker.tsx:63
  - src/components/composer/Composer.tsx:42
  - src/components/layout/Sidebar.tsx:295
  - src/components/layout/Sidebar.tsx:448
---

## 问题

模型管理（`ModelConfigModal`，全局 `uiStore.modelConfigOpen`）当前有两处入口：

- 输入框模型下拉底部的「配置模型」项（[ModelPicker.tsx:63](../../src/components/composer/ModelPicker.tsx#L63)，经 `onConfigure` 回到 Composer 开弹窗）；
- 底部账号头像弹出菜单里的「模型管理」行（[Sidebar.tsx:448](../../src/components/layout/Sidebar.tsx#L448)）。

用户希望：模型管理是全局设置，入口应在**左侧导航菜单**里，而**不再**塞在选择模型的下拉里当「配置模型」——那里应只做选模型这一件事。

## 触发场景

用户在输入框切模型时，下拉底部混着一个「配置模型」的设置入口，语义混杂；想找模型管理时也不该先去点模型下拉。

## 影响

P2：交互语义问题，非功能缺陷。弹窗与全局 flag 都现成，只是入口位置需要挪。

## 建议修法

- **左侧「更多」弹出菜单**加「模型管理」项（`setView` 无关，直接 `setModelConfigOpen(true)` + 关菜单），复用既有 `more-item` 样式与一个齿轮/滑块图标。
- **移除输入框模型下拉的「配置模型」**：删掉 `ModelPicker` 里的 `pop-div` + `pop-item`「配置模型」及 `onConfigure` prop；`Composer` 去掉传参与不再使用的 `openModelConfig`。空态文案由「点下方『配置模型』…」改为指向左侧「更多 · 模型管理」。
- **账号菜单**的「模型管理」行移除（改由「更多」承载，避免重复入口）。
- **后端文案收尾**：`runtime.py` 三处用户可见报错还写「请在『配置模型』里…」，入口改名后会指向不存在的东西——统一改为「模型管理」。

## 验证

- `npx tsc --noEmit` 过。
- 左侧「更多」菜单出现「模型管理」，点开即弹出 `ModelConfigModal`；账号菜单不再有该行。
- 输入框模型下拉不再有「配置模型」项；无可用模型时空态文案指向「更多 · 模型管理」。
- 明暗双主题看「更多」菜单新项样式协调（复用 `more-item`）。

## 处理记录

- 2026-07-14 fixed。按「建议修法」实现：
  - [Sidebar.tsx](../../src/components/layout/Sidebar.tsx)「更多」菜单加「模型管理」项（`setModelConfigOpen(true)` + 关菜单），移除账号菜单里的「模型管理」行。
  - [ModelPicker.tsx](../../src/components/composer/ModelPicker.tsx) 删「配置模型」`pop-item`/`pop-div` 与 `onConfigure` prop，空态文案改指向「更多 · 模型管理」。
  - [Composer.tsx](../../src/components/composer/Composer.tsx) 去掉 `openModelConfig` 与 `ModelPicker` 的 `onConfigure` 传参。
  - [runtime.py](../../backend/agent/runtime.py) 三处报错文案「配置模型」→「模型管理」。
  - 验证：`npx tsc --noEmit` 过。
