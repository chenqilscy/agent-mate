---
id: WB-208
title: 产品仍使用腾讯同名 WorkBuddy 品牌，容易混淆
severity: P1
area: fullstack
status: fixed
origin: 既有实现
files:
  - src/components/layout/Sidebar.tsx:204
  - src/views/HomeView.tsx:57
  - backend/agent/runtime.py:44
  - src-tauri/tauri.conf.json:3
  - hub/web/console.html:6
created: 2026-07-20
---

## 问题

当前应用、桌面壳、Agent 身份和管理端均使用 `WorkBuddy`，与作为视觉参考的腾讯 WorkBuddy 同名，用户在沟通、演示和分发时难以区分两套产品。

## 触发场景

启动本地应用或打开 Manager 后，窗口标题、首页、侧栏、对话回复、托盘和管理端都显示 `WorkBuddy`，无法判断当前使用的是本项目还是腾讯产品。

## 影响

P1：产品身份不独立，容易造成来源误认；应用截图、安装包、导出内容和对外沟通均存在品牌混淆。

## 建议修法

- 用户可见产品名统一为 `AgentMate`，覆盖 App、Agent 身份、桌面壳、托盘、导出内容和 Manager。
- 更新主要项目文档，明确 AgentMate 的实现参考来自腾讯 WorkBuddy；参考原型使用明确的 `tencent-workbuddy-*` 文件名与说明保证溯源。
- 技术标识也彻底改名：数据库与数据目录、环境变量、sidecar/可执行文件、应用 identifier、日志命名空间、邮件头及测试辅助代码不保留旧别名。

## 验证

- App 首页、侧栏、对话、设置、项目提示和导出内容不再显示旧产品名。
- 桌面窗口、托盘和 Manager 管理端显示 `AgentMate`。
- 仓库除明确标注为“腾讯 WorkBuddy 参考”的原型内容和本 issue 的问题背景外，不再存在 `workbuddy` 技术标识。
- `npx tsc --noEmit`、生产构建、Python 编译和 Tauri 配置检查通过。

## 处理记录（2026-07-20）

- 改动：用户可见品牌统一为 `AgentMate`，覆盖首页、侧栏、对话署名、设置说明、项目提示、导出内容、LLM 系统身份、FastAPI 标题、AgentMate Hub / Manager、Tauri 窗口与托盘、安装包名称及主要现状文档；邮件自回复标记只使用 `X-AgentMate-Assistant`。
- 二次调整：按产品决策取消全部旧兼容标识，统一改为 `com.agentmate.app`、`AGENTMATE_*`、`%LOCALAPPDATA%/AgentMate`、`~/.agentmate` 和 `agentmate-backend`；不再自动读取旧路径或旧变量，避免长期维护双命名体系。
- 文件与数据：实现方案、Hub/助理/数据规范、参考原型、PyInstaller spec 和功能测试辅助模块均改为新文件名；本地开发库从 `agentmate.db` 直接承接原数据，旧库文件不再存在；构建目录只发布 `agentmate-backend-*`。
- 验证：新增品牌契约回归，完整 regression 9/9 通过；`npx tsc --noEmit`、`npx vite build`、Python 编译、全量清缓存后的 `cargo check` 和 `git diff --check` 通过。浏览器实测 App 标题/品牌区与 Manager 登录页均显示 AgentMate；硬重启后 `/openapi.json` 分别返回 `AgentMate API` 与 `AgentMate Hub API`。冻结后的 `agentmate-backend.exe` 已通过真实启动 smoke test，相关 numpy 打包问题由 WB-209 修复并关闭。
- commit：本次提交。
