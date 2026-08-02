# AgentMate Issues 登记册

本目录只保留**活动 issue**。所有发现的问题先登记、再处理；终态记录会合并归档，但不会删除审计内容。
完整流程由 `.agents/skills/issue-tracker/SKILL.md` 定义。

## 约定

- 活动状态 `open` / `in-progress` / `deferred`：每个问题一个 `WB-<编号>-<slug>.md` 文件。
- 终态 `fixed` / `wontfix`：运行 `python scripts/archive_issues.py --apply` 后进入 [`archive/`](archive/README.md)。
- 编号全局递增且不复用；当前最大编号是 `WB-364`，可用 `python scripts/archive_issues.py --next-id` 查询。
- 活动文件 frontmatter 是权威状态；下表是活动状态镜像。

## 活动台账

> 状态：⬜ open · 🟡 in-progress · ⏸ deferred

| ID | 状态 | 严重度 | 领域 | 标题 |
|----|------|--------|------|------|
| [WB-283](WB-283-production-desktop-update-deployment-acceptance.md) | ⏸ | P1 | fullstack | 正式桌面更新服务缺少生产域名、CI 签名材料与上线验收 |
| [WB-344](WB-344-v1-controlled-user-pilot.md) | ⏸ | P1 | misc | V1.0 受控真实用户试用缺少参与者、安装版本与连续证据 |
| [WB-359](WB-359-scheduler-observability.md) | ⬜ | P1 | backend | Scheduler 扫描与 Server outbox 异常被静默吞掉 |
| [WB-360](WB-360-ci-hermetic-quality-gate.md) | ⬜ | P1 | misc | 完整 V1 质量门禁未自动执行且测试依赖在线模型下载 |
| [WB-361](WB-361-server-external-integration-relay.md) | ⬜ | P1 | backend | Server 缺少面向外部系统的服务身份与设备投递中继 |
| [WB-362](WB-362-federated-sso-auth-hardening.md) | ⬜ | P1 | fullstack | Server 缺少微信 Google Telegram 联合登录与公网鉴权加固 |
| [WB-363](WB-363-versioned-migrations-and-architecture-docs.md) | ⬜ | P2 | backend | 数据库升级缺少版本化迁移且架构文档已漂移 |

## 已关闭归档

共 356 条 `fixed` / `wontfix` 记录，按年份和编号段合并保存。详情、处理记录和原始文件名见
[`archive/README.md`](archive/README.md)。Git 历史仍可追溯迁移前的独立文件。
