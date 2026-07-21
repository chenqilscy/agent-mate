---
id: WB-259
title: Ant Design 依赖声明与精确版本门禁漂移，完整回归持续失败
severity: P2
area: frontend
status: fixed
files:
  - package.json:25
  - pnpm-lock.yaml:27
  - backend/tests/regression/test_app_ant_design_migration.py:15
created: 2026-07-21
---

## 问题

`package.json` 与 lockfile 把 Ant Design 声明为 `^6.5.1`，而 UI 迁移回归明确要求生产依赖精确锁定为
`6.5.1`。因此完整 regression 在 `test_versions_are_pinned` 稳定失败。

## 触发场景

运行 `python -m unittest tests.regression.test_app_ant_design_migration -v`。

## 影响

P2：发布门禁无法全绿；caret 范围还允许后续安装静默升级到未验收的 Ant Design 次版本，与锁定策略冲突。

## 建议修法

把 `package.json` 与 `pnpm-lock.yaml` 的 specifier 都恢复为精确 `6.5.1`，安装产物版本保持 6.5.1，
然后重跑 Ant Design 定向测试、前端类型检查和生产构建。

## 验证

- `test_app_ant_design_migration` 全部通过；
- `pnpm install --lockfile-only --frozen-lockfile` 不产生差异；
- `npx tsc --noEmit` 与 `npx vite build` 通过。

## 处理记录（2026-07-21）

- 改动：`package.json` 与 `pnpm-lock.yaml` 的 Ant Design specifier 统一恢复为精确 `6.5.1`，已安装版本不变。
- 验证：`pnpm install --lockfile-only --frozen-lockfile` 无差异；Ant Design 4 项定向回归、TypeScript 检查与 Vite 生产构建通过。
- 提交：登记提交 `8bd8e75`；修复提交见本次 WB-259 交付。
