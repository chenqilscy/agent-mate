---
id: WB-248
title: Skill 工具权限只有 plan_safe 粗粒度标记且长任务无法可靠取消隔离
severity: P1
area: backend
status: fixed
origin: 既有实现
files:
  - backend/agent/tools.py:52
  - backend/agent/runtime.py:529
  - backend/agent/runtime.py:766
created: 2026-07-21
---

## 问题

当前工具安全元数据主要是 `plan_safe`，不能表达文件读写、网络、进程、外部写入、凭据和连接器调用等
权限。同步工具通过 `asyncio.to_thread` 在 Backend 进程内执行，取消协程无法可靠终止底层线程；重型或
卡死工具缺少统一的运行时限、资源配额和崩溃隔离。

## 触发场景

- Skill release 从只读工具变为网络或外部写工具，界面无法展示权限 diff，也没有重新确认边界。
- 用户停止运行时，底层线程仍可能继续执行阻塞库调用。
- 第三方 Skill 包含 scripts，未来若直接接入当前进程会扩大密钥和主机权限暴露面。

## 影响

P1：权限审核不精确，取消语义不可靠；继续扩充工具后会成为本地执行安全和稳定性瓶颈。

## 建议修法

- 为 Tool 与 Skill release 声明结构化 permissions；合并权限时取更保守结果并记录快照。
- 为工具执行增加统一超时、取消状态和错误分类；高风险/重型工具放入独立 worker/subprocess。
- 官方内置工具随签名 App/sidecar 发布；第三方 scripts 默认不执行，未来只允许经签名和沙箱运行。

## 验证

- Run 快照可列出实际权限；新增权限的升级不能静默生效。
- 超时/取消后执行单元不再继续写入，trace 记录 timeout/cancelled。
- 未授权脚本不会被 runtime 枚举或执行。

## 处理记录

- 2026-07-21：`Tool` 新增结构化 `permissions`、`timeout_seconds`、`isolation` 契约；所有内置工具完成分类。WB-266 后 Skill 工具运营契约由 Server 数据库下发，Server 根据选中工具权威计算权限，目录 revision 同时覆盖工具目录变化；App 的执行能力报告直接来自真实实现注册表。
- 2026-07-21：Run 的 `permission_snapshot` 新增实际权限并集与逐工具执行策略；Skill release manifest 至少包含绑定工具所需权限，runtime 拒绝权限声明不足的 release。
- 2026-07-21：Skill 升级新增权限时后端返回 `permission_confirmation_required`，App 详情页展示权限差异并把用户明确同意的权限随升级请求提交，避免静默扩权。
- 2026-07-21：新增统一执行边界：普通同步工具有截止时间和取消分类，MCP 调用有 60 秒截止时间；`run_command` 使用独立进程组，停止/超时时终止完整进程树，trace 明确记录 `cancelled`/`timeout`。第三方 `scripts/` 仍不进入工具注册表。
- 2026-07-21：验证通过：Backend 权限/隔离/Skill/Run 30 项回归、Server 下行与 Console 契约 11 项回归、相关 Python `py_compile`、`npx tsc --noEmit`、`npm run build`；两项真实 PowerShell 延迟写入测试确认取消/超时后文件均未产生。
