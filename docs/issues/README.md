# AgentMate Issues 登记册

本目录只保留**活动 issue**。所有发现的问题先登记、再处理；终态记录会合并归档，但不会删除审计内容。
完整流程由 `.agents/skills/issue-tracker/SKILL.md` 定义。

## 约定

- 活动状态 `open` / `in-progress` / `deferred`：每个问题一个 `WB-<编号>-<slug>.md` 文件。
- 终态 `fixed` / `wontfix`：运行 `python scripts/archive_issues.py --apply` 后进入 [`archive/`](archive/README.md)。
- 编号全局递增且不复用；当前最大编号是 `WB-455`，可用 `python scripts/archive_issues.py --next-id` 查询。
- 活动文件 frontmatter 是权威状态；下表是活动状态镜像。

## 活动台账

> 状态：⬜ open · 🟡 in-progress · ⏸ deferred

| ID | 状态 | 严重度 | 领域 | 标题 |
|----|------|--------|------|------|
| [WB-283](WB-283-production-desktop-update-deployment-acceptance.md) | ⏸ | P1 | fullstack | 正式桌面更新服务缺少生产域名、CI 签名材料与上线验收 |
| [WB-344](WB-344-v1-controlled-user-pilot.md) | ⏸ | P1 | misc | V1.0 受控真实用户试用缺少参与者、安装版本与连续证据 |
| [WB-419](WB-419-local-test-accounts-ignore.md) | ✅ | P3 | backend | 本地 Server 测试账号凭据文件应被忽略且不入库 |
| [WB-420](WB-420-workbuddy-reference-and-design-docs.md) | ✅ | P3 | docs | 补充 WorkBuddy 参考解读与 AgentMate 设计系统文档资料 |
| [WB-423](WB-423-first-registration-admin-by-default.md) | ✅ | P2 | backend | 首个注册用户应自动成为平台管理员 |
| [WB-437](WB-437-server-first-data-migration-retirement.md) | ⬜ | P1 | misc | 存量业务数据迁移与旧同步机制退役 |

## 已关闭归档

共 445 条 `fixed` / `wontfix` 记录，按年份和编号段合并保存。详情、处理记录和原始文件名见
[`archive/README.md`](archive/README.md)。Git 历史仍可追溯迁移前的独立文件。
