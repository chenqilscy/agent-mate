# 桌面版构建与发布（路线 A）

AgentMate 用 Tauri 2 打成桌面应用：前端在系统 WebView2 里显示，Rust 壳负责窗口、
托盘、自动更新，并把 Python 后端作为 **sidecar** 打成单文件 exe 一起分发、启动时拉起、
退出时清理。本文覆盖构建、发布、签名与已知事项。

## 前置

- Node 20+ / pnpm、Python 3.11+（后端 venv 已装 PyInstaller）、Rust（`cargo` / `rustc`）。
- Windows 打包还需要 WebView2 运行时（Win10/11 一般自带）。WiX / NSIS 由 `tauri build`
  首次自动下载。

## 开发运行

两种方式：

**浏览器开发**（全功能、开发库 `backend/agentmate.db`）：
```bash
cd backend && ./.venv/Scripts/python.exe main.py     # 后端 :8000
pnpm dev                                              # Vite :5173
# 浏览器打开 http://localhost:5173
```

**桌面壳里跑**（验证打包行为）：
```bash
backend/.venv/Scripts/python.exe backend/build_sidecar.py   # 构建 sidecar（改了后端才需重跑）
pnpm dev                                                     # Vite :5173
pnpm tauri:dev                                               # 原生窗口，壳自动拉起 sidecar 后端
```
> 桌面壳用的是**打包版后端**：数据目录在 `%LOCALAPPDATA%/AgentMate`，与开发库隔离。

## 构建安装包

```bash
# 1) 构建后端 sidecar（PyInstaller onefile → src-tauri/binaries/）
backend/.venv/Scripts/python.exe backend/build_sidecar.py
# 2) 出安装包（release 编译 + WiX/NSIS 打包）
pnpm tauri build
```
产物在 `src-tauri/target/release/bundle/`：
- `msi/AgentMate_<ver>_x64_en-US.msi`（WiX）
- `nsis/AgentMate_<ver>_x64-setup.exe`（NSIS）

**注意**：`tauri build` 的 `beforeBuildCommand` 是 `pnpm build`（含 `tsc -b`），**要求整个
前端类型检查通过**。若因在改的代码报 TS 错，先修好，或临时用 `npx vite build` 预构建 dist
并把 `beforeBuildCommand` 置空来出包。

## 架构要点

- **sidecar**：`backend/build_sidecar.py` 跑 `agentmate-backend.spec`（onefile），按 Rust
  目标三元组命名拷进 `src-tauri/binaries/`。Windows 上 Tauri 按 `x86_64-pc-windows-msvc`
  匹配（即便 host 是 gnu），脚本已同时放 msvc/gnu 两个名字。
- **进程接管**：`src-tauri/src/lib.rs` 启动时 `spawn` sidecar、drain 其输出、退出时 kill。
- **前端 API 基址**：壳内自动走绝对 `http://127.0.0.1:8000/api`（无 Vite 代理），后端 CORS
  已放行 tauri 源。
- **冻结感知**：`config.py` 打包后在 `%LOCALAPPDATA%/AgentMate` 存放 DB/工作区，`.env` 在
  exe 旁/数据目录查找。
- **本地连接器**：内置 MCP 服务器（本地便签/时间助手/工作区检索）在打包版里改用**内存
  传输**同进程运行（不起子进程），可用。第三方 stdio 连接器（GitHub）打包版默认禁用，
  可设 `AGENTMATE_BUNDLE_CONNECTORS=1` 尝试。

## 自动更新（脚手架，接端点即生效）

已装 `tauri-plugin-updater` + `tauri-plugin-process`，签名公钥在 `tauri.conf.json`
`plugins.updater.pubkey`，私钥 `src-tauri/.updater-key`（**已 gitignore，务必妥善保管**）。
菜单栏「帮助(H)」触发检查更新。

上线步骤：
1. 把 `plugins.updater.endpoints` 里的占位 URL 换成你托管 `latest.json` 的地址
   （支持 `{{target}}`/`{{arch}}`/`{{current_version}}` 占位）。
2. 构建时提供私钥签名：
   ```bash
   set TAURI_SIGNING_PRIVATE_KEY=<私钥内容或路径>
   set TAURI_SIGNING_PRIVATE_KEY_PASSWORD=<密码，无则留空>
   pnpm tauri build
   ```
   `bundle.createUpdaterArtifacts` 已开启，会产出 `.sig` 签名文件。
3. 把新版本的安装包与签名、以及 `latest.json`（含 version/notes/platforms+signature）
   发布到端点。客户端「检查更新」即可下载安装并自重启。

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

- **A4 自动更新**需你提供发布端点才真正生效（见上）。
- **代码签名**需你购买证书（见上）。
- 第三方 stdio 连接器（GitHub 等）在打包版里默认禁用（内置连接器已可用）。
