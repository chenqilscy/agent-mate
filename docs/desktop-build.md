# 桌面版构建与发布（路线 A）

AgentMate 用 Tauri 2 打成桌面应用：前端在系统 WebView2 里显示，Rust 壳负责窗口、
托盘、自动更新，并把 Python Local Agent 作为 **sidecar** 打成单文件 exe 一起分发、启动时拉起、
退出时清理。本文覆盖构建、发布、签名与已知事项。

## 前置

- Node 20+ / pnpm、Python 3.11+（Local Agent venv 已装 PyInstaller）、Rust（`cargo` / `rustc`）。
- Windows 打包还需要 WebView2 运行时（Win10/11 一般自带）。它与 GNU 目标动态链接所需的
  `WebView2Loader.dll` 不是同一个组件；后者由 Windows bundle 配置随安装包放到主程序同目录。
  WiX / NSIS 由 `tauri build` 首次自动下载。

## 开发运行

两种方式：

**浏览器开发**（全功能；Local Agent 兼容源码目录为 `backend/`）：
```bash
pnpm dev:local-agent                                  # Local Agent :8101
pnpm dev:app                                          # App UI :8102
# 浏览器打开 http://localhost:8102
```

**桌面壳里跑**（验证打包行为）：
```bash
backend/.venv/Scripts/python.exe backend/build_sidecar.py   # 构建 Local Agent sidecar
pnpm dev                                                     # Vite :8102
pnpm tauri:dev                                               # 原生窗口，壳自动拉起 Local Agent sidecar
```
> 桌面壳用的是**打包版 Local Agent**：数据目录在 `%LOCALAPPDATA%/AgentMate`，与开发库隔离。

## 构建安装包

```bash
# 1) 构建 Local Agent sidecar（PyInstaller onefile → src-tauri/binaries/）
backend/.venv/Scripts/python.exe backend/build_sidecar.py
# 1.1) 真启动新产物并验证受 IPC token 保护的 Local Agent 健康接口
pwsh -NoLogo -NoProfile -NonInteractive -File scripts/smoke-local-agent-sidecar.ps1
# 2) 出安装包（release 编译 + WiX/NSIS 打包）
pnpm tauri build
# 3) 安装产物后核对主程序、sidecar 与 GNU WebView2 Loader 均已落盘
powershell -ExecutionPolicy Bypass -File scripts/validate-windows-tauri-install.ps1
# 可选真启动 smoke；成功后应用保持运行，验收结束后从托盘正常退出
powershell -ExecutionPolicy Bypass -File scripts/validate-windows-tauri-install.ps1 -LaunchSmoke
```
校验脚本还会解析 PE header，要求 `agentmate.exe` 与 `WebView2Loader.dll` 架构一致；缺文件或
x86_64/arm64 混装都会 fail closed。`-LaunchSmoke` 同时等待真实窗口句柄和 sidecar 健康接口。
产物在 `src-tauri/target/release/bundle/`：
- `msi/AgentMate_<ver>_x64_en-US.msi`（WiX）
- `nsis/AgentMate_<ver>_x64-setup.exe`（NSIS）

**注意**：`tauri build` 的 `beforeBuildCommand` 是 `pnpm build`（含 `tsc -b`），**要求整个
前端类型检查通过**。若因在改的代码报 TS 错，先修好，或临时用 `npx vite build` 预构建 dist
并把 `beforeBuildCommand` 置空来出包。

## 架构要点

- **sidecar**：`backend/build_sidecar.py` 跑 `agentmate-local-agent.spec`（onefile），按 Rust
  目标三元组命名拷进 `src-tauri/binaries/`。Windows 上 Tauri 按 `x86_64-pc-windows-msvc`
  匹配（即便 host 是 gnu），脚本已同时放 msvc/gnu 两个名字。
- **WebView2 Loader**：Windows GNU Rust 目标会动态依赖 Cargo 生成到
  `src-tauri/target/release/WebView2Loader.dll` 的 Loader；`tauri.windows.conf.json` 将它安装到
  `agentmate.exe` 同目录。它缺失时 Windows 会在应用代码运行前直接拒绝启动。
- **进程接管**：`src-tauri/src/lib.rs` 启动时 `spawn` sidecar、drain 其输出、退出时 kill。
- **Local Agent API 基址**：壳内自动走绝对 `http://127.0.0.1:8101/api`（无 Vite 代理），Local Agent
  CORS 已放行 tauri 源。
- **冻结感知**：`config.py` 打包后在 `%LOCALAPPDATA%/AgentMate` 存放 DB/工作区，`.env` 在
  exe 旁/数据目录查找。
- **本地连接器**：内置 MCP 服务器（本地便签/时间助手/工作区检索）在打包版里改用**内存
  传输**同进程运行（不起子进程），可用。第三方 stdio 连接器（GitHub）打包版默认禁用，
  可设 `AGENTMATE_BUNDLE_CONNECTORS=1` 尝试。

