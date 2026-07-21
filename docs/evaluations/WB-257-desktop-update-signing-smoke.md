# WB-257 桌面 updater 真实签名安装演练

日期：2026-07-22；平台：Windows x64；范围：Tauri updater 签名、NSIS 安装、失败拒绝和显式回滚。

## 演练产物

使用一次性 Tauri updater 密钥构建 0.9.9 与 1.0.0 release NSIS 包；私钥只存在系统临时目录，未进入
仓库、Server 或应用配置。正式 `src-tauri/tauri.conf.json` 的公钥、HTTPS 策略和窗口配置在演练后已还原。

| 产物 | SHA-256 |
| --- | --- |
| `AgentMate_0.9.9_x64-setup.exe` | `2ABD443EB31277212E521E509572441A19D88C9CDC8142780F1864C8A629D01A` |
| `AgentMate_0.9.9_x64-setup.exe.nsis.zip` | `C75E167681CB23C3043580825B911CBAB3D91A85195A71966C5C4FA8FD9CC318` |
| `AgentMate_0.9.9_x64-setup.exe.nsis.zip.sig` | `1CC5BBDA9E076BD3E4E7EAD512A76C57CFF95B99F32F0CC6038E90384511A8B9` |
| `AgentMate_1.0.0_x64-setup.exe` | `A68ACD512CBF12847F763D8C2717AAD88D31F9D4E7A07997C30585EC0B4C59AA` |
| `AgentMate_1.0.0_x64-setup.exe.nsis.zip` | `25C986377A2635CCE119F8879D9DCA1DC261560678E4E5B826732EA2DF46750A` |
| `AgentMate_1.0.0_x64-setup.exe.nsis.zip.sig` | `39B7FBD5EB01F2272EF30243C05D7CDABA222D983FEF944CBBA80467E2546651` |

两个 `.sig` 都由 `tauri signer sign` 生成。两个 EXE 的 `Get-AuthenticodeSignature` 都为 `NotSigned`：
本演练验证的是 Tauri updater 内容签名，不代表 Windows 可信发布者代码签名。

## 结果

1. 0.9.9 安装器静默安装退出码为 0，卸载注册表 `DisplayVersion=0.9.9`。
2. 服务器返回 1.0.0 artifact 但篡改 signature：客户端先报告 `available`，随后
   `install_error=The signature verification failed`；注册表仍为 0.9.9。
3. 换回正确 signature：客户端从 0.9.9 报告 `install_started`，NSIS 更新后注册表为 1.0.0；从已安装
   1.0.0 二进制再次检查得到 `status=latest,current_version=1.0.0`。
4. 服务器改为 0.9.9 且 `rollback=true`：1.0.0 客户端报告目标 0.9.9/rollback 并开始安装；注册表回到
   0.9.9，从已安装二进制再次检查得到 `status=latest,current_version=0.9.9`。

## 环境边界与生产差距

本机 AppCompat 会让 `%LOCALAPPDATA%\\AgentMate\\agentmate.exe` 在 Rust 入口前以 0 退出；同一已安装
二进制复制到 D 盘隔离路径后可正常运行。验收从该副本调用真实 Tauri updater，下载的 NSIS 仍真实更新
`%LOCALAPPDATA%\\AgentMate` 和卸载注册表。测试构建临时采用无窗口配置及 loopback transport，以绕开该
主机的 WebView/AppCompat 限制；这些配置均未提交，正式代码继续拒绝非 HTTPS endpoint。

生产发布方仍需提供公开 HTTPS 域名与不可变存储、正式 updater 私钥的 CI secret、与内置正式公钥匹配的
签名产物、可信 CA Windows Authenticode 证书和时间戳服务，并使用生产前后版本复跑一次安装/数据迁移/回滚。

## 回归命令

- `python -m unittest server.tests.test_desktop_update_service -v`：4/4 通过。
- `cargo test --manifest-path src-tauri/Cargo.toml --no-run` 与 `cargo check --manifest-path src-tauri/Cargo.toml`：通过。
- `cargo test` 的可执行文件在本机启动时返回 `STATUS_ENTRYPOINT_NOT_FOUND`；测试目标已编译成功，未产生断言结果。
- `npx tsc --noEmit`、`npx vite build`：通过（仅保留既有大 chunk 警告）。
- `pnpm release:validate -- release-good.json`：真实 artifact 的 sha256/size/signature manifest 通过；HTTP URL 负例退出 1。
