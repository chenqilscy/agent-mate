# AgentMate 外部系统接入

## 1. 接入面怎么选

| 接入面 | 方向 | 适用场景 | 身份与边界 |
|---|---|---|---|
| App REST API | 外部系统 → AgentMate | 代表真实用户管理项目、会话、自动化 | 用户 Bearer；按 owner/项目成员权限校验 |
| Local Automation Webhook | 同机外部系统 → App | 本机 CI、监控、工单事件触发任务 | 每条自动化独立 HMAC 密钥、时间窗、幂等键 |
| Server Relay | 互联网外部系统 → Server → App | SaaS/CI/CRM 投递到可能离线的指定设备 | scoped service token + HMAC；Server 持久队列；设备租约与 ack |
| MCP Connector | AgentMate → 外部系统 | Agent 在一次 Run 内查询或操作外部工具 | 本机可信启动定义 + 连接凭据；Server 目录不能下发可执行命令，MCP 调用受 Run 超时/取消约束 |
| Skill | AgentMate 内部 | 封装指令、文件、工具绑定和权限声明 | 不是网络鉴权协议，也不直接提供公网入口 |
| Channel | 双向消息 | Telegram、邮件等人机消息入口/结果投递 | 渠道账户绑定和发送者映射；不是通用系统事件总线 |

建议先按事件方向选接入面：同机事件用 Local Webhook，公网事件用 Server Relay，Run 主动访问外部服务用 MCP；需要用户身份的管理操作
才使用 REST API。不要把 Skill 当成外部 API，也不要把用户 Bearer 填进第三方 Webhook 配置。

## 2. Automation Webhook

### 2.1 创建

1. 在“自动化”中新建或编辑任务，把触发方式设为 `Webhook` 并保存；
2. 再次打开任务，点击“生成地址与密钥”；
3. 立即把一次性显示的 `whsec_...` 密钥保存到外部系统的 secret manager；
4. 将页面显示的 `/api/webhooks/automations/{webhook_id}` 地址配置为 HTTP `POST` 目标。

读取配置不会返回密钥。遗失密钥只能轮换，轮换后旧密钥立即失效；停用会删除 hook identity 及其投递审计。

### 2.2 请求契约

- 方法：`POST`
- 正文：UTF-8 JSON object，最大 64 KiB；数组、标量和非 JSON 均拒绝；
- `X-AgentMate-Timestamp`：当前 Unix 秒，允许服务器时间前后 300 秒；
- `X-AgentMate-Idempotency-Key`：1–120 个 ASCII 字符，首字符为字母或数字，其余可含 `._:-`；
- `X-AgentMate-Signature`：`v1=<hex>`；其中：

```text
signed_payload = timestamp + "." + exact_raw_request_body
signature = hex(HMAC-SHA256(webhook_secret, signed_payload))
```

签名必须基于实际发送的原始字节。JSON 重新格式化会改变签名，因此应先序列化一次，再用同一份字节签名并发送。

Python 示例（占位密钥，不是真实凭据）：

```python
import hashlib, hmac, json, time, urllib.request

url = "http://127.0.0.1:8101/api/webhooks/automations/wh_REPLACE_ME"
secret = "whsec_REPLACE_ME"
timestamp = str(int(time.time()))
body = json.dumps({"event": "build.failed", "build_id": "b-123"},
                  separators=(",", ":")).encode("utf-8")
signature = hmac.new(secret.encode(), timestamp.encode() + b"." + body,
                     hashlib.sha256).hexdigest()
request = urllib.request.Request(url, data=body, method="POST", headers={
    "Content-Type": "application/json",
    "X-AgentMate-Timestamp": timestamp,
    "X-AgentMate-Idempotency-Key": "build-b-123",
    "X-AgentMate-Signature": "v1=" + signature,
})
print(urllib.request.urlopen(request).read().decode())
```

### 2.3 幂等、并发与响应

