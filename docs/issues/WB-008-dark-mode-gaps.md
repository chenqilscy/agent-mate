---
id: WB-008
title: 暗色主题遗漏（btn-dark:disabled / add-btn / mrow.off）
severity: P1
area: ui
status: open
origin: 🏚 迁移遗留
files:
  - src/styles/app.css:526
  - src/styles/app.css:265
  - src/styles/app.css:306
created: 2026-07-06
---

## 问题
上一批暗色修复（toast/btn-dark:not(:disabled)/cat.active/pe-badge/cstop/model chip）已覆盖大部分，但仍有三处遗漏：

1. **`.btn-dark:disabled`（`app.css:526`）**：暗色只覆盖了 `:not(:disabled)`，禁用态仍走 `background:#C9CDD3`（浅灰）+ `.btn-dark` 的 `color:#fff` → 白字浅灰底，对比≈1.4，几乎读不出。触发：新建项目弹窗标题为空时的「确定」。
2. **`.add-btn`（`app.css:265`）**：`background:#fff` 无 `body.dark` 覆盖 → 暗色卡片（#22272D）上出现纯白按钮。触发：专家·技能·连接器视图技能卡右上的添加按钮。
3. **`.mrow .off`（`app.css:306`）** [低]：`color:#E5484D; background:#FDECEC` 硬编码无暗色变体，暗色弹层上呈浅粉底红字，能读但不融主题。触发：模型选择器里带「限时折扣」徽标的模型。

## 建议修法
```css
body.dark .btn-dark:disabled { background:#3A414B; color:var(--text-3); }
body.dark .add-btn { background:#22272D; }
body.dark .mrow .off { background:#3A2326; color:#F98A8E; }
```

## 验证
暗色主题下逐一查看：新建项目空标题「确定」、专家视图添加按钮、模型选择器折扣徽标，均对比清晰、融入主题。
