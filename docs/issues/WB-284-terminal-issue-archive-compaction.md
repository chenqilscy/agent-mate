---
id: WB-284
title: 已关闭 issue 单文件长期堆积导致台账难以浏览和维护
severity: P2
area: misc
status: open
origin: 既有实现
files:
  - docs/issues/README.md:1
  - .agents/skills/issue-tracker/SKILL.md:9
created: 2026-07-22
---

## 问题

`docs/issues/` 当前包含 282 个独立 issue 文件和一个索引，其中绝大多数已经是 `fixed`/`wontfix`，
但仍与活动 issue 平铺在同一目录。文件浏览、全文检索、索引核对和后续编号管理都被大量终态记录干扰。

## 触发场景

维护者打开 `docs/issues/` 查找当前待处理项，或让自动化扫描活动 issue 时，需要先穿过数百个已关闭文件；
README 也长期保留数百行终态记录，活动项不易识别。

## 影响

P2：不影响运行时功能，但持续增加文档维护成本，容易造成状态镜像遗漏、重复登记和过时链接。

## 建议修法

- 活动 issue（`open`/`in-progress`/`deferred`）继续保持一个文件一条记录；
- 终态 issue（`fixed`/`wontfix`）按编号段合并到 `docs/issues/archive/<year>/`，保留完整正文、元数据和稳定 `#wb-###` 锚点；
- 根索引只展示活动项和归档入口，归档索引保存终态摘要；
- 提供确定性的归档脚本和校验模式，统一更新仓库内相对链接；
- 更新 issue-tracker、AGENTS/CLAUDE 约定，后续关闭 issue 时自动进入归档。

## 验证

- `docs/issues/` 根目录只包含活动 issue 与 README；
- 每个历史 ID 在归档中恰好出现一次，活动/归档数量之和等于迁移前数量；
- 仓库内 Markdown 相对链接不存在指向已删除 issue 文件的情况；
- 归档脚本重复运行无差异，`--check` 通过；
- WB-283 仍可作为活动项正常流转，新 issue 仍取最大编号 +1。
