---
id: WB-283
title: 正式桌面更新服务缺少生产域名、CI 签名材料与上线验收
severity: P1
area: fullstack
status: deferred
origin: WB-239 关闭时拆分的外部部署门槛
files:
  - docs/desktop-build.md:74
  - docs/agentmate-实现方案.md:181
  - docs/agentmate-server-架构设计.md:227
created: 2026-07-22
---

## 问题

WB-257 已完成不可变 release、通道/灰度/暂停/回滚、HTTPS endpoint、Tauri 客户端更新入口与一次性真实
updater 密钥下的本机签名升级、错误签名拒绝和显式回滚演练。但正式生产部署仍缺少本仓库不能生成或代替的
外部材料：公开 HTTPS 域名与发布存储、受保护 CI 中的正式 Tauri updater 私钥、可信 CA 签发的 Windows
代码签名证书，以及可用于旧版→新版→回滚的两个生产签名安装版本。

## 影响

P1（部署）：产品和更新代码链可验收，但在这些材料到位并完成生产演练前，不能宣称正式桌面自动更新已经上线，
也不能用本机演练密钥、自签名证书或 HTTP 地址替代生产信任链。

## 外部前置条件

由部署方一次性提供或在受保护基础设施中完成：

1. 可由客户端访问的正式 HTTPS Server 根地址、DNS/TLS 和不可变 artifact 存储；
2. 仅在受保护 CI secret 中可用的 Tauri updater 私钥，公钥按正式构建流程注入客户端；
3. 可信 CA 签发且可在 CI 中安全调用的 Windows 代码签名证书（OV/EV）；
4. 一个正式旧版本和一个正式新版本的 MSI/NSIS 安装包、updater artifact、`.sig` 与 release 元数据；
5. 发布、暂停、回滚、审计和应急负责人及可执行时间窗。

任何私钥、证书口令、连接 token 均不得提交仓库、写入 Console 数据库或出现在 issue 验收日志中。

## 建议实施

1. 按 `docs/desktop-build.md` 在受保护 CI 构建并签署前后两个生产版本；校验二进制、签名和 release 元数据对应关系。
2. 上传到不可变 HTTPS URL，通过 Server `/api/admin/desktop-releases` 发布 beta 小比例灰度；客户端只配置正式 HTTPS 根地址。
3. 在干净 Windows 真机从旧版检查并升级到新版，确认签名、下载、安装、重启、sidecar 健康和版本回报。
4. 用被篡改或错误 updater 签名验证客户端 fail closed，不执行安装且错误可见、可审计。
5. 执行暂停与显式回滚；验证新请求停止、已安装客户端可回到指定生产版本，审计链完整。
6. 扩大灰度前确认崩溃率、更新成功率和回滚门槛；保留已签名旧版本直到观察期结束。

## 验证

- HTTPS、证书链、artifact 哈希和 updater 签名全部来自正式生产材料；
- 旧版→新版、错误签名拒绝、暂停、回滚均在真实 Windows 安装版本完成，不能只用 API、单测或开发 WebView 替代；
- Server 发布/暂停/回滚审计与客户端版本回报可相互核对；
- CI/日志/仓库中无私钥、证书口令或其他 secret；
- App/Server 回归与正式安装 smoke 均通过。

## 延后记录（2026-07-22）

- 状态：`deferred`/⏸。当前阻塞为部署方域名、受保护 CI secret、可信证书和生产发布窗口，仓库内无法安全代造。
- 解除条件：上述外部前置条件全部到位后，将本 issue 改为 `in-progress`，严格按真实生产验收步骤执行并保存脱敏证据。
- 与 WB-239 的边界：WB-239 的 R0～R5 产品/代码范围已完成；本 issue 只追踪正式生产部署，不反向把产品 epic 标为未完成。