- 首次合法投递返回 `202`，包含稳定的 `delivery_id`、`fire_id`、`session_id` 和状态；
- 同一 hook 下，同一幂等键与同一原始正文返回原 fire，`duplicate=true`，不会重复执行；
- 同一幂等键换了正文返回 `409`；调用方必须使用新的业务事件键；
- 同一自动化已有运行中/等待重试的 fire 时返回 `409 automation is busy`。调用方应保留同一幂等键与正文退避重试；
- 过期时间戳或错误签名返回通用 `401`，不暴露 hook 是否存在；
- 非 Webhook、停用或已删除的自动化失败关闭，不会降级为匿名用户执行。

投递审计只保存幂等键、正文 SHA-256、状态和关联 fire，不保存原始 HTTP 正文。为支持本机崩溃恢复与重试，解析后的
JSON 只保存在本地 fire 执行记录中，并作为明确标注的“不可信事实输入”交给模型；它不会进入 Server outbox。

## 3. Server Relay（公网到离线设备）

### 3.1 安全拓扑

App 后台每 20 秒使用已登录的 Server 用户 token 向 Server 长轮询式 pull，首次 pull 会登记一个本机持久的不透明
`device-<uuid>`。外部系统只连 Server HTTPS，不得把 App 的 `127.0.0.1:8101` 暴露到公网。Server 只保存事件 JSON、目标
automation/device 和投递状态，不保存 LLM/连接器凭据、会话正文或工作区文件。

### 3.2 开通步骤

1. App 使用目标用户登录 Server，保持运行一轮；
2. 用用户 Bearer 调 `GET /api/relay/devices` 取目标 `device_id`；
3. 用同一用户 Bearer 调 `POST /api/integrations/service-accounts`，创建包含 `relay:write` / `relay:read` 的服务身份；
4. 立即把仅显示一次的 `ams_...` token 存入外部系统 secret manager。读取列表不会回显 token；遗失只能 rotate，旧 token 立即失效；
5. 在 App 为同一用户创建已启用的 Webhook 自动化，将其本地 `automation_id` 作为事件目标。

### 3.3 事件契约

`POST /api/relay/events` 的 JSON 最大 64 KiB：

```json
{
  "event_key": "build-20260803-42",
  "device_id": "device-00000000-0000-0000-0000-000000000000",
  "automation_id": "local-automation-uuid",
  "payload": {"event": "build.failed", "build_id": "42"}
}
```

`Authorization: Bearer ams_...`；`X-AgentMate-Timestamp` 与 `X-AgentMate-Signature` 的签名方法与 2.2 相同，但 HMAC secret 是
service token。`event_key` 在同一服务身份内幂等：完全相同的重试返回原事件，换目标或正文返回 `409`。

Server 按分钟对服务身份限速（默认 60）。App pull 后获得有时租约；离线/崩溃未 ack 时租约到期自动重投，错账号、
错设备或过期 lease token 不能确认。外部系统可使用 `relay:read` token 调 `GET /api/relay/events/{event_id}` 查询
`pending / leased / succeeded / failed / dead_letter`。

## 4. Local-first 网络边界

默认 backend 只监听 `127.0.0.1:8101`，所以同机脚本和本机服务可直接调用；互联网 SaaS 无法直接回调该地址。
若需要远程回调，优先使用上述 Server Relay。只有自托管特殊网关场景才应将 HTTPS 网关/隧道转发到本机，并同时满足：

- TLS、来源限速、请求体上限和访问日志脱敏；
- 网关不得终止或重写上述 HMAC 正文，除非重新按本机 hook secret 签名；
- hook secret 不进入前端源码、Git、日志、Server 目录或普通环境透传；
- 离线时由网关持久重试，同一业务事件始终复用同一幂等键。

Server Relay 是应用层持久中继；生产部署仍需由用户基建提供 TLS、域名、备份与可用性。