## 自动更新

### 当前状态：发布服务与客户端链路已落地，生产域名和签名产物由部署注入

已装 `tauri-plugin-updater`，签名公钥在 `tauri.conf.json` 的 `plugins.updater.pubkey`；私钥仍只允许从
受保护 CI 注入。客户端不再编译占位 endpoint：设置中心或构建变量 `VITE_AGENTMATE_UPDATE_ENDPOINT`
提供 Server HTTPS 根地址，Rust command 校验协议后调用 Tauri updater，签名校验仍由插件完成。

Server 的 `/api/admin/desktop-releases` 管理不可变 release 与签名产物，`/api/desktop-updates/...` 按
stable/beta、平台、架构、当前版本和匿名设备哈希返回 204 或标准 Tauri manifest。通道支持稳定灰度、
最低版本强制、暂停和显式签名回滚；App 每日去重检查，下载/安装只能由用户手工触发。

### 最小上线步骤

1. 构建时提供私钥签名：
   ```bash
   set TAURI_SIGNING_PRIVATE_KEY=<私钥内容或路径>
   set TAURI_SIGNING_PRIVATE_KEY_PASSWORD=<密码，无则留空>
   pnpm tauri build
   ```
   `bundle.createUpdaterArtifacts` 已开启，会产出 `.sig` 签名文件。
2. 把 updater artifact 和 `.sig` 上传到不可变 HTTPS URL，生成 release JSON（每个平台含
   `target/arch/url/signature/sha256/size_bytes`），执行 `pnpm release:validate -- release.json`。
3. 平台管理员把验证后的 JSON POST 到 `/api/admin/desktop-releases`，再调用对应 release 的
   `/publish` 设置通道、灰度比例和最低版本；生产 App 配置同一 Server HTTPS 根地址。
4. 先在 beta 真机验证，再推进 stable 灰度。失败时暂停通道或把通道 rollback 到上一签名 release。
5. 验证从上一受支持版本升级：下载、签名校验、安装、sidecar/DB 迁移、自重启、版本显示和旧数据。

仓库提供 `scripts/desktop_update_smoke_server.py` 作为本机安装演练服务。它只绑定 `127.0.0.1`，可在
隔离的演练构建中分别提供正常签名、`--bad-signature` 和 `--rollback` manifest；不得在正式构建中
开启非 HTTPS updater 传输，也不得用演练密钥替代 CI 私钥。WB-257 的完整演练证据见
`docs/evaluations/WB-257-desktop-update-signing-smoke.md`。

### 生产发布要求

- **不可变产物**：安装包、updater artifact、`.sig`、manifest 和 release notes 按版本归档，禁止
  覆盖同版本二进制。
- **通道与灰度**：至少 stable/beta；灰度按稳定设备分桶，重复检查不能来回切版本。
- **兼容窗口**：Server API 在桌面升级周期内向后兼容；安全/协议断裂才设置强制最低版本。
- **失败回滚**：保留上一安装包和最后可用数据库备份策略；发布平台监控检查/下载/校验/安装失败码，
  不上传凭据、文件或会话正文。
- **Skill/Tool 联动**：Console 发布引用新 Tool 的 Skill 前，先确认目标客户端已经具备所需
  `app_version/tool_contract_version`；目录数据不能代替 App 更新。
- **密钥隔离**：Tauri updater 私钥和 Windows 代码签名证书只进入受保护 CI，不能进入 Console、
  Server DB、仓库或 App 安装包。

## 代码签名（去掉 SmartScreen 警告）

未签名的安装包在别人机器上会有 SmartScreen「未知发布者」警告。去掉它需要一张**受信任
CA 的代码签名证书**（OV 或 EV；**自签名无效**，SmartScreen 只认可信 CA + 声誉，EV 证书
可即时获得声誉）。有证书后：

1. 把证书装进 Windows 证书库，拿到指纹（thumbprint）。
2. 在 `tauri.conf.json` 加：
   ```json
   "bundle": {
     "windows": {
       "certificateThumbprint": "你的证书指纹",
       "digestAlgorithm": "sha256",
       "timestampUrl": "http://timestamp.digicert.com"
     }
   }
   ```
   （未配置 `certificateThumbprint` 时构建不签名——即当前状态。）
3. `pnpm tauri build` 会自动用 `signtool` 签名安装包与主 exe。

## 已知待办

- **A4 自动更新**代码链路及本机真实 updater 签名安装演练已完成；每个部署仍必须配置公开 HTTPS
  Server、CI 私钥、可信代码签名证书和生产签名产物，并用前后两个生产安装版本复跑升级/回滚；正式
  上线所需输入、步骤和退出条件由 [WB-283](issues/WB-283-production-desktop-update-deployment-acceptance.md) 追踪。
- **代码签名**需你购买证书（见上）。
- 第三方 stdio 连接器（GitHub 等）在打包版里默认禁用（内置连接器已可用）。
