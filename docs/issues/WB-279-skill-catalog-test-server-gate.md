---
id: WB-279
title: Skill catalog 同步回归未开启 Server gate
severity: P2
area: test
status: fixed
origin: 🆕 近期改动
files:
  - backend/tests/regression/test_skill_catalog_contract.py:379
created: 2026-07-22
---

## 问题
目录同步测试 mock 了 Server client，却未设置 `AGENTMATE_SERVER_URL`。`pull_catalog` 在 client 调用前按 `settings.server_enabled` 短路，测试拿到 `{reachable:false}` 后误报缺 `revision`。

## 触发场景
默认纯本地环境运行全量 regression，`test_catalog_sync_persists_revision_and_incompatibility` 报 `KeyError: revision`。

## 影响
P2。产品行为无误，但离线全量门禁持续红灯，掩盖真实回归。

## 建议修法
测试在 mock Server 快照期间显式设置非空 Server URL，覆盖它声称验证的已启用同步路径。

## 验证
- 该测试文件独立运行通过。
- 全量 backend regression 不再出现 revision 错误。

## 处理记录（2026-07-22）
- 改动：目录同步契约测试用例显式 patch 非空 `AGENTMATE_SERVER_URL`，让被 mock 的 snapshot client 路径真实可达；测试结束自动恢复纯本地设置。
- 验证：测试文件编译通过；`test_skill_catalog_contract` 15/15 通过。
- commit：本提交。
