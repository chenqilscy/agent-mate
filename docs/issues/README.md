# AgentMate Issues 登记册

本目录只保留**活动 issue**。所有发现的问题先登记、再处理；终态记录会合并归档，但不会删除审计内容。
完整流程由 `.agents/skills/issue-tracker/SKILL.md` 定义。

## 约定

- 活动状态 `open` / `in-progress` / `deferred`：每个问题一个 `WB-<编号>-<slug>.md` 文件。
- 终态 `fixed` / `wontfix`：运行 `python scripts/archive_issues.py --apply` 后进入 [`archive/`](archive/README.md)。
- 编号全局递增且不复用；当前最大编号是 `WB-386`，可用 `python scripts/archive_issues.py --next-id` 查询。
- 活动文件 frontmatter 是权威状态；下表是活动状态镜像。

## 活动台账

> 状态：⬜ open · 🟡 in-progress · ⏸ deferred

| ID | 状态 | 严重度 | 领域 | 标题 |
|----|------|--------|------|------|
| [WB-283](WB-283-production-desktop-update-deployment-acceptance.md) | ⏸ | P1 | fullstack | 正式桌面更新服务缺少生产域名、CI 签名材料与上线验收 |
| [WB-344](WB-344-v1-controlled-user-pilot.md) | ⏸ | P1 | misc | V1.0 受控真实用户试用缺少参与者、安装版本与连续证据 |
| [WB-374](WB-374-runtime-permission-enforcement.md) | 🟡 | P0 | backend | 工具权限仅记录未执行门禁且后台外部输入可调用高权限工具 |
| [WB-375](WB-375-sso-popup-window-contract.md) | ⬜ | P1 | frontend | SSO 弹窗使用 noopener 后错误依赖 WindowProxy 返回值 |
| [WB-376](WB-376-relay-queued-ack.md) | ⬜ | P1 | backend | Relay 本地执行仅排队时被错误 ACK 为失败 |
| [WB-377](WB-377-relay-retention-supervision.md) | ⬜ | P1 | backend | Relay 周期清理一次异常后永久停止且健康检查无感知 |
| [WB-378](WB-378-stale-run-recovery.md) | ⬜ | P1 | backend | 进程崩溃后普通会话 Run 永久停留在活动状态 |
| [WB-379](WB-379-server-revocation-window.md) | ⬜ | P1 | backend | Server 账号撤销与 App 长期离线令牌缓存语义冲突 |
| [WB-380](WB-380-thread-tool-cancellation.md) | 🟡 | P2 | backend | 同步线程工具超时取消后仍可能继续产生副作用 |
| [WB-381](WB-381-ask-user-recovery.md) | ⬜ | P2 | backend | ask_user 断流泄漏等待对象且无法恢复待回答检查点 |
| [WB-382](WB-382-auth-audit-coverage.md) | ⬜ | P2 | backend | 平台管理员变更及 SSO 身份操作缺少认证审计 |
| [WB-383](WB-383-sso-key-rotation-readiness.md) | ⬜ | P2 | backend | SSO 密钥无版本轮换且就绪检查不能发现解密失败 |
| [WB-384](WB-384-compaction-degraded-state.md) | ⬜ | P2 | backend | 长会话摘要失败静默丢弃旧上下文且无降级状态 |
| [WB-385](WB-385-durable-run-plan.md) | ⬜ | P2 | fullstack | 会话任务列表仅为文本 trace 无稳定状态和恢复能力 |
| [WB-386](WB-386-model-governance.md) | ⬜ | P2 | fullstack | 模型配置缺少组织策略预算健康检查和受控故障转移 |

## 已关闭归档

共 370 条 `fixed` / `wontfix` 记录，按年份和编号段合并保存。详情、处理记录和原始文件名见
[`archive/README.md`](archive/README.md)。Git 历史仍可追溯迁移前的独立文件。
