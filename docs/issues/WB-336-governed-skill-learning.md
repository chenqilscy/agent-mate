---
id: WB-336
title: 从成功任务沉淀 Skill 缺少候选、验证、审核和发布闭环
severity: P1
area: backend
status: open
origin: 既有实现
files:
  - backend/agent/skills.py:261
  - backend/agent/skills_store.py:681
  - server/routers/catalog.py:413
created: 2026-07-31
---

## 问题

当前 `create_local_skill` 可以经对话直接创建本机 Skill，但不能从已验证 Run 提取证据和流程，
也没有“候选草稿 → diff/权限 → Test Run → 审核 → 灰度发布”的受控学习入口。

## 触发场景

- 用户希望把刚完成且已验证的工作沉淀为可复用 Skill，只能重新口述。
- Agent 直接创建 Skill 后即进入本机已安装状态，缺少候选质量和权限复核。
- 一次反馈被误当成应立即修改现有正式 Skill 的依据。

## 影响

P1：程序性经验难以可靠复用；若直接自动学习，又会扩大错误固化和权限漂移风险。

## 建议修法

- 只允许从归属当前用户、已成功且有验证证据的 Run 生成候选草稿。
- 候选保留来源 Run、证据引用、基础 release、内容/权限 diff，不直接覆盖或启用现有 Skill。
- 本地 Skill 需用户确认后安装；平台 Skill 复用现有 Test Run、双人审核、灰度和回滚状态机。

## 验证

- 失败、无权或无证据 Run 不能生成候选。
- 候选创建不会改变当前已安装/已发布 Skill。
- 确认、测试、审核、发布和回滚均有审计记录。
