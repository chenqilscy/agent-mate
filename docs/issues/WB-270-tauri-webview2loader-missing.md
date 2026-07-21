---
id: WB-270
title: GNU Tauri 安装包遗漏 WebView2Loader.dll 导致桌面端无法启动
severity: P0
area: misc
status: fixed
origin: 既有实现
files:
  - src-tauri/tauri.windows.conf.json:1
  - scripts/validate-windows-tauri-install.ps1:1
  - docs/desktop-build.md:10
created: 2026-07-22
---

## 问题

Windows 上使用仓库当前的 `x86_64-pc-windows-gnu` Rust 工具链构建时，
`webview2-com-sys` 会让 `agentmate.exe` 动态依赖 `WebView2Loader.dll`。Cargo 已把该 DLL
复制到 `src-tauri/target/release/`，但 `src-tauri/tauri.conf.json` 的 bundle 配置没有把它
作为安装资源收入 NSIS 包。实际安装目录因此缺少 DLL，Windows 加载器在 Rust/Tauri 业务代码
运行前直接报“找不到 WebView2Loader.dll”。

## 触发场景

1. 在 Windows GNU Rust 工具链下运行 `pnpm tauri:build` 生成 NSIS 安装包。
2. 安装并从开始菜单启动 AgentMate。
3. `agentmate.exe` 报系统错误，提示缺少 `WebView2Loader.dll`，应用无法打开。

## 影响

P0：当前 Windows 安装包安装成功后仍完全无法启动，所有桌面功能不可用；重复安装同一产物
不会恢复。

## 建议修法

- 让 Windows GNU 构建产出的 `WebView2Loader.dll` 明确进入 Tauri bundle，并安装到
  `agentmate.exe` 同目录。
- 在桌面发布校验中加入安装目录依赖检查，防止“编译目录可运行、安装目录缺运行库”的产物发布。
- 文档区分 WebView2 Runtime 与 WebView2 Loader DLL，避免把本故障误判为系统 Runtime 缺失。

## 验证

- 从干净构建产物生成 NSIS 安装包并安装后，安装目录存在与当前架构匹配的
  `WebView2Loader.dll`。
- 从安装目录直接启动 `agentmate.exe`，不再出现系统 DLL 错误，窗口和 backend sidecar 正常启动。
- `npx tsc --noEmit`、`npx vite build`、Rust 编译及桌面 release 校验通过。

## 处理记录（2026-07-22）

- 改动：新增 Windows 专属 Tauri 配置，把 GNU release 构建生成的
  `target/release/WebView2Loader.dll` 映射到安装资源根目录；新增安装完整性/可选真启动校验脚本，
  并在桌面构建文档中区分 WebView2 Runtime 与 Loader DLL。
- 验证：`npx tsc --noEmit`、`npx vite build`、`cargo check --manifest-path
  src-tauri/Cargo.toml` 均通过；Tauri release 编译和 NSIS bundle 成功（本机安装验证显式关闭 updater
  artifact 生成，不改变正式签名配置）。静默安装退出码 0，安装目录的主程序、sidecar、Loader 完整，
  均输出 SHA-256；主程序和 Loader PE 架构均为 `x86_64`，缺失 Loader 及替换为 arm64 Loader 的负例
  均 fail closed。`-LaunchSmoke` 从安装目录真实启动后得到 `AgentMate` 窗口标题、有效窗口句柄、
  `agentmate-backend` 进程及健康接口 `ok=true`，不再出现 DLL 系统错误。
- commit：`d1b58e0`（安装包修复）；架构门禁见后续 WB-270 提交。
