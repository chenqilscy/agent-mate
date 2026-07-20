---
id: WB-212
title: Issue 索引来源段落仍引用更名前的架构文档路径
severity: P2
area: misc
status: fixed
origin: 🆕 近期改动
files:
  - docs/issues/README.md:237
created: 2026-07-20
---

## 问题

WB-210 完成 Server/Console 重命名后，`docs/issues/README.md` 的来源说明仍链接到已更名的 `agentmate-hub-架构设计.md` 和 `buddywebmgr-管理门户设计.md`，链接目标已经不存在。

## 触发场景

在 issue 索引底部点击 WB-058～063 或 WB-078～084 的总设计链接，会跳到不存在的文件。

## 影响

P2：不影响运行时，但破坏问题台账到架构决策文档的可追溯性。

## 建议修法

保留历史背景表述，将链接目标更新为当前的 `agentmate-server-架构设计.md` 和 `agentmate-console-管理门户设计.md`。

## 验证

两条 Markdown 相对链接均能解析到仓库内现存文件。

## 处理记录（2026-07-20）

- 改动：将 issue 索引来源说明中的 Server/Console 架构文档链接更新为当前文件名，并同步修正 WB-078 台账行中的旧设计文档路径文本。
- 验证：旧路径在 `docs/issues/README.md` 中已清零；两个新目标文件均存在，Markdown 相对链接可解析。
- commit：随本提交。
