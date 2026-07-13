---
id: WB-152
title: 安全中心真后端 —— 命令安全策略(黑名单·真拦截) + 审计日志(真记录 run_command/网络访问)
severity: P2
area: fullstack
status: fixed
origin: 🆕 近期改动
files:
  - backend/agent/security.py
  - backend/agent/tools.py
  - backend/agent/runtime.py
  - backend/routers/security.py
  - src/components/settings/SettingsModal.tsx
created: 2026-07-14
---

## 问题

设置中心「安全中心」tab 还是「即将上线」占位。用户要「接沙箱策略/审计日志」——做成**真生效**：
命令安全策略（黑名单命中即拦截 `run_command`）+ 审计日志（真记录命令/网络访问的执行与拦截）。
不做那些需要执行层大改才生效的项（文件白名单/网络域名规则/数据网关），诚实占位（铁律#1）。

## 触发场景

设置 → 安全中心 → 命令安全加规则「rm -rf」→ 之后 agent 若尝试跑含「rm -rf」的命令，被真拦截、
返回被拦截说明、审计里出现一条 blocked；正常命令执行则记一条 executed（含命令/URL）。审计可清空。

## 影响

P2：给 local-first 用户一个真实可控的命令防护 + 可见的审计轨迹；只碰 run_command 一处，风险可控、fail-open。

## 建议修法

1. **`agent/security.py`**：owner contextvar（`set_security_context`/`current_owner`，run_chat 设，随
   `asyncio.to_thread` 传入工具线程）；命令黑名单 KV `security.cmd_blocklist`（get/set，JSON）；
   `check_command(cmd)`→(allowed, 命中规则)；`audit(owner, tool, detail, action)`。
2. **DB**：`audit_log` 表（owner_id/tool/detail/action/created_at）+ add/list/clear。
3. **`agent/tools.py`** `_run_command_run`：先 `check_command`，命中 → 审计 blocked + 返回被拦截说明、不执行；
   否则执行后审计 executed（detail=命令，curl/wget 即「网络访问」）。
4. **`agent/runtime.py`**：`security.set_security_context(user.id)`（紧随 set_work_context）。
5. **路由 `routers/security.py`**：`GET/PUT /api/security/policy`（命令黑名单）、`GET /api/security/audit`、
   `POST /api/security/audit/clear`。`main.py` 注册。
6. **前端**：`api.security*`；`SettingsModal` 安全中心 panel——命令黑名单编辑 + 审计列表(工具/详情/时间 +
   executed/blocked 徽章)+清空；文件/网络/数据网关等诚实占位「由本地运行时提供 / 即将上线」。

## 验证

- `py_compile` + `tsc`。
- 加规则「rm -rf」→ 让 agent 跑 `rm -rf x` 被拦截(返回拦截说明)、审计现 blocked；跑正常命令现 executed。
- 清空审计生效；GET 回显策略。
- 明暗双主题看 panel。

## 处理记录（2026-07-14）

- 改动：
  - 新增 `backend/agent/security.py`：owner contextvar（`set_security_context`/`current_owner`）+ 命令黑名单 KV `security.cmd_blocklist`（get/set，JSON，≤100 条）+ `check_command`（子串·大小写不敏感，fail-open）+ `audit`（吞异常不影响执行）。
  - `backend/storage/db.py`：`audit_log` 表 + `add_audit`（写后裁旧至 500）/`list_audit`/`clear_audit`。
  - `backend/agent/tools.py` `_run_command_run`：先 `check_command`，命中 → 审计 blocked + 返回拦截说明、不执行；否则执行后审计 executed。
  - `backend/agent/runtime.py`：`security.set_security_context(user.id)`（紧随 set_work_context，随 to_thread 传入工具线程）。
  - 新增 `backend/routers/security.py`：`GET/PUT /api/security/policy`、`GET /api/security/audit`、`POST /api/security/audit/clear`；`main.py` 注册。
  - 前端 `src/lib/{types,api}.ts`：`AuditEntry` + `securityPolicy/saveSecurityPolicy/securityAudit/clearAudit`。
  - `src/components/settings/SettingsModal.tsx`：`SecurityPanel`——命令黑名单 chips 编辑 + 审计列表（已执行/已拦截徽章）+ 清空 + 文件/网络/数据网关诚实占位。
  - `src/styles/app.css`：`set-chips/set-chip2*/set-audit*/set-badge*` 样式。
- 验证：
  - `py_compile` + `tsc` 过。
  - API：GET policy 空；PUT 黑名单回显。
  - **真拦截**：黑名单加 `echo CANARY_BLOCK` → 真 agent（exec）跑 `echo CANARY_BLOCK_777` → 审计出现 `blocked | run_command | echo CANARY_BLOCK_777`（命中即拦截、未执行）。
  - **真审计 executed**：直调真 `run_command.run({'echo HELLO_EXEC_OK'})`（设 security 上下文）→ 退出码 0 真输出 + 审计 `executed`。（正常命令的 agent 链路遇 LLM 429 限流，改直调真工具证明，非代码问题。）
  - CDP 明暗双主题实截 panel（黑名单 chip + 已执行/已拦截双徽章 + 占位，无坑）。
  - 清理：审计清空、黑名单清空、max_rounds 复位 12。
- commit：未提交（与 WB-150 一并，待用户确认）。
