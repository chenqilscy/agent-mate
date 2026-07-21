---
id: WB-273
title: Plan 模式静默忽略已选连接器
severity: P3
area: backend
status: fixed
origin: 🏚 迁移遗留
files:
  - backend/agent/runtime.py:596
created: 2026-07-22
---

## 问题
Plan 模式为避免外部副作用不启动 MCP 连接器，但运行轨迹也不显示用户已选的连接器，形成静默 no-op。

## 触发场景
挂载任一连接器，开启 Plan 后发送消息；连接器未加载且“已加载”步骤没有连接器或原因。

## 影响
P3。不会产生越权写入，但用户可能误以为规划使用了连接器中的信息。

## 建议修法
保持 Plan 不启动外部 MCP 的保守边界，把所有已选连接器记录为未加载，并在 loadout 轨迹中说明模式原因。

## 验证
- Plan + 已选连接器返回逐项未加载原因。
- Exec 不产生模式跳过项，仍走真实连接器启动路径。
- 后端编译和回归测试通过。

## 处理记录（2026-07-22）
- 改动：新增 `connector_mode_skips`，Plan 模式把全部已选连接器记录为“计划模式不启用外部连接器”；既有 loadout 轨迹会据此展示“连接器未就绪”，Exec 仍调用真实 `open_connectors`。
- 验证：`runtime.py` 与测试文件编译通过；`test_plan_connector_transparency` 2 项通过，覆盖 Plan 逐项原因与 Exec 无模式跳过。
- commit：本提交。
