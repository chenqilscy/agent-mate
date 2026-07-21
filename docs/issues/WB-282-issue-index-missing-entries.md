---
id: WB-282
title: issue 索引漏列 WB-173～175，文件与台账状态不一致
severity: P2
area: docs
status: in-progress
origin: 集成一致性审计
files:
  - docs/issues/README.md
  - docs/issues/WB-173-weknora-backend.md
  - docs/issues/WB-174-weknora-frontend.md
  - docs/issues/WB-175-knowledge-add-tool.md
created: 2026-07-22
---

## 问题

`docs/issues/` 中 WB-173、WB-174、WB-175 三个 issue 文件均存在且 frontmatter 状态为 `fixed`，但
`docs/issues/README.md` 在 WB-172 后直接跳到 WB-176。台账索引因此无法完整反映实际 issue 集合。

## 触发场景

对所有 `WB-*.md` 的 `id`、`status` 与 README 表格状态图标执行自动一致性审计时，三条记录均被报告为
`fixed` 状态无对应索引行。

## 影响

P2。不会影响运行时功能，但会导致未完成项统计、历史检索和 issue 审计失真，也可能让后续维护者误判
WeKnora 后端、前端和 `knowledge_add` 三项工作从未登记或已经丢失。

## 建议修法

- 按编号顺序把 WB-173～175 的链接、状态、优先级、领域和摘要补回 README；
- 不修改三个已关闭 issue 的 frontmatter 与既有处理记录；
- 重新运行 issue ID 唯一性与 README 状态镜像审计，要求重复 ID 与状态缺失均为 0。

## 验证

- WB issue 文件数量与唯一 ID 数量一致；
- README 中 WB-173～175 均显示 `✅`，并与各自 `status: fixed` 一致；
- 全量状态镜像审计无遗漏。
