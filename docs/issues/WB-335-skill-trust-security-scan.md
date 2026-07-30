---
id: WB-335
title: 第三方 Skill 缺少本地内容安全扫描与来源信任分级
severity: P1
area: backend
status: open
origin: 既有实现
files:
  - backend/agent/skills_store.py:640
  - backend/agent/skills_store.py:1160
  - backend/routers/skills.py:207
created: 2026-07-31
---

## 问题

Skill 导入和 SkillHub 安装已校验路径、大小、slug、完整性与平台 blocklist，但仓库内没有对
`SKILL.md`、references、templates、scripts 做内容风险分类，也没有区分 AgentMate、可信源、
社区源和本地来源的信任策略。

## 触发场景

- 社区 Skill 的正文包含提示注入、数据外传或诱导调用高权限基础工具的指令。
- scripts 附件包含混淆下载执行、破坏性命令或凭据收集内容。
- 来源信任等级降低或更新新增风险时，已安装副本仍可直接启用。

## 影响

P1：文件系统完整性不能证明内容安全；恶意指令可借已有工具权限影响工作区、网络或主机。

## 建议修法

- 建立 `agentmate/trusted/community/local` 信任分级及持久 provenance。
- 安装前对所有文本内容做确定性风险扫描，覆盖提示注入、外传、破坏性命令、混淆和供应链信号。
- dangerous 结果不可绕过；warning 必须显式确认并记录，更新后新增风险要重新确认。
- scripts 继续默认不可执行，扫描报告与权限 diff 在 Skill 详情中可见。

## 验证

- 安全样例可安装；warning 未确认不能启用；dangerous 永远阻断。
- ZIP/目录/SkillHub/目录发布四条路径都执行同一扫描策略。
- 扫描报告、来源、内容 hash 与确认记录持久化且不包含密钥。
