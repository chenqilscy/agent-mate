# AgentMate 外部系统接入

> 状态：当前接入边界，更新于 2026-08-10。外部系统不应连接或暴露 Local Agent 的 loopback 控制面。

## 1. 先选择正确入口

| 需求 | 入口 | 身份与数据边界 |
|---|---|---|
| 管理 Server 上的项目、任务、Session、Run、自动化 | Server REST API | 用户 Bearer 或最小权限 service identity；Server 权限与审计 |
| 公网 SaaS/CI/CRM 投递事件 | Server webhook/relay | scoped token + HMAC + 幂等键；Server 持久排队 |
| 同机受信系统触发个人任务 | 受保护的本机 webhook | 独立 HMAC、loopback、大小和时间窗限制；不暴露公网 |
| Agent 在 Run 中访问外部系统 | Local MCP/连接器 | App 配置的本机实例和加密凭据；受 Run 权限、暂停和取消控制 |
| Telegram、邮件等人机入口 | Channel | Server 定义与本机 credential reference；不是通用事件总线 |
| 封装 Agent 操作规程 | Skill | 不是网络鉴权或公网 API |

不要把用户 Bearer 写进第三方 webhook 配置，不要把 Skill 当 API，也不要通过隧道把 `127.0.0.1:8101` 暴露为公网 Agent 服务。

## 2. Server API

- App、Console 和受授权客户端使用同一 `/api` 业务模型。
- 用户 Bearer 代表真实账号；服务身份必须只授予所需 scope、组织和项目范围。
- 创建请求使用 `Idempotency-Key`；重试复用相同 key 和正文。
- 更新遵守实体 version/ETag；冲突由调用方重新读取后处理。
- Viewer/Member/Admin/Owner 权限始终由 Server 校验，不能依赖客户端隐藏按钮。
- 个人模型、MCP、连接器和渠道 secret 不能放入业务 API payload。

## 3. Webhook 与 Relay

公网事件先到 Server，由 Server 验证来源、持久排队并分配到设备 Run。请求至少包含：

- Unix 秒时间戳，默认容忍窗口不超过 300 秒；
- 业务幂等键，同一来源内稳定唯一；
- `v1=<hex>` HMAC-SHA256，签名对象是 `timestamp + "." + exact_raw_body`；
- UTF-8 JSON object 和明确的请求体上限。

密钥只显示一次并进入调用方 secret manager；读取接口不回显。错误签名、过期时间、停用来源和 scope 不匹配均失败关闭。Relay 的 lease/ACK 与业务 Run 的 lease/ACK 是不同协议，不得互相代替。

## 4. MCP 与连接器

App 管理当前 owner 在这台设备上的连接器实例：

- stdio：启动命令、逐项参数、非敏感环境变量和单独加密的 credential env；
- HTTP/SSE：服务 URL、非敏感 Header 和单独加密的 credential Header；
- 内置：可信本机定义，可按声明配置凭据或 OAuth。

保存定义后必须执行真实 MCP 初始化与工具发现。只有启用、配置完整且健康的实例可加入 loadout。Server Catalog 只提供推荐和兼容信息，不能把远程 JSON 直接当本机可执行命令。

Run 调用连接器仍受 owner、session、项目角色、执行模式和高风险权限约束。暂停请求会等待已开始的工具步骤到达安全边界，只有此后才确认 paused 且不再消费工具流；取消时终止当前连接。失败必须产生可见错误，不能静默跳过后声称完成。

## 5. Channel

Channel 用于持续的人机消息，不用于任意系统事件：

- 定义、启停、成员策略和审计属于 Server/Console；
- bot token、邮箱密码或 OAuth token 留在负责执行的 Local Agent；
- 入站必须做发送者映射、去重、offset/lease 和自回复循环防护；
- 出站遵守平台长度、附件、速率和错误规则；
- 设备离线时必须显示等待或失败，不伪装成已送达。

未完成真实授权、收发、去重和真机验证的类型必须显示不可用。

## 6. 网络与秘密

- Local Agent 默认且必须只绑定 loopback；公网入口由 Server 或部署方 HTTPS 网关提供。
- 任何网关都必须执行 TLS、限速、请求体上限、脱敏日志和 HMAC 原文保持。
- secret 不进入 URL、前端构建、Git、普通日志、Run event 或 Server Catalog。
- 外部 payload 是不可信输入，只能作为事实材料进入 Run，不能直接变成本机命令或权限。
- 生产域名、证书、备份和可用性由部署方提供，仓库内测试不替代生产验收。
