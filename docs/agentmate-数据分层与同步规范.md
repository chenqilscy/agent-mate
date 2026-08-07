# AgentMate 数据归属与传输规范

> 状态：v4 Server-first 目标规范（2026-08-08）；对应 [WB-431](issues/archive/2026/WB-400-499.md#wb-431)。
> 本规范是新增实体和迁移完成后的唯一数据边界。当前 local-first 代码尚在迁移，旧镜像/代理行为只能作为兼容实现，不能成为新功能样板。
> 完整组件、Run 协议和迁移设计见 [`agentmate-server-first-架构设计.md`](agentmate-server-first-架构设计.md)。

## 0. 核心规则

1. **所有持久业务数据由 Server 唯一权威。** Desktop UI 和 Console 读取同一组 Server API/模型。
2. **Local Agent 不是业务 Server。** 本地只保存设备秘密、执行工作集、事件 WAL 和可重建缓存。
3. **没有通用双向同步。** 业务 CRUD 直接提交 Server；执行事件通过有序 WAL/ACK 协议上传。
4. **离线只延续已领取的执行。** 不允许离线创建或修改 Server 业务对象，不做恢复后的业务冲突合并。
5. **秘密和本机权限按执行位置归属。** 本机执行秘密留 Local Agent；Server deployment secret 留 Server，二者不互传。

## 1. 组件定位

- **AgentMate Server**：API、Console、业务数据库、对象存储、Run 调度和事件流。所有持久业务状态都在这里提交。
- **Desktop UI**：用户工作台。业务数据访问 Server，本机文件/权限/设备操作访问 Local Agent Core。
- **Local Agent Core**：后台 sidecar/daemon。负责设备连接、Run 租约、Agent Runtime、本机工具、working copy 和 event WAL。
- **Console**：Server 同源管理 UI，不是独立数据源。

## 2. 数据归属总表

| 数据类别 | 唯一权威 | Local Agent 是否持久化 | 离线行为 | 迁移状态 |
|---|---|---|---|---|
| 账号、外部身份、组织、成员、角色、邀请 | Server | token/账号显示缓存 | 不能新登录或改权限 | Server 已权威 |
| 项目、任务、里程碑、Sprint、自定义字段、治理 | Server | 只读可重建缓存 | 只读缓存；禁止业务写 | 部分仍有本地镜像 |
| 评论、@、通知、presence、timeline、审计 | Server | 可选短期缓存 | 只读或不可用 | Server 已覆盖主要 API |
| 会话、消息、Run、步骤、交付、结构化工具事件 | Server | 当前 Run working set + 未 ACK WAL | 已领取 Run 可受控继续 | Server schema/API 已落地，待客户端迁移 |
| 助理、频道、自动化、调度与历史 | Server | 执行所需快照/缓存 | 不创建、不编辑；已租约任务按协议继续 | Server schema/API 已落地，待客户端迁移 |
| Catalog、Capability Release、策略、安装目标 | Server | 已校验能力包缓存 | 使用 last-known-good 执行包；不改策略 | 已有目录下行，待去镜像化 |
| 项目资产、正式产物、对象版本 | Server + object storage | working copy / 下载缓存 | 未上传文件仍标记“仅本机” | 待建设 |
| 设备、capability、heartbeat、lease、ACK 高水位 | Server | 设备私钥、当前租约与 WAL | 重连后按 epoch/seq 恢复 | relay 有基础，Run 协议待建设 |
| 用户 LLM/MCP/连接器执行 secret | Local Agent secure storage | ✅ 权威 | 仅本机可用 | 已本地保存，需迁入安全存储 |
| OS 权限、外部路径 bookmark、浏览器 profile 授权 | Local Agent | ✅ 权威 | 仅本机可用 | 部分已有 |
| Server SSO/中央服务/deployment secret | Server secret store | ❌ | 相关 Server 能力不可用 | 已有只写/加密基础 |
| PID、端口、进程句柄、临时目录 | Local Agent runtime | 仅执行期 | 进程恢复按 Run 协议处理 | 已有 |
| Server 查询缓存、对象块缓存 | Server | 可选、可删除 | 只读并显示缓存时间 | 待统一 |

“迁移状态”只描述当前代码差距，不改变目标权威。新功能不能因为某类尚未迁移就继续新增本地业务表。

## 3. 必须留在本地的数据

### 3.1 设备秘密

- device private key；
- Server refresh/session token；
- 本机加密主密钥。

优先使用操作系统 secure storage；不得写入日志、事件 WAL、前端 localStorage、工作区或普通导出。

### 3.2 执行秘密

- 用户自带 LLM API key；
- 本机 MCP/连接器 OAuth token、bot token；
- 只对当前设备有效的 credential material。

Server 可以保存 provider 类型、credential reference、健康状态和缺失原因，但不能保存或回显上述秘密。Server 管理的企业服务凭据属于 Server secret，不属于 Local Agent secret。

### 3.3 本机权限与路径

- 用户授予的目录/文件访问权；
- 文件选择 bookmark、浏览器 profile 授权；
- 本机应用、证书或硬件设备访问权。

Server 只能知道“该设备是否声明具备某能力”，不能获得可直接访问本机资源的令牌或真实路径。

### 3.4 working copy 与运行时

Local Agent 可以保存执行输入、下载资产、生成中的文件、临时目录、PID 和 checkpoint，但这些不是业务真相。正式产物只有完成 Server 元数据事务和对象存储提交后才算已交付。

### 3.5 event WAL

WAL 只保存未获 Server ACK 的 Run 事件，必须具备：

- `run_id + lease_epoch + seq + event_id` 幂等键；
- payload hash、创建时间、尝试次数和连续 ACK 高水位；
- 原子追加、进程重启恢复、容量上限和可观察积压；
- secret redaction 和 payload 大小限制。

WAL 不是 sessions/messages/runs 的本地副本，不接受 UI 直接编辑；ACK 后按保留策略清理。

## 4. Server 业务数据契约

### 4.1 读取

- Desktop UI 和 Console 直接调用 Server API。
- Local Agent 只读取当前 Run 执行必需的版本化快照、能力包和资产引用。
- 本地 cache 可以优化启动和弱网展示，但必须可删除重建、只读、带版本/ETag 和缓存时间。
- Server 不可达不能把缓存自动提升为写权威。

### 4.2 写入

- Server API 成功响应代表业务事务已提交。
- 网络超时使用 request id/idempotency key 查询原结果，不能在本地创建另一条业务记录。
- Local Agent 产生的业务结果通过 Run event/artifact commit API 进入 Server；Server 验证当前 lease epoch、权限和 schema 后提交。
- Viewer/Member/Admin/Owner 等权限只由 Server 决定，本地检查只能用于提前提示，不能代替 Server 授权。

### 4.3 缓存失效

- Server 使用 revision、ETag、版本号或实时失效事件通知客户端刷新。
- 网络不可达保留 last-known-good cache；Server 明确 tombstone/撤回则必须失效。
- “不可达”和“已删除/撤权”是不同状态，不能用同一空列表回退处理。

### 4.4 持久业务 API 基线（WB-432）

Server 已建立 `sessions/messages/runs/run_steps/assistants/channels/automations/assets` 的版本化关系模型，统一路由位于 `/api`：

- 集合读取使用 `limit + next_cursor`；游标由稳定排序字段和实体 id 组成，调用方不能自行解释或改写；
- 创建请求可带 `Idempotency-Key`。同账号、同实体类型和同 key 重试返回原实体；key 对应的 payload 改变时返回 `409`；
- 可变实体携带 `version`，更新和删除必须传 `expected_version`，陈旧写返回 `409`；
- 项目实体由 Server 的项目角色判定：Viewer 只读，Member 可写执行数据，Admin/Owner 管理共享助理、渠道和自动化；撤权后立即返回不可见；
- 写操作与实体事务同时写入 `business_audit`，审计通过 `/api/business/audit` 使用同样的稳定游标导出；业务集合本身也可逐页导出，不提供绕过权限的全库 dump；
- 删除采用有审计的 soft delete。本阶段不自动物理清除；数据库备份保留实体关系和 tombstone。后续若引入物理保留期，必须是显式的平台策略和独立审计操作；
- `channels.public_config` 拒绝 token/secret/password/API key 等字段，只允许保存不含秘密的配置；`credential_ref` 只能是指向本机或设备安全存储的 opaque URI；
- `assets` 在本阶段只提交元数据、hash 和对象引用状态。对象字节、签名上传与 working copy 由 WB-436 定义，不能把二进制或本机绝对路径写入此 API。

这些 API 是迁移的 Server 目标端，不构成长期双写许可。Desktop 切换前的本地表仍按 §10 管理。

## 5. Run 事件传输

### 5.1 先落 WAL，再发送

Local Agent 产生事件时先原子写入 WAL，再通过出站执行通道发送。Server 以 `event_id` 和 `(run_id, lease_epoch, seq)` 去重，事务提交后返回 ACK 高水位。

### 5.2 重试不是重复执行

- 发送失败重传原 event；
- 不因 HTTP/WebSocket 超时生成新的 completion/tool-result 事件；
- Server 返回 seq gap 时从 WAL 补传；
- 旧 lease epoch 的新副作用事件必须被拒绝。

### 5.3 敏感 payload

- 消息和安全结构化结果进入 Server；
- secret 字段在本机剔除；
- 大文件和长输出转为 asset/artifact 引用；
- 必须留本地的原始工具 payload 只上传 hash、大小、状态和安全摘要，并标记 `local_only`。

## 6. 文件与对象存储

1. 项目正式资产和 Run 产物由 Server 元数据 + object storage 权威管理。
2. Local Agent 使用授权下载创建 working copy；缓存命中必须校验 content hash。
3. 上传采用临时对象/分片，只有 Server 完成 hash、size、权限和 Run/项目归属校验后才 commit。
4. 用户任意本机文件默认不上传。引用时 UI 必须显示“仅本机”；明确上传后才获得 Server asset id。
5. 事件 JSON 禁止内嵌大文件正文、二进制或无限长 stdout。
6. 删除 Server asset 不等于未经确认地删除用户原始外部文件；working copy 按独立清理策略回收。

## 7. 离线规范

| 操作 | Server 不可达时 |
|---|---|
| 浏览已缓存项目/会话/任务 | 允许只读，显示缓存时间和离线状态 |
| 新建/修改/删除业务实体 | 禁止；明确提示未保存 |
| 发起新 Run | 禁止，除非 Server 已提前创建并授予有效租约 |
| 继续已领取 Run | 在租约和本地策略允许时继续，事件写 WAL |
| 租约过期后的工具副作用 | 禁止，等待 Server 恢复或人工确认 |
| 创建本机临时文件 | 允许，但标记为未上传、非正式资产 |
| 修改本机设备设置/凭据 | 允许，仅影响当前设备 |

不提供“离线修改业务对象、恢复后自动合并”。如果未来确有该产品需求，必须作为新的架构决策显式引入，而不能复用 cache/WAL 偷渡实现。

## 8. 身份和人归属

- Server account id 是账号、actor、assignee、creator、reviewer 等字段的唯一人员标识。
- 显示名是可变投影，不能作为关系键。
- Desktop UI token、device identity 和 Local Agent 执行秘密是三种不同凭据，必须分开撤销和审计。
- 未登录设备不是本地账号，不允许创建长期业务数据；可以进入有限的登录/设备设置界面。
- Server 撤权立即阻止新读取/写入/租约；本地缓存不能继承已撤销权限。

## 9. 新增实体决策流程

新增实体前按顺序检查：

1. **它是否是跨会话需要保留的产品/业务状态？** 是 → Server 权威。
2. **它是否是本机秘密、OS 权限、真实路径或运行中进程状态？** 是 → Local Agent 权威，Server 只保留必要非敏感状态。
3. **它是否只是未 ACK 的执行事件？** 是 → Local WAL，ACK 后清理，Server 保存正式事件。
4. **它是否只是性能缓存？** 是 → 必须可删除重建、只读、有版本，不能产生离线写。
5. **它是否是项目文件或交付物？** 正式版本 → Server/object storage；执行 working copy → Local Agent。

禁止为新的业务实体增加以下模式：

- `origin=local/server` 双权威；
- `server_dirty/server_updated_at` 通用镜像字段；
- 本地写成功后后台补传业务 CRUD；
- 通用 LWW/冲突台账；
- Server 不可达时自动创建纯本地替代对象。

## 10. 迁移期兼容规则

当前代码仍包含本地业务表、`POST /api/server/pull`、写代理、镜像字段、冲突台账和业务 outbox。迁移完成前：

1. 不在这些机制上新增实体或扩展离线写能力。
2. 每类实体切换时必须先完成 Server schema/API、幂等导入、权限回归和只读备份。
3. 同一实体任一时刻只有一个写权威；禁止为了平滑迁移做无限期双写。
4. 切换完成后，本地旧表只读观察，随后按退出门槛删除。
5. 旧客户端不能在切换后重新写入本地并要求 Server 合并；Server 必须执行最低协议/版本门禁。

具体阶段和退出门槛见目标架构设计 §11–§12。
