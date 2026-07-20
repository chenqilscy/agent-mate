---
id: WB-207
title: 已安装技能的编辑入口挂载不存在的旧技能且不能保存修改
severity: P2
area: fullstack
status: fixed
origin: 既有实现
files:
  - src/views/ExpertsView.tsx:251
  - backend/agent/skills_store.py:383
created: 2026-07-20
---

## 问题

已安装技能卡片的“编辑”调用 `editSkill()`，挂载不存在的 `skill-creator` 并预填提示。运行时会把该身份判为未就绪；即使改成新的 `skill-creator-guide`，WB-206 的创建工具也会拒绝已存在 slug，当前仍没有安全读取并更新指定技能的闭环。

## 触发场景

进入“技能 → 我安装的”，打开任意技能菜单并点击“编辑”：页面进入 composer，但无法把修改可靠写回原技能目录。

## 影响

P2：管理菜单展示了无法完成的编辑能力，违反“不模拟、不假成功”；不影响 WB-206 的查找、导入和新建技能。

## 建议修法

- 新增仅针对已存在技能 key 的读取/更新工具，要求显式确认后原子替换 `SKILL.md`，保留 references/scripts 与元数据。
- 编辑入口传稳定 slug/key，挂载真实 `skill-creator-guide`，并把现有名称、描述与指令注入上下文。
- 增加并发/重复身份、停用态与编辑失败不破坏原文件的回归测试。

## 验证

- 编辑一个真实已安装技能后，详情、列表和运行时注入均读取新内容；失败时原文件不变。
- 不存在/内置技能不可误编辑，明暗主题与错误提示清晰。

## 处理记录（2026-07-21）

- 改动：删除旧 `skill-creator` 假跳转；“我安装的”对本地/SkillHub 技能打开真实编辑弹窗，后端 `PATCH /api/skills/{key}` 原子更新 SKILL.md，保留 references/scripts 与其他文件；AgentMate 目录技能明确拒绝本地改写，改走版本升级。
- 验证：浏览器创建并编辑临时本地技能，名称、简介与正文真实写回，弹窗关闭后列表即时更新；自动化验证其他文件保持不变、AgentMate 目录技能不可误编辑，明暗主题通过。
- commit：本次 WB-207/WB-224～229 合并提交。
