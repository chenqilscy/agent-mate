---
id: WB-272
title: Plan 与 Ask 可叠加并产生冲突系统提示
severity: P3
area: fullstack
status: fixed
origin: 🏚 迁移遗留
files:
  - src/stores/settingsStore.ts:64
  - backend/agent/runtime.py:258
created: 2026-07-22
---

## 问题
前端允许同时打开 Plan 与 Ask。后端虽然工具集最终为空且运行状态记为 Ask，却先选用 Plan 系统提示，再追加“不要调用任何工具”，形成自相矛盾的契约。

## 触发场景
依次开启 Plan 和 Ask 后发送消息，载荷同时包含 `plan=true`、`ask=true`。

## 影响
P3。不会越权执行工具，但模型行为和界面模式语义不稳定。

## 建议修法
前端把 Plan/Ask 设为互斥；后端对旧客户端或直接请求做权威归一，冲突时 Ask 优先。

## 验证
- 前端开启 Plan 后 Ask 为 false，开启 Ask 后 Plan 为 false。
- 后端 `plan=true, ask=true` 归一为 `(false, true)`。
- 对应回归测试和 `npx tsc --noEmit` 通过。

## 处理记录（2026-07-22）
- 改动：前端 `setPlan`/`setAsk` 开启时关闭另一模式；后端 `normalize_modes` 在进入遥测、提示词、工具集和持久化前统一归一，冲突时 Ask 优先。
- 验证：后端编译通过；`test_runtime_mode_contract` 4 组模式组合通过；`npx tsc --noEmit` 通过；真实 Chromium/Vite 页面切换得到 Plan=`[true,false]`、Ask=`[false,true]`。
- commit：本提交。
