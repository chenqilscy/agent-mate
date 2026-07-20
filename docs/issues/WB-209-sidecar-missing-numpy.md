---
id: WB-209
title: PyInstaller sidecar 缺少 numpy，打包后端无法启动
severity: P1
area: backend
status: fixed
origin: 既有实现
files:
  - backend/agentmate-backend.spec:1
  - backend/build_sidecar.py:27
created: 2026-07-20
---

## 问题

`backend/build_sidecar.py` 能成功生成 `agentmate-backend.exe`，但真启动时在 `agent.memory` 导入阶段报 `ModuleNotFoundError: No module named 'numpy'`。PyInstaller 分析日志处理了 numpy 相关依赖，但最终 one-file 包未包含可导入的 numpy 模块。

## 触发场景

运行 `backend/.venv/Scripts/python.exe backend/build_sidecar.py`，再以独立端口启动 `backend/dist/agentmate-backend.exe`，进程立即以退出码 1 结束，无法提供 API。

## 影响

P1：开发模式正常，但桌面安装包内的 Python sidecar 无法启动，导致桌面壳无法使用后端能力。

## 建议修法

- 审查 `agentmate-backend.spec` 的 hidden imports / collect 配置，确保 numpy 及其运行时依赖被完整收集。
- 构建后增加 sidecar 真启动 smoke test，不能只以 PyInstaller 退出码 0 作为成功标准。

## 验证

- 重建 sidecar 后以隔离端口启动，`GET /openapi.json` 返回 `AgentMate API`。
- `src-tauri/binaries/agentmate-backend-*` 两个目标产物均来自通过 smoke test 的同一 exe。

## 处理记录（2026-07-20）

- 改动：从 `backend/agentmate-backend.spec` 的显式排除列表移除运行时必需的 `numpy`，重新构建 `agentmate-backend.exe` 并同步桌面 GNU/MSVC sidecar 产物。
- 验证：以隔离端口真实启动冻结后的 sidecar，`GET /openapi.json` 返回 `AgentMate API`；dist、GNU、MSVC 三份可执行文件 SHA-256 均为 `6FA6A10BEAB30DE27E9A60A3F02D13CC1D996D19262AC12CD65847E32CB0E02C`。
- commit：本次提交。
