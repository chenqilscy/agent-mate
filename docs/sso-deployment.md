# AgentMate Server 联合登录部署

## 1. 边界

Server 是唯一账号权威和 SSO broker。App、Console 不接触 provider client secret：它们向 Server 创建一次性登录 attempt，
在系统浏览器完成授权，再用仅持有于发起端的 `attempt_token` 轮询结果。回调不会把 Server Bearer token 放进 URL、HTML 或日志。

未配置或停用的 provider 不出现在 App/Console。外部身份以 `(provider, subject)` 唯一绑定账号；即使 provider 返回与现有账号
相同的已验证邮箱，也不会自动合并，必须先用现有账号登录并以 `mode=link` 显式绑定。

## 2. 公网前置条件

- 首次部署先设置一次性的 `AGENTMATE_BOOTSTRAP_ADMIN_SECRET`，调用 `POST /api/auth/bootstrap` 创建首个管理员；
  创建成功后移除该环境变量。公开 `/api/auth/register` 不再隐式创建首管理员；
- 正式环境设置 `AGENTMATE_ENVIRONMENT=production` 和独立的
  `AGENTMATE_SSO_SECRET_ENCRYPTION_KEY`。未配置主密钥时生产环境拒绝写入 Provider secret；
  `AGENTMATE_SSO_SECRET_ENCRYPTION_KEY_ID` 标识当前密钥（默认 `primary`）。轮换时先把旧
  `key_id -> secret` 以 JSON 放入 `AGENTMATE_SSO_SECRET_ENCRYPTION_PREVIOUS_KEYS`，配置新密钥和
  新 key ID 后启动 Server；启动迁移或 `POST /api/admin/sso/rotate-encryption` 会原子重加密，确认
  readiness 全绿后再移除 previous key。密钥值不得写入仓库或日志；
- 将 `AGENTMATE_SSO_PUBLIC_BASE_URL` 设为 Server 的公开 HTTPS origin，例如 `https://agentmate.example.com`；
- 反向代理保留原始 query，限制 `/api/auth/*` 请求速率并记录脱敏访问日志；
- Google / 微信开放平台 / Telegram BotFather 中登记精确回调：
  - `https://agentmate.example.com/api/auth/sso/google/callback`
  - `https://agentmate.example.com/api/auth/sso/wechat/callback`
  - `https://agentmate.example.com/api/auth/sso/telegram/callback`
- 微信需要已审核的网站应用与 `snsapi_login` 权限；Telegram 使用当前 OIDC code + PKCE 流程；Google 使用 OIDC code + PKCE。

## 3. Provider 配置

只有平台管理员能配置。优先使用 Console「平台设置 → 联合登录」；下列 API 适合自动化部署。`client_secret` 是只写字段：
读取接口仅返回 `secret_configured`，更新时省略它会保留旧值。

```http
PUT /api/admin/sso/providers/google
Authorization: Bearer <platform-admin-token>
Content-Type: application/json

{"enabled":true,"client_id":"<client-id>","client_secret":"<client-secret>"}
```

`google` 可换为 `wechat` 或 `telegram`。先以 `enabled:false` 保存/轮换，再完成 provider 控制台配置和回调检查，最后启用。
`GET /api/admin/sso/providers` 不回显任何 secret；`GET /api/auth/sso/providers` 只列出已启用且凭据完整的入口。
Server 使用 AES-GCM 将 Provider secret 加密后写入 SQLite；开发环境会在数据库旁生成独立的、已忽略提交的
`.sso.key`，生产环境必须使用部署环境注入的主密钥。`GET /api/admin/sso/audit` 返回脱敏配置审计，
`GET /api/admin/sso/readiness` 返回公网回调、注册策略、密钥保护及每个 Provider 的上线自检结果，
其中会真实解密已配置 secret；`secret_decryption_failed` 是发布阻断项，而不是延迟到首次登录才发现。

## 4. 首次注册与账号绑定

默认 `AGENTMATE_SSO_REGISTRATION_POLICY=invite_only`。平台管理员创建一次性、哈希存储的注册邀请码：

```http
POST /api/admin/sso/signup-invites
Authorization: Bearer <platform-admin-token>
Content-Type: application/json

{"ttl_seconds":86400}
```

返回的 `ami_...` 只显示一次。App/Console 首次联合登录时填写；已绑定用户留空。可显式改为 `open`、`existing_only` 或
`disabled`，生产环境建议保留 `invite_only`。账号绑定由已登录用户调用 `POST /api/auth/sso/start` 且传 `mode=link`；
`GET /api/auth/identities` 查询，`DELETE /api/auth/identities/{provider}` 解绑。没有本地口令的账号不能删除最后一种登录方式。

## 5. 安全与运维

- Google/Telegram 校验 state、nonce、PKCE、JWT 签名、issuer、audience 与过期时间；Google 邮箱必须为 verified；
- 微信使用一次性 state，code 与 AppSecret 只由 Server 后端交换，主体优先使用 `unionid`；
- state、登录 attempt、邀请码与会话 token 均为一次性或有界生命周期；数据库只保存 Bearer token 的 SHA-256 key；
- 新口令使用 scrypt；存量 PBKDF2 账号在下一次成功登录时自动升级；登录与 SSO start 使用持久分钟窗限速；
- provider 外部真实验收必须使用部署方自己的已审核应用、域名和凭据。仓库测试只验证协议、安全状态机和失败关闭，不包含真实 secret。

## 6. 真实 Provider 验收

每个 Provider 都必须分别完成，不能用协议单测替代：

1. Console 自检显示该 Provider `configured=true`、`ready_for_external_test=true`；
2. 使用从未绑定的真实账号和一次性邀请码完成首次登录，确认创建一个普通账户而非平台管理员；
3. 登出后再次登录，确认复用同一 `account_id`，邀请码不可重放；
4. 使用已有密码账户执行显式绑定，确认同邮箱不会自动合并、冲突 subject 失败关闭；
5. 管理员暂停账户，确认现有 App/Console 会话立即 401，重新 SSO 也不能取得 token；
6. 轮换 Provider secret，确认旧值不回显、数据库无明文、审计只出现 `client_secret_rotated`；
7. 保存 Provider 控制台回调配置截图、Server 脱敏审计、测试账号 ID 和时间作为部署证据，随后清理测试绑定。
