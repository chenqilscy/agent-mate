---
id: WB-344
title: V1.0 受控真实用户试用缺少参与者、安装版本与连续证据
severity: P1
area: misc
status: deferred
origin: V1 RC 下一阶段
files:
  - docs/agentmate-v1-release-candidate.md:55
created: 2026-08-01
---

## 问题

V1 工程、真实 LLM 功能和桌面源码预检已通过，但尚未由目标用户在非开发环境连续使用。当前没有已确认的
3–5 名参与者、5 个工作日窗口、固定安装版本/哈希、反馈负责人和最终 Go/No-Go 记录。

## 触发场景

准备把当前候选版称为“可进入受控发布”时，仓库证据只能证明自动化检查与本机真实功能，不能证明目标用户
能独立完成成果交付、工作项验收和定时自动化三条路径。

## 影响

P1。缺少真实使用证据时继续扩功能或直接发布，都会跳过产品可用性、恢复能力与价值验证。

## 前置条件

- 确认 3–5 名目标用户、试用负责人和连续 5 个工作日时间窗；
- 固定一个可识别的 beta 安装版本、哈希和回滚方式；桌面生产材料边界见 [WB-283](WB-283-production-desktop-update-deployment-acceptance.md)；
- 明确只收集聚合指标和用户主动提交的问题，不收集密钥、工作文件或会话正文；
- 使用 [V1 RC 试用方案](../agentmate-v1-release-candidate.md#4-小范围真实试用包) 的任务卡和阈值。

## 验证

- 每名参与者完成或明确阻断三条黄金路径，并记录首次有效成果耗时、人工救援次数和继续使用意愿；
- 汇总完成率、定时触发成功率、阻断问题和安全/数据事故，保存版本对应证据；
- 达到文档阈值后记录 Go；未达到则逐项登记 issue、修复并只重跑受影响路径；
- 在证据完成前保持 deferred，不以内部演示或自动测试代替真实用户试用。

## 推进记录（2026-08-04）

- 已完成试用前工程基线：正式 `scripts/validate-v1-rc.ps1 -IsolatedLive -DesktopPreflight` 同一次运行通过
  12 个选定门禁；Backend 336、Server 117、隔离 HTTP 集成 4、真实 LLM A–F 共 101 条断言、263 个跟踪
  Python 源编译和 Tauri Rust 预检全部通过。
- 已修复试用门禁暴露的 WB-415：Chat body 限流中间件不再截断 SSE 客户端生命周期，`ask_user` 挂起/恢复
  的真实链路稳定通过 17/17。
- 已在提交 `b76d652ac36dcc812646d43ae3dfe8edf179e496` 上重新冻结 sidecar 并生成当前候选包：NSIS
  `AgentMate_1.0.0_x64-setup.exe` 为 163433389 bytes，SHA-256
  `64CE62BE7D1832DB6F63BB70D0315E4BBA03D00E33420871F2F2953F7CBC9371`；MSI 为 175542272 bytes，
  SHA-256 `7507783E10C059C87ED686B7154FB052D5311281893BFFF59CAD73E3D0D60AE8`。发布目录结构校验通过，
  主程序、当前 sidecar 与 WebView2 Loader 均存在且为 x86_64。
- `pnpm tauri build` 在 MSI/NSIS 生成后因缺少 `TAURI_SIGNING_PRIVATE_KEY` 以退出码 1 终止；这是
  [WB-283](WB-283-production-desktop-update-deployment-acceptance.md) 的既有签名边界。上述文件只能视为
  未签名受控 beta 候选，尚未完成干净机器安装、真启动和回滚验收，不能描述为正式发布包。
- 真实试用尚未启动：仍缺 3–5 名已确认参与者、试用负责人和连续 5 个工作日窗口；开始前还需由试用负责人
  确认是否接受未签名包的系统警告，或提供受保护签名流水线产物。状态保持 `deferred`，不以构建和自动门禁
  代替真实用户逐日证据。
