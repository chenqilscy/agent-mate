# AgentMate 数据归属与传输规范

> 状态：当前强制规范，更新于 2026-08-10。适用于所有新增和修改；迁移兼容代码不得成为新功能样板。

## 1. 五条红线

1. **持久业务数据只由 Server 权威。** App 与 Console 使用同一业务模型和权限结果。
2. **Local Agent 不是业务 Server。** 本地只保存设备秘密、权限、执行工作集、working copy、未 ACK WAL 和可重建缓存。
3. **不做通用双向同步。** 业务写直接提交 Server；执行结果通过 Run event 和 asset commit 进入 Server。
4. **离线不产生业务分叉。** 只读缓存可以展示；只有已领取且 lease 有效的 Run 可以继续。
5. **秘密跟随执行位置。** 个人本机 secret 留 Local Agent，Server deployment secret 留 Server，任何目录或事件都不能搬运它们。

## 2. 数据归属

| 数据 | 权威 | 本机允许保存 | 离线行为 |
|---|---|---|---|
| 账号、组织、成员、角色、邀请 | Server | token 的加密绑定和显示缓存 | 不登录、不改权限 |
| 项目、任务、里程碑、Sprint、评论和审计 | Server | 只读、带版本缓存 | 可显示缓存，不写 |
| Session、消息、Run、事件、交付和验收 | Server | 当前执行工作集、lease、未 ACK WAL | 有效 lease 内继续 |
| 自动化、助理、渠道定义和团队策略 | Server | 当前执行所需快照 | 不创建、不编辑 |
| Catalog、Skill release、兼容策略 | Server | 已验证安装包/定义缓存 | 使用 last-known-good，不改策略 |
| 项目资产与正式产物 | Server + object storage | working copy 和下载缓存 | 只保留“仅本机”状态 |
| LLM/MCP/连接器/渠道个人凭据 | Local Agent | 加密权威 | 仅当前设备可用 |
| OS 权限、真实路径、浏览器 profile | Local Agent | 设备绑定权威 | 仅当前设备可用 |
| PID、进程句柄、执行门、临时目录 | Local Agent runtime | 当前执行期 | 按 lease/checkpoint 恢复 |

## 3. Server 业务写

- 成功响应必须代表 Server 事务已提交；不能先写本地再后台补传。
- 创建使用幂等键；同 key 改 payload 返回冲突，超时后查询原结果。
- 更新使用实体 version/ETag；陈旧写失败，不能在 App 静默覆盖。
- 项目权限由 Server 最终判定；前端隐藏按钮和本地角色缓存只用于体验优化。
- 删除、验收、发布、撤回等关键动作与审计在同一权威事务中完成。

## 4. Run、lease 与 WAL

每个执行事件包含：

```text
event_id / run_id / device_id / lease_id / lease_epoch
sequence / event_type / occurred_at / payload / payload_hash
```

- Local Agent 先原子追加 WAL，再发送；网络重试重发相同事件。
- Server 对 `event_id` 和 `(run_id, lease_epoch, sequence)` 双重去重，返回连续 ACK 高水位。
- sequence gap、hash 变化、旧 epoch 或外部 lease 均拒绝。
- 暂停不是终态：活动设备保持 lease 和协程执行门，暂停墙钟时间不计入活跃执行超时；设备丢失且没有可验证 checkpoint 时禁止自动新建 epoch 重放，原 Run fail closed，用户只能显式重试为新 Run。
- 取消是终态；重试创建新 Run 并记录 `retry_of`。
- ACK 后才能清除 WAL；诊断清理不得删除未 ACK 事件。

## 5. 文件与资产

1. 用户选择的任意本机文件默认是设备本地引用，不自动上传。
2. Run working copy 可读写中间文件，但 UI 必须区分“仅本机 / 上传中 / 已提交”。
3. 上传使用临时对象或分片；Server 校验 owner、project、run、hash、size 和 content type 后才提交版本。
4. 正式交付必须引用 Server asset；事件 JSON 不内嵌二进制、绝对路径或无限长 stdout。
5. 删除 Server asset 不自动删除用户原始外部文件；本机缓存按独立策略回收。

## 6. Secret 与配置

- 设备私钥、Server/Device token、模型 key、MCP/连接器 secret 使用 OS secure storage 或本机加密存储。
- 前端读取接口只返回 `configured/has_secret`，不回显 secret。
- stdio MCP 只继承安全基础环境和该实例声明的 secret；禁止透传整个 Local Agent 环境。
- HTTP/SSE MCP 的 credential 只作为该实例声明的 Header 注入。
- secret 不进入日志、WAL、Server request snapshot、工具 trace、普通导出或 Git。
- Server 可以保存非敏感 credential reference、设备 capability 和健康原因，但不能借此获得秘密本身。

## 7. 缓存与失效

- 缓存必须只读、可删除重建、带版本和更新时间。
- Server 不可达与实体已删除/撤权是不同状态；不可达保留 last-known-good，tombstone/撤权立即失效。
- 不能使用 `origin=local/server`、`server_dirty`、LWW 或冲突台账为新实体建立双主。
- Local Agent 诊断缓存、连接器健康和 worker 状态不升级为业务真相。

## 8. 离线矩阵

| 操作 | Server 不可达 |
|---|---|
| 查看已缓存项目、任务、Session、Run | 允许只读，显示缓存时间 |
| 新建或修改业务实体 | 禁止并明确提示未保存 |
| 发起新 Run | 禁止，除非 Server 已创建并授予 lease |
| 继续已领取 Run | lease 和本机策略允许时继续，事件写 WAL |
| pause/resume/cancel | 命令未被 Server 接受前不得伪报成功 |
| 创建本机临时文件 | 允许，标记为未上传 |
| 修改本机模型、MCP 和设备设置 | 允许，只影响当前设备 |

## 9. 新实体判断

依次判断：

1. 跨会话或跨设备保留的业务状态 → Server。
2. 本机秘密、OS 权限、真实路径、运行中进程 → Local Agent。
3. 未 ACK 执行事件 → Local WAL，ACK 后 Server 是正式记录。
4. 正式文件/产物 → Server + object storage；执行副本 → Local Agent。
5. 纯性能数据 → 可删除的只读缓存。

无法明确归属时停止实现并更新架构决策，不得通过“先放本地以后再同步”绕过。

## 10. 存量退役

WB-437 处理旧本地业务表、pull/outbox、镜像字段和冲突机制。退役期间：

- 迁移源库只读，先做加密一致备份；
- 导入使用稳定映射、幂等键和权限 readback；
- 单类切换后禁止旧客户端重新写入；
- 兼容表只读观察后删除；
- 回滚不恢复双主。

运行步骤见 [`server-first-migration-runbook.md`](server-first-migration-runbook.md)。
