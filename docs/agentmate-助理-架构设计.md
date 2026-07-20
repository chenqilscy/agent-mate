# AgentMate 多助理、多渠道架构

> 状态：助理、Telegram 与邮件渠道已实现；企业微信和 WhatsApp 仅作为不可用类型展示。
> 基础实现对应 WB-086～WB-096，本文描述当前边界，不再保留实施前分片排期。

## 1. 定位

“助理”是一个可长期存在、可由 App 或外部渠道触达的本地 agent 配置。每个助理拥有独立的指令、
模型、权限模式、工作空间和专家/Skill/连接器 loadout；一个助理可以绑定多个渠道。

助理仍在 App backend 本机执行。AgentMate Server/Console 不保存助理渠道凭据，也不代替本机轮询或
发送消息。

## 2. 当前对象

### 2.1 assistants

主要字段：

```text
id / owner_id / name / avatar
instruction / model / mode
workspace              default | project:<id> | dedicated
experts / skills / connectors
created_at / updated_at
```

- `dedicated` 使用 `workspace/assistants/<id>/`。
- `project:<id>` 复用所选项目工作区，并继续受项目访问角色约束。
- Skill 与专家保存稳定 slug；运行时必须解析到真实、可用定义。

### 2.2 channels

主要字段：

```text
id / assistant_id / type
config / enabled / update_offset / created_at
```

当前类型：

| 类型 | 状态 | 接入方式 |
|---|---|---|
| Telegram | 可用 | Bot API long polling；token + chat_id/配对约束 |
| 邮件 | 可用 | IMAP 拉取未读 + SMTP 回复；账号与服务器配置存本机 |
| 企业微信 | 不可用 | 类型注册表明确返回 `available=false` |
| WhatsApp | 不可用 | 类型注册表明确返回 `available=false` |

不可用类型不得显示可保存的假开关或成功 toast。

## 3. 运行时

```text
外部消息
  → ChannelManager 轮询
  → 渠道鉴权/白名单/去重
  → channel_session 映射到 AgentMate session
  → run_chat（助理 instruction + model + mode + workspace + loadout）
  → 收集最终回复
  → 渠道 API 发送
```

App 内的 `/api/assistants/{id}/say` 走同一助理运行配置，但不经过外部渠道收发。

`ChannelManager` 根据数据库中的启用渠道维护 poller：配置变化会更新运行签名并重启对应 poller；停止
backend 时统一取消。单个渠道失败要记录并重试，不能阻断其它渠道或 App 对话。

## 4. 会话映射与防循环

- 同一外部对话映射到稳定的本地 session，保留上下文但不把正文上传 Server。
- Telegram 使用 update offset 避免重复消费。
- 邮件只处理授权来源和符合条件的未读邮件；回复必须带可识别的关联信息并避免处理自己的出站邮件，
  防止自回复循环。
- 渠道消息最终仍经过正常的 owner、workspace、工具权限与安全策略检查。

## 5. 凭据与隐私

- 渠道 token、邮箱密码和 OAuth 类 secret 只存 App 本地 DB，不进 Server、前端构建产物、日志或普通
  子进程环境。
- AgentMate 是仅绑定 `127.0.0.1` 的 local-first App；用户可在本机设置 UI 查看和修改自己的渠道
  配置，这是显式的本机管理能力。API 与日志仍须避免无关回显和错误泄漏。
- 渠道收到的正文进入本机会话；Server 最多接收用户明确开启的最小时间线元数据。
- 删除渠道要停止 poller 并清理映射/状态；解绑不得留下继续运行的旧凭据。

## 6. 前端

`AssistantView` 使用主从布局：左侧为助理列表，右侧包含“对话 / 设置 / 渠道”三个 tab。

- 对话：复用本地 session 与 composer 语义。
- 设置：编辑指令、模型、模式、工作空间和 loadout。
- 渠道：只为 `available=true` 的类型提供真实表单、校验、启停、解绑和删除。
- 状态点来自真实 channel `running/enabled` 状态，不从是否填过表单推断成功。

## 7. 新增渠道的门槛

新增企业微信、WhatsApp 或其它渠道前，必须完成：

1. 真实授权/凭据校验与本机安全存储；
2. 入站消费、offset/幂等、白名单或配对；
3. 出站发送、长度/格式/附件限制与错误回传；
4. 自回复循环与重放防护；
5. 多助理、多渠道并发隔离；
6. 硬重启 backend 后的真机收发验证。

只有 UI 表单、目录卡或提示词不满足“可用渠道”的定义。

## 8. 已知限制

- ChannelManager 当前跟随单机 backend 生命周期，不是独立高可用消息服务。
- 外部渠道执行仍受本机在线、电源、网络与邮箱/Bot 平台策略影响。
- 渠道级速率限制、统一重试队列、运营审计与企业级凭据轮换仍需单独设计。
- 助理是单个 runtime 配置，不等同于真实多 Agent 团队调度。
