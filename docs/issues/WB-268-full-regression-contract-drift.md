---
id: WB-268
title: 全量回归门禁与已落地 Ant 及项目工作台实现漂移，持续集成仍有三项失败
severity: P1
area: frontend
status: fixed
origin: WB-266 全量回归发现
files:
  - package.json:20
  - server/tests/test_console_ant_design_entry.py:15
  - server/tests/test_console_catalog_editors.py:46
  - backend/tests/regression/test_app_ant_design_migration.py:37
  - src/components/ui/IconPicker.tsx:1
created: 2026-07-21
---

## 问题

WB-266 完成定向回归后执行全量 Server/Backend 测试，仍有三项与本次工具目录无关的失败：

1. `test_console_dependencies_are_antd6_compatible` 仍要求 `antd` 依赖以 `^6.` 开头，但 WB-259 已把
   依赖固定为精确版本 `6.5.1`，测试和版本门禁目标相互矛盾。
2. `test_project_workspace_covers_all_legacy_capabilities` 仍查找旧 `TasksTab` 标记；WB-263 已迁到
   `ProjectTasks` 等 `ProjectWorkspace` 组件，测试没有随架构更新。
3. `test_visible_native_form_controls_use_ant_primitives` 检出 WB-265 新增的 `IconPicker.tsx` 含原生表单
   控件，违反现有 Ant 迁移门禁，或需要明确、审查后的组件级例外策略。

## 影响

P1：定向功能和生产构建虽然通过，但仓库完整回归仍为红色；后续无法区分真实回归与过时断言，WB-265
的共享图标控件也尚未证明符合既定组件体系和无障碍门禁。

## 建议修法

- 统一依赖策略：若以精确版本防漂移，测试应断言精确 6.x 与锁文件一致，不再要求 caret。
- 把项目工作台测试更新为稳定职责/组件/API 契约，覆盖 `ProjectTasks`、计划、负载、甘特等当前结构。
- 审查 `IconPicker` 的原生控件：优先改用 Ant 组件；若必须保留隐藏原生 input，建立最小且有理由的
  allowlist，并补键盘、标签、焦点与明暗主题测试，不能整体豁免文件。

## 验证

- `python -m unittest discover -s server/tests -p "test_*.py"` 全绿。
- `python -m unittest discover -s backend/tests/regression -p "test_*.py"` 全绿。
- `npx tsc --noEmit`、Console 类型检查和生产构建通过。

## 处理记录（2026-07-22）

- 改动：Console 依赖门禁改为断言已采用的精确 `antd 6.5.1` 与 Pro Components
  `3.1.14-2`；项目工作台契约改为覆盖 `ProjectOverview/ProjectPlan/ProjectTasks/ProjectWorkload/ProjectGantt`
  及现有工作项 API，不再查找已删除的 `TasksTab`。
- 改动：`IconPicker` 图标选项从原生 `<button>` 迁到 Ant `Button type="text"`，保留
  `aria-label`、`aria-pressed`、原生键盘焦点与选中状态；CSS 使用 `.icon-picker-option.ant-btn`
  精确覆盖 Ant 基础样式，未添加文件级门禁豁免。
- 验证：Server 全量 40/40；隔离集成态 Backend 全量 90/90（显式初始化隔离数据库并启用 mocked
  Server 契约）；`pnpm build` 完整通过。隔离 `:8110` 真页面验证 Ant Button、tabIndex、ARIA、
  780px 滚动、明暗主题与零 console error/warn；隔离进程、数据库和工作树均已清理。
- 边界：主工作树同时存在 WB-255/WB-257 的未提交验证状态，其中 updater 临时把 Tauri 版本设为
  `0.9.9`，会单独触发产品版本契约；本 issue 未覆盖或提交这些并行改动。
