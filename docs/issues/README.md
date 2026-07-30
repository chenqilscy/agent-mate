# AgentMate Issues 登记册

本目录只保留**活动 issue**。所有发现的问题先登记、再处理；终态记录会合并归档，但不会删除审计内容。
完整流程由 `.agents/skills/issue-tracker/SKILL.md` 定义。

## 约定

- 活动状态 `open` / `in-progress` / `deferred`：每个问题一个 `WB-<编号>-<slug>.md` 文件。
- 终态 `fixed` / `wontfix`：运行 `python scripts/archive_issues.py --apply` 后进入 [`archive/`](archive/README.md)。
- 编号全局递增且不复用；当前最大编号是 `WB-338`，可用 `python scripts/archive_issues.py --next-id` 查询。
- 活动文件 frontmatter 是权威状态；下表是活动状态镜像。

## 活动台账

> 状态：⬜ open · 🟡 in-progress · ⏸ deferred

| ID | 状态 | 严重度 | 领域 | 标题 |
|----|------|--------|------|------|
| [WB-283](WB-283-production-desktop-update-deployment-acceptance.md) | ⏸ | P1 | fullstack | 正式桌面更新服务缺少生产域名、CI 签名材料与上线验收 |
| [WB-307](WB-307-project-instruction-object-text.md) | ⬜ | P2 | ui | Console 项目列表将项目说明渲染为 object Object |
| [WB-337](WB-337-skill-usage-governance.md) | ⬜ | P2 | backend | Skill 只有 release 聚合结果，缺少用户侧使用价值与陈旧治理 |
| [WB-338](WB-338-skill-bundles-environment-gates.md) | ⬜ | P2 | backend | Skill 缺少命名组合与平台环境适用性门禁 |

## 已关闭归档

共 333 条 `fixed` / `wontfix` 记录，按年份和编号段合并保存。详情、处理记录和原始文件名见
[`archive/README.md`](archive/README.md)。Git 历史仍可追溯迁移前的独立文件。
