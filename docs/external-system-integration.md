# AgentMate 外部系统接入

## 1. 接入面怎么选

| 接入面 | 方向 | 适用场景 | 身份与边界 |
|---|---|---|---|
| App REST API | 外部系统 → AgentMate | 代表真实用户管理项目、会话、自动化 | 用户 Bearer；按 owner/项目成员权限校验 |
| Automation Webhook | 外部系统 → AgentMate | CI、监控、工单、CRM 事件触发无人值守任务 | 每条自动化独立 HMAC 密钥、时间窗、幂等键 |
| MCP Connector | AgentMate → 外部系统 | Agent 在一次 Run 内查询或操作外部工具 | 连接器配置与工具权限；MCP 工具仍受 Run 审批/沙箱约束 |
| Skill | AgentMate 内部 | 封装指令、文件、工具绑定和权限声明 | 不是网络鉴权协议，也不直接提供公网入口 |
| Channel | 双向消息 | Telegram、邮件等人机消息入口/结果投递 | 渠道账户绑定和发送者映射；不是通用系统事件总线 |

建议先按事件方向选接入面：外部事件启动任务用 Webhook，Run 主动访问外部服务用 MCP；需要用户身份的管理操作
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

## 3. Local-first 网络边界

默认 backend 只监听 `127.0.0.1:8101`，所以同机脚本和本机服务可直接调用；互联网 SaaS 无法直接回调该地址。
若需要远程回调，应由用户控制的 HTTPS 网关/隧道或未来 Server Hub 转发到本机，并同时满足：

- TLS、来源限速、请求体上限和访问日志脱敏；
- 网关不得终止或重写上述 HMAC 正文，除非重新按本机 hook secret 签名；
- hook secret 不进入前端源码、Git、日志、Server 目录或普通环境透传；
- 离线时由网关持久重试，同一业务事件始终复用同一幂等键。

当前实现没有提供托管公网 Hub；这属于部署能力，不应通过把本机 FastAPI 直接暴露到公网来替代。
