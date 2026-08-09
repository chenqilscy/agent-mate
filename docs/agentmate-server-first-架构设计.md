# AgentMate Server-first 架构设计

> 状态：目标架构，2026-08-08 经产品决策确认；对应迁移 epic [WB-431](issues/archive/2026/WB-400-499.md#wb-431)。
> 当前代码仍处于 local-first 兼容阶段；本文描述迁移完成后的唯一目标，不代表所有能力已经落地。
> 实体归属与传输红线以 [`agentmate-数据分层与同步规范.md`](agentmate-数据分层与同步规范.md) 为准。

## 1. 决策

AgentMate 从“local-first App + 可选 Server 控制平面”调整为：

> **Server-first 协作平台 + Local Agent 本机执行节点。**

- **AgentMate Server** 由 API、Console、业务数据库、对象存储、Run 调度与实时事件流组成，是所有持久业务数据的唯一权威。
- **AgentMate Local Agent** 是安装在用户设备上的桌面客户端，由 Desktop UI、后台执行服务、Agent Runtime、本机工具 worker 和本地安全存储组成。
- 本地持久化只允许保存设备绑定的秘密/权限、执行工作集、可靠事件 WAL 和可重建缓存；不能成为另一份业务权威。
- 离线时可以继续已领取的 Run 并缓存事件，但不能创建或修改 Server 业务对象。

这不是对现有双向同步机制的继续扩展，而是有计划地退役业务镜像、冲突合并和纯本地业务模式。

## 2. 目标与非目标

### 2.1 目标

1. 一个实体只有一个持久权威源，跨设备读取结果一致。
2. Server 可以完整承载账号、协作、会话、Run、自动化、资产和审计生命周期。
3. Local Agent 可以在不向公网暴露本机端口的前提下安全使用文件、终端、浏览器、MCP 与用户凭据。
4. Run 事件在断线、进程重启和重复投递下不丢失、不重复生效。
5. 桌面 UI、Console 和外部 API 使用同一组 Server 业务模型与权限规则。
6. 迁移期间不双写业务实体，不用“看起来成功”的本地记录掩盖 Server 写失败。

### 2.2 非目标

- 不承诺无 Server 时完整创建、编辑和协作。
- 不把 Local Agent 做成第二套业务 Server。
- 不让 Server 直接执行任意本机命令，也不允许 Server payload 绕过本机能力注册表和权限门禁。
- 不把本机 LLM/MCP/连接器秘密、操作系统权限令牌或任意外部路径自动上传 Server。
- 不在本轮设计项中一次性重写全部运行代码；实施按独立迁移 issue 推进。

## 3. 目标拓扑

```text
┌──────────────────────────── AgentMate Server ────────────────────────────┐
│ API                                                                     │
│ auth · orgs · projects · sessions · messages · runs · automations       │
│ catalog · assets · policies · audit · device registry                   │
│                                                                          │
│ durable database · object storage · Run scheduler · event stream         │
│                                      ▲                                   │
│                                      │ same-origin /api                   │
│                              AgentMate Console                           │
└───────────────────────▲────────────────────────────▲──────────────────────┘
                        │ HTTPS / SSE / WebSocket     │ outbound job channel
                        │                             │ lease · event · ack
┌───────────────────────┴──────────── Local Agent ───┴──────────────────────┐
│ Desktop UI（Tauri + React）                                               │
│   ├─ 业务数据 ───────────────▶ Server API                                 │
│   └─ 本机操作 ───────────────▶ Local Agent Core（IPC）                     │
│                                                                          │
│ Local Agent Core · Agent Runtime · Tool/MCP Workers                       │
│ secure secrets · workspace working copy · event WAL · disposable cache   │
└──────────────────────────────────────────────────────────────────────────┘
```

Server 不主动连接用户设备。Local Agent 使用 HTTPS/WebSocket 主动建立出站连接，完成设备注册、心跳、任务租约、事件上传和 ACK。

## 4. 组件职责

### 4.1 Server API

Server API 负责：

- 认证、组织、成员、角色与权限；
- 项目、工作项、里程碑、讨论与通知；
- 会话、消息、Run、结构化执行事件与交付记录；
- 助理、频道、自动化、目录、安装目标与组织策略；
- 项目资产元数据、对象存储授权和产物版本；
- 设备注册、能力报告、Run 分配、租约和取消；
- 审计、用量、健康状态和协议兼容门禁。

业务写入只在 Server 事务中提交。Local Agent 或 Desktop UI 收到的成功响应必须代表 Server 已接受该变化。

### 4.2 Console

Console 是 Server 同源托管的管理 UI，不是独立服务或第三套数据源，负责：

- 平台账号、组织、成员和项目治理；
- Catalog、Skill/工具发布、灰度、撤回与兼容策略；
- 自动化、设备、Run、审计和运行健康管理；
- Server deployment secret 的只写配置与轮换；
- 业务资产和团队协作的 Web 管理入口。

### 4.3 App（个人 Agent 工作台）

App 是普通用户使用 AgentMate 的主要工作入口，不是 Local Agent 的管理控制台，也不是 Console 的桌面复制品。它把 Server 上的项目、任务、会话和 Run 组织成个人工作上下文，让用户发起、推进、监督和验收 Agent 工作。Local Agent 是当前默认的本机执行节点；App 的产品边界不依赖某一个执行节点，未来可以在不复制业务权威的前提下选择受 Server 管理的远程或云端执行位置。

App 与 Local Agent Core 共同安装在桌面端，但生命周期和职责独立：Core 可以在 App 窗口关闭后继续已领取的 Run；App 负责用户交互、工作上下文和执行控制，Core 负责实际执行与可靠事件上报。

App UI 负责：

- 展示当前用户的项目任务、会话、Run 和需要关注的执行，形成个人工作入口；
- 选择 Server 项目或任务作为上下文，发起 Run，但不提供项目结构和组织治理 CRUD；
- 选择当前可用的执行位置；现阶段真实可用的位置是这台设备上的 Local Agent；
- 实时展示思考、工具、计划、产物与终态；
- 回答 `ask_user`，执行暂停、继续、取消、权限确认和交付验收；
- 选择本机文件，管理 working copy、下载目录和本机产物提交；
- 管理本机模型凭据、已安装 Skill、本机 MCP/连接器和设备级运行设置；
- 展示 Local Agent 在线状态、设备身份、能力缺口、WAL 积压、错误与恢复动作；
- 在需要账号、组织、项目、成员、自动化或目录管理时打开 Server Console。

Console 管理系统，App 使用系统完成工作，Local Agent 在设备上实际执行。App 可以通过 Server API 完成领取任务、评论、回答、提交交付和验收等当前工作必需的业务流转，但项目结构、自动化定义、助理发布、成员、目录发布和审计等治理页面不得在 App 中再维护一套同构信息架构。

| 用户意图 | 唯一入口 |
|---|---|
| 管理账号、组织、项目、成员、助理、自动化、目录、审计 | Server Console |
| 查看我的项目任务、会话、Run，并开始或继续工作 | App |
| 推进当前任务，回答、审批、提交交付和验收 | App；业务状态直接写 Server |
| 查看/控制当前设备执行、权限、WAL、working copy | App 的“此设备”；状态来自 Local Agent |
| 配置仅存在于本机的模型密钥、Skill、MCP 和连接器凭据 | App 的“本机能力/此设备” |
| 查看个人跨设备会话与 Run 结果 | App；数据来自 Server |
| 查看团队全局运行、设备舰队、成本和审计 | Server Console |

业务数据直接使用 Server API；文件选择、权限确认、设备设置等本机能力使用 Tauri IPC、Named Pipe 或仅绑定 loopback 的受保护 Local Agent API。不得继续以本地业务数据库作为 UI 数据源。

### 4.4 Local Agent Core

Local Agent Core 是桌面安装包内的后台 sidecar/daemon，负责：

- 设备注册、密钥对、心跳与 capability report；
- 领取和续租 Run，执行取消与 fencing；
- 驱动 Agent Runtime、LLM、工具、MCP 和本机连接器；
- 管理沙箱 working copy、子进程、浏览器和文件访问；
- 将执行事件先写 WAL，再按序上传并等待 Server ACK；
- 对 Server 下发的能力包做签名/hash、版本、权限和本机实现校验；
- 对用户可见地处理权限申请、离线、积压和恢复。

Local Agent Core 不提供项目、会话、任务等业务 CRUD，不维护业务冲突，也不签发用户身份。

### 4.5 Agent Runtime 与 Tool Workers

- Agent Runtime 保留真实 LLM function-calling、多轮工具循环、`ask_user` 和多 Agent 编排。
- Tool/MCP worker 在最小权限环境中运行，只接收当前 Run 已授权的输入。
- Server 下发声明不能直接变成任意进程命令；本机可信注册表、已安装签名包和用户授权共同决定是否可执行。
- 工具输出在进入 Server 事件流前执行数据分类和 secret redaction。

## 5. 单一权威与数据归属

### 5.1 Server 持久业务数据

下列实体迁移完成后只能以 Server 为权威：

- accounts、external identities、orgs、members、roles、invites；
- projects、work items、milestones、sprints、custom fields、governance；
- sessions、messages、runs、run steps、结构化 tool events、acceptances；
- comments、mentions、notifications、presence、timeline、audit；
- assistants、channels、automations、schedules、delivery history；
- catalog、capability releases、安装目标、策略、用量与成本；
- project assets、artifact metadata、object versions 和内容 hash；
- devices、capabilities、leases、heartbeats 与协议版本。

### 5.2 本地持久数据

本地只允许以下类别：

| 类别 | 示例 | 约束 |
|---|---|---|
| 设备秘密 | device private key、Server refresh/session token | 使用 OS secure storage 或本地加密存储；不进日志/WAL |
| 执行秘密 | 用户 LLM key、本机 MCP/连接器 OAuth token | 只供 Local Agent 使用；Server 仅保存非敏感 credential reference/status |
| 本机权限 | 目录授权、浏览器 profile 授权、外部路径 bookmark | 设备绑定，不能跨设备复用 |
| working copy | Run 输入、下载资产、生成中的文件、临时目录 | 不是业务权威；提交产物后由 Server/object storage 持久化 |
| 运行时状态 | PID、端口、进程句柄、sandbox lease | 只对当前设备和当前执行有效 |
| event WAL | 尚未获得 Server ACK 的顺序事件 | 可恢复、幂等；ACK 后按保留策略清理 |
| cache | Server 查询、能力包、对象块 | 可删除、可重建，不允许离线编辑 |
| 设备设置 | 运行并发、下载目录、ASR、Langfuse 本机配置 | 不影响跨设备业务语义 |

### 5.3 文件与资产

- 项目正式资产和 Run 产物使用 Server 元数据 + 对象存储作为权威。
- Local Agent 通过短期签名 URL 或受权流式 API 下载输入、上传产物；Server 完成 hash/size/content-type 校验后才提交对象版本。
- 本机任意外部文件默认不上传。用户引用它时先创建设备本地引用；只有明确执行“上传/附加到项目”后才进入 Server 资产。
- working copy 可包含尚未提交的中间文件，但 UI 必须区分“仅本机”与“已上传”。

### 5.4 消息和工具事件

- 会话消息和 Run 状态进入 Server，保证跨端恢复和团队可见。
- 工具事件使用结构化 envelope；参数和返回值先执行字段级 secret redaction、大小限制与敏感级别分类。
- 明确标记 `local_only` 的原始 payload 不上传；Server 只保存事件类型、时间、hash、大小、结果状态和安全摘要。
- 文件正文不应内嵌在事件 JSON 中，应转换成受权限控制的 asset/artifact 引用。

## 6. 通信与身份

### 6.1 用户身份

- Server 是唯一账号与授权权威。
- Desktop UI 使用标准 Server access/refresh token；refresh token 存 OS secure storage，不存浏览器普通 localStorage。
- Console 和 Desktop UI 使用同一 account id、org role 和 project role。

### 6.2 设备身份

- Local Agent 首次启动生成设备密钥对，以登录用户授权完成设备注册。
- Local Agent 生成不可关联主机名/用户名的 opaque `device_id`，Server 在用户授权下登记；后续连接通过设备私钥签名 challenge，并绑定当前账号授权。
- 设备撤销后不能领取新 Run；已有租约被 fencing，未 ACK 事件只能按受控恢复协议上传。
- capability report 只包含版本、OS/arch、可信工具/协议版本和非敏感可用状态。

### 6.3 双通道客户端

Desktop UI 不再只有一条本地 `/api` 通道：

```text
业务通道：Desktop UI ──HTTPS/SSE──▶ Server
本机通道：Desktop UI ──IPC────────▶ Local Agent Core
执行通道：Local Agent ──WSS───────▶ Server
```

本机通道只提供设备状态、文件选择、权限确认、working copy 和运行控制等本机能力，不代理通用 Server 业务 API。

## 7. Run 租约与事件协议

### 7.1 状态机

```text
queued → leased → running ↔ waiting_user
                     ├─→ completed → accepted
                     ├─→ failed
                     └─→ cancelled

leased/running --lease timeout--> recoverable → queued 或 failed
```

- Server 创建 Run 并保存请求、目标设备/能力要求、状态和幂等键。
- Local Agent 原子领取租约，得到 `lease_id`、`lease_epoch`、到期时间和输入快照。
- 所有状态变更必须携带当前 epoch；旧 worker 即使恢复也会被 fencing，不能覆盖新执行者。
- 只有 Server 可以提交终态；Local Agent 上报 terminal event 后等待 Server ACK。

### 7.2 事件 envelope

每条事件至少包含：

```text
event_id            全局幂等 ID
run_id
device_id
lease_epoch
seq                 当前 Run/epoch 单调递增
event_type
occurred_at
payload             已分类、限长、脱敏
payload_hash
```

Local Agent 必须先把事件和 payload hash 原子写入 WAL，再发送。Server 以 `(run_id, lease_epoch, seq)` 和 `event_id` 去重，事务提交后返回连续 ACK 高水位。Local Agent 只能删除不高于该高水位的 WAL 记录。

### 7.3 断线、重试与恢复

- 发送超时不代表失败；Local Agent 重发相同 event，不生成新的语义事件。
- Server 可返回缺失 seq 范围，Local Agent 从 WAL 补传。
- WAL 达到容量/时间阈值后停止产生可能丢失的新输出，并在 UI 明确显示阻塞；不能静默丢事件。
- 设备重启后先恢复 WAL，再申请继续租约；租约已失效时仅允许上传被 Server 接受的历史事件，不得继续执行。
- `ask_user` 问题先进入 Server；Desktop UI 回答写 Server，Local Agent 从执行通道收到答案并继续。

### 7.4 取消与暂停

- 用户取消先写 Server；Server 递增 cancel version 并推送设备。
- Local Agent 停止子进程、写入取消确认事件；Server 在超时后可强制把设备标记失联，但不能假装本机进程已停止。
- 暂停必须区分“Server 不再分配步骤”和“本机已安全停在 checkpoint”；没有 checkpoint 的工具只能取消或等待完成。

### 7.5 已落地协议基线（WB-433）

- 用户通道：`POST /api/devices/register` 创建一次性 challenge，`POST /api/devices/{id}/verify` 校验 Ed25519 签名并签发独立 Device token；`GET/DELETE /api/devices/{id}` 查询或撤销设备。
- 设备通道：`POST /api/agent/heartbeat` 更新公开 capability；`POST /api/agent/runs/lease` 原子领取；`renew/events/commands` 分别续租、提交有序事件和拉取取消/`ask_user` 命令。
- Server migration v11 保存设备、challenge/token hash、租约、正式事件和命令；`business_runs.lease_epoch` 是 fencing 权威，活跃租约在数据库中有唯一索引。
- Local App migration v9 只保存当前租约和未 ACK event WAL。发送失败、进程重启与 seq gap 都保留原 event；只有连续 `ack_high_water` 推进后才删除。
- 后台调度器仅注册、心跳和补传 WAL；Run 领取、事件写入和完成控制已由 WB-434 的受保护 Core 接口承接，不由兼容业务调度器抢占。

### 7.6 已落地 Local Agent Core 基线（WB-434）

- `backend/main.py --local-agent-core` 启动独立 FastAPI app，只初始化 `agentmate-local-agent.db`，不注册项目、会话、任务、自动化、登录或通用 Server 代理路由，也不打开本地业务数据库。
- Core 仅绑定 `127.0.0.1`，并再次按请求来源拒绝非 loopback 客户端；所有 `/api/local-agent/*` 请求还必须携带 Tauri 每次启动生成的随机 IPC token。
- IPC token 只通过 sidecar stdin 管道一次性注入，在 Tauri/Python 进程内存中使用；不进入参数值、子进程环境、数据库或前端。Desktop 只暴露窄化的原生命令，不提供通用带权代理。
- 设备私钥、Device token 和 Server session token 在 Windows 使用当前用户 DPAPI 加密后落库；Run lease 和未 ACK WAL 使用独立 Core SQLite，payload 密钥字段在写 WAL 前失败关闭。
- 为等待 WB-435 的 UI 双通道切换，默认 sidecar 暂时仍启动兼容 app，并在同一进程挂载上述受保护 Core 路由；独立 Core 入口和空业务库 Run 完成链路已经可验证，兼容业务路由不属于 Core app。

## 8. 离线和故障语义

| 场景 | 行为 |
|---|---|
| Server 不可达，尚未开始 Run | 不创建新业务对象，不显示假成功 |
| 已领取 Run 短时断线 | 在租约和本地策略允许时继续，事件写 WAL |
| 断线超过租约 | 停止产生新副作用，等待恢复/人工确认 |
| Desktop UI 关闭 | Local Agent 可在托盘继续执行；UI 重开从 Server 恢复状态 |
| Local Agent 崩溃 | Server 等租约过期；本机重启后恢复 WAL/working copy |
| Server 重启 | 数据库、对象存储和事件高水位恢复；Local Agent 重连并续传 |
| 本地 cache 损坏 | 删除并从 Server 重建，不进入冲突合并 |
| 本地 secret 丢失 | Run 进入 `blocked_missing_credential`，不得上传或伪造 secret |

缓存页面可以只读显示，并必须标记缓存时间；离线不能修改项目、消息、任务、自动化、目录或资产元数据。

## 9. 安全边界

- Server→Local Agent 的所有执行指令必须绑定用户、项目、Run、device、lease epoch、能力版本和权限声明。
- Local Agent 只执行本机可信实现或通过签名/hash 校验的能力包；Server 不能直接下发任意 shell command。
- 用户秘密不进入 Server 业务表、事件 payload、对象元数据、日志或 crash report。
- Server deployment secret 与本机执行 secret 分域管理，二者不能互相回显或自动复制。
- working copy 继续使用路径穿越防护、最小环境变量和子进程权限限制。
- Desktop UI 的业务 token 与设备私钥分开存储；撤销用户 session 不等同于擦除设备私钥，设备撤销需独立审计。
- Server 必须对消息、资产和工具事件执行租户/项目权限校验，不能依赖 Local Agent 已过滤。

## 10. 可观察性和运维

Server 至少暴露：

- Run 各状态数量、排队时间、租约超时、重分配和终态延迟；
- 设备在线率、协议版本、心跳延迟和 capability mismatch；
- 事件接收速率、重复率、seq gap、ACK 延迟和拒绝原因；
- 对象上传失败、hash 不匹配和孤立 multipart；
- 每账户/组织用量、成本、自动化成功率和审计事件。

Local Agent 至少暴露给本机诊断页：

- Server 连接、设备注册、当前租约和最后心跳；
- WAL 条数/字节/最老事件、上传高水位和最近错误；
- running worker、子进程、working copy 使用量和权限缺口；
- 本机 capability report 与 Server 要求的差异。

日志和指标不得包含 token、secret、消息正文或文件内容。

## 11. 迁移策略

### 阶段 0：设计冻结

- 本文与数据归属规范成为新增功能的目标约束。
- 旧 local-first 文档明确标记为当前兼容实现，不再扩展新的业务镜像实体。
- 创建迁移子 issue，并为每一阶段定义入口、退出和回滚条件。

### 阶段 1：Server 持久业务面

- 在 Server 建立 sessions/messages/runs/assistants/channels/automations/assets 等权威模型、权限和 API。
- 桌面仍可经兼容 adapter 访问，但新数据只在 Server 写入。
- 退出门槛：Server API 覆盖现有用户流程，备份/迁移/审计和跨账户隔离测试通过。

### 阶段 2：设备与 Run 协议

- 落地 device registration、capability report、job lease、heartbeat、event WAL/ACK、fencing、取消和恢复。
- 退出门槛：断网、重复发送、进程崩溃、租约过期和双 worker 竞争测试无重复副作用、无事件丢失。

### 阶段 3：Local Agent 收缩

- 从 `backend/` 移除业务权威职责，保留 runtime、工具、MCP、凭据、workspace、WAL 和 device API。
- 当前 FastAPI 可作为过渡 sidecar，但本地路由只能服务本机能力，不得继续拥有业务 CRUD。
- 退出门槛：删除本地业务 DB 后，Local Agent 仍可从 Server 领取并完成 Run。
- **2026-08-08 基线：** 独立 Core app、受保护 loopback IPC、独立加密 secret/lease/WAL 存储和空业务库 Run 完成回归已落地；默认 sidecar 的兼容业务路由将在阶段 4 完成 UI 切换时停止启动，避免提前破坏现有桌面流程。

### 阶段 4：Desktop UI 双通道切换

- 项目、会话、任务和设置等业务 store 改连 Server；文件选择、权限和设备诊断改连 Local Agent IPC。
- 退出门槛：桌面重启或换设备后可从 Server 恢复完整业务视图；Local Agent 离线状态可见且不会产生假成功。

### 阶段 5：资产与 working copy

- 项目文件和产物迁入对象存储，Local Agent 实现下载、上传、hash、断点续传和本机/已上传标识。
- 退出门槛：大文件、重试、冲突命名、权限撤销和孤立上传清理通过验收。

### 阶段 6：存量迁移与旧同步退役

- 对本地业务库执行只读扫描、预检、幂等导入、数量/hash 对账和用户确认。
- 按账户/设备逐步切换；切换后不允许旧客户端重新成为写权威。
- 观察期内保留加密只读备份和兼容读取工具，不再双写。
- 退出门槛：`origin/server_dirty/server_updated_at/server_sync_conflicts`、通用 `/server/pull` 和业务 outbox 删除，回归与恢复演练通过。

## 12. 发布与回滚原则

1. **不双写**：同一实体在任一阶段只能有一个写权威。
2. **先 Server、后客户端**：Server API 向后兼容一个明确窗口，客户端 capability gate 防止协议不兼容设备领取 Run。
3. **按实体切换**：通过服务端迁移状态决定某账户/实体的 authority，不使用本机隐式猜测。
4. **可核对导入**：每批迁移都有 manifest、源 ID、目标 ID、数量、内容 hash、失败清单和重试键。
5. **回滚不回到双主**：回滚使用新客户端兼容 adapter 或暂停写入；不能恢复旧客户端本地写入后再尝试合并。
6. **删除有门槛**：只有完成备份恢复、跨设备、离线续传和权限回归后，才删除旧表与代码。

## 13. 工作包

| 工作包 | 范围 | 依赖 |
|---|---|---|
| [WB-431](issues/archive/2026/WB-400-499.md#wb-431) | 目标架构、数据归属、迁移阶段与子项拆分 | 无 |
| [WB-432](issues/archive/2026/WB-400-499.md#wb-432) | Server 持久业务模型与 API | WB-431 |
| [WB-433](issues/archive/2026/WB-400-499.md#wb-433) | 设备身份、Run 租约、事件 WAL/ACK 协议 | WB-431；与 WB-432 对齐 Run schema |
| [WB-434](issues/archive/2026/WB-400-499.md#wb-434) | Local Agent Core 收缩和本机 IPC | WB-433 |
| [WB-435](issues/WB-435-desktop-dual-channel-cutover.md) | Desktop UI 业务/本机双通道切换 | WB-432、WB-433、WB-434 |
| [WB-436](issues/WB-436-server-assets-working-copy.md) | Server 对象存储与 Local Agent working copy | WB-432、WB-433 |
| [WB-437](issues/WB-437-server-first-data-migration-retirement.md) | 存量导入、分批切换和旧同步退役 | WB-432～WB-436 |

## 14. 当前实现映射

| 目标组件 | 当前代码基础 | 迁移方向 |
|---|---|---|
| Server API/Console | `server/`、`console/` | 扩展业务模型、Run/设备/资产 API |
| Desktop UI | `src/`、`src-tauri/` | 业务请求改连 Server，本机能力改走 IPC |
| Local Agent Core | `backend/local_agent_core.py`、`backend/agent/`、`backend/mcp_*` | 独立 Core 入口已落地；WB-435 后默认 sidecar 停止加载兼容业务 app |
| 本地安全/工作集 | `backend/local_agent_store.py`、`backend/local_secret_store.py`、`workspace/` | secret/lease/WAL 已拆分；working copy 与 cache 继续按 WB-436 收口 |
| 旧同步层 | `backend/server_sync.py`、`backend/server_client.py`、镜像字段/表 | 迁移完成后删除 |

旧 [`agentmate-server-架构设计.md`](agentmate-server-架构设计.md) 继续记录已经实现的 local-first 控制面基线，供迁移追溯；不得再把它当成新增功能的目标架构。
