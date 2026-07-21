---
id: WB-239
title: AgentMate 功能主线尚未围绕可验收任务交付闭环组织
severity: P1
area: fullstack
status: fixed
origin: 既有实现
files:
  - docs/agentmate-功能规划-v2.md:1
  - src/views/HomeView.tsx:20
  - backend/storage/models.py:41
created: 2026-07-21
---

## 问题

AgentMate 已经具备真实 agent 工具循环、项目、自动化、助理、能力目录、Server 和 Console，
但产品入口与数据语义仍按历史模块平铺：会话常被称为任务，项目中另有 WorkItem，执行产物又只从
消息 diff 临时派生。用户难以从一个统一入口判断哪些工作正在执行、哪些失败、哪些已经产生可验收结果，
成功执行也没有稳定地转为自动化或组织能力。

## 触发场景

用户启动 AgentMate 后，需要分别进入侧栏任务、项目、自动化和文件页面才能判断当前工作状态；
从项目工作项发起执行、查看 Run、验收 Artifact、回写完成和固化复用还不是一条统一产品链路。

## 影响

P1：继续按页面增加功能会放大概念重复和入口分散，真实工具与 Server 能力也难以转化为可衡量的
任务完成率、产物质量、恢复成功率和能力发布可靠性。

## 建议修法

- 以 `WorkItem → Run → Artifact → 验收 → Automation/Skill` 为功能主线；
- 明确 Session 只负责协商上下文，Run 表示一次执行，Artifact 表示可验收交付物；
- 按 R0 收口、R1 可交付、R2 可托管、R3 可协作、R4 可运营、R5 可编排分阶段实施；
- 每个阶段拆独立子 issue，以真实数据、权限、trace、产物和真机验收作为完成条件。

## 验证

- `docs/agentmate-功能规划-v2.md` 成为路线图基线，明确对象、边界、阶段和退出条件；
- 子 issue 在台账中可追溯到本 epic，且不把待建能力描述为已经实现；
- R0 完成后 App/文档对 Session、Run、WorkItem、Artifact 的口径一致，完整生产构建和回归保持绿色。

## 启动记录（2026-07-21）

- 规划：新增 `docs/agentmate-功能规划-v2.md`，确定任务交付主线、三个产品面、R0–R5 路线和黄金任务。
- 首个切片：先修复 R0 生产构建门禁 WB-237，再以 WB-240 落首页任务控制台。

## 路线图进展（2026-07-21）

- R0、R1、R2、R3、R5 的子 issue 已实现并验证：任务控制台、Run/Artifact、办公与浏览器工具、可靠自动化、WorkItem 协作链、多专家 DAG 与真实对照评测均已落地。
- R4 的能力发布与桌面更新代码链已实现；WB-257 已用一次性真实 updater 密钥和前后两个 release 安装包完成签名失败拒绝、正确签名升级与显式回滚演练。
- 本 epic 保持 `in-progress`，不随 WB-257 提前关闭：仍需做全路线图统一验收，并由部署方提供生产 HTTPS 域名、正式 CI updater 私钥、可信 Windows 代码签名证书和生产前后版本完成上线演练。

## 集成验收记录（2026-07-22）

- 已将独立实现统一集成：WB-023、WB-053、WB-193 已关闭；WB-112 的 Console 任务模板切片与 WB-160 的
  邮件连接器代码已进入目标树。WB-112 仍需自定义字段、依赖关系、Sprint 与导出等后续范围，WB-160 仍需真实
  IMAP/SMTP 账号联调，因此两条继续保持 `in-progress`，不以代码合入冒充完整交付。
- 统一回归通过：Backend 128/128、Server 41/41、WB-112 HTTP 集成 1/1、App 与 Console 生产构建、Tauri
  `cargo check`。WB-193 另以无 workaround 真实 LLM 会话完成 URL 入库、状态轮询和同文档检索闭环。
- 当时本 epic 继续保持 `in-progress`：除 WB-112/WB-160 的明确剩余项外，生产更新链仍需要部署方提供正式域名、
  CI updater 私钥、可信 Windows 代码签名证书和生产前后版本上线演练。

## 关闭记录（2026-07-22）

- WB-112 已补齐自定义字段、依赖关系、Sprint/燃尽、CSV 导出和 App 镜像契约，并通过 Server 45/45、Backend 131/131、真实 Server↔Backend HTTP 集成及 App/Console 生产构建。
- WB-160 已使用本机真实邮件渠道完成 IMAP/SMTP 自发自收，验证 PEEK 不提前 Seen、稳定身份、回环防护和精确 UID Seen；9 项持久投递协议回归继续覆盖崩溃/重启与至多一次回复分支。
- WB-191 已按当前 App 直连 SkillHub 架构落地 Manager 下架策略；WB-240～258 等路线图子项均在台账中有独立实现、验证与关闭记录。
- R0～R5 的产品与代码退出条件均已满足。正式 HTTPS 域名、受保护 CI updater 私钥、可信 Windows 代码签名证书及生产前后版本上线演练是部署方外部输入，不再把已完成的产品 epic 长期标为 `in-progress`；该上线门槛由 WB-283 独立追踪。
- 状态：`fixed`/✅。
