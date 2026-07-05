---
id: WB-011
title: 连接器子进程继承整个 os.environ（含 LLM_API_KEY）
severity: P1
area: backend
status: fixed
origin: 🆕 近期改动
files:
  - backend/agent/mcp_client.py:75
  - backend/config.py:16
created: 2026-07-06
---

## 问题
`open_connectors` 用 `{**os.environ, ...}` 作为 MCP 连接器子进程的 env（`mcp_client.py:75`）。`load_dotenv` 会把 `LLM_API_KEY` 写入 `os.environ`（`config.py:16`）。对真实第三方 MCP 服务器（GitHub / 腾讯文档等）等于把后端 API Key 及全部环境变量泄漏给连接器进程。

与项目硬线「API Key 只存后端、绝不外泄」直接冲突。

## 触发场景
启用任何真实（第三方）连接器。当前只有本地 `notes` demo 服务器，影响有限，但一旦接真实连接器即泄漏。

## 影响
密钥泄漏面。安全性问题。

## 建议修法
只传白名单 env，不整体透传 `os.environ`：
```python
base_env = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", **env}
# 需要 PATH 之类可显式挑选；绝不含 LLM_API_KEY / LLM_API_BASE
```

## 验证
启动连接器后，在其子进程内打印 env 确认不含 `LLM_API_KEY`；本地 notes 连接器仍能正常读写 `WORKBUDDY_NOTES_DIR`。

## 处理记录（2026-07-06）
- 改动：连接器子进程 env 由 `{**os.environ,...}` 改为安全白名单 `_safe_base_env()`（仅转发 PATH/SYSTEMROOT/TEMP 等无害变量），绝不含 LLM_API_KEY/LLM_API_BASE。（backend/agent/mcp_client.py）
- 验证：verify_backend.py「env excludes LLM_API_KEY / LLM_API_BASE、keeps PATH」PASS；本地 notes 连接器仍收到 WORKBUDDY_NOTES_DIR。
