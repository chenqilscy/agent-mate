# AgentMate 文档导航

> 本目录只维护一套“当前方案”。历史决策、阶段计划和完成度快照由 Git 与
> [`issues/archive/`](issues/archive/README.md) 保存，不再与当前架构并列展示。

## 当前权威文档

| 文档 | 用途 | 权威范围 |
|---|---|---|
| [`agentmate-server-first-架构设计.md`](agentmate-server-first-架构设计.md) | 产品定位、组件职责、运行与安全架构 | Console、App、Local Agent、Server 的总体边界 |
| [`agentmate-数据分层与同步规范.md`](agentmate-数据分层与同步规范.md) | 数据归属、离线、WAL/ACK、秘密与资产规则 | 新实体和数据传输的强制约束 |
| [`agentmate-console-管理门户设计.md`](agentmate-console-管理门户设计.md) | Console 信息架构与管理边界 | 系统、组织、项目、目录和审计治理 |
| [`agentmate-v1-release-candidate.md`](agentmate-v1-release-candidate.md) | 发布和真实试用门禁 | 版本声称与验收证据 |
| [`external-system-integration.md`](external-system-integration.md) | 外部 API、事件、MCP 与渠道接入选择 | 外部系统集成边界 |

发生冲突时，优先级为：数据规范 → Server-first 架构 → 专项设计 → 运维指南。
实现完成度以当前代码、自动化验证和 [`issues/`](issues/README.md) 为准，文档中的能力名称本身不构成完成证据。

## 运维与部署指南

- [`desktop-build.md`](desktop-build.md)：桌面构建、签名、更新与安装包。
- [`server-first-migration-runbook.md`](server-first-migration-runbook.md)：存量数据迁移和旧机制退役。
- [`sso-deployment.md`](sso-deployment.md)：Server 联合登录部署。
- [`langfuse-observability.md`](langfuse-observability.md)：本机可观测性配置。
- [`weknora-部署.md`](weknora-部署.md)：自托管知识库接入。

## 参考与证据

- [`WorkBuddy/`](WorkBuddy/README.md)：腾讯 WorkBuddy 公开资料和设计参考，**不是 AgentMate 实现契约**。
- [`evaluations/`](evaluations/)：特定 issue/版本的评估证据，不代表当前版本自动通过。
- [`superpowers/`](superpowers/)：历史设计过程材料，不高于当前设计系统和产品架构。
- [`issues/archive/`](issues/archive/README.md)：已关闭问题及阶段决策的审计记录。

## 维护规则

1. 不新增另一份“总体实现方案”或“功能规划 vN”；总体变化直接修改权威架构并登记 issue。
2. 阶段性评估写入 `evaluations/` 或 issue 处理记录，注明 commit、日期和验证范围。
3. 已被替代的方案直接删除；需要审计时查 Git，不在当前目录保留会被误读的副本。
4. 未实现能力必须明确标为未实现或活动 issue；已实现能力必须能指向真实代码和验证。
5. 文档不得要求把个人模型、MCP、连接器或渠道凭据同步到 Server。
