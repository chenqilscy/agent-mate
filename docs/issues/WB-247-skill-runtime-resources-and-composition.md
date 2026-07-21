---
id: WB-247
title: Skill references 与模板运行时不可达且多 Skill 指令缺少总预算和冲突规则
severity: P1
area: backend
status: open
origin: 既有实现
files:
  - backend/agent/skills_store.py:917
  - backend/agent/skills.py:426
  - backend/agent/runtime.py:385
created: 2026-07-21
---

## 问题

Console 和安装器允许 Skill 携带 `references/`、`templates/` 等文本附件，但 runtime 只注入截断后的
`SKILL.md` 正文；工作区文件工具又不能越过项目沙箱读取全局 Skill 目录，因此附件在真实执行中不可按需
访问。多个 Skill 各自最多注入 6000 字符，但没有会话总预算、优先级和指令冲突检测。

## 触发场景

- Skill 指令要求先读取 `references/guide.md`，Agent 既没有文件内容，也没有合法工具读取安装目录。
- 同时挂载多个长 Skill，系统提示词快速膨胀；两个 Skill 对同一行为给出冲突要求时没有可见告警。

## 影响

P1：随包资料与模板成为“可上传但不可执行”的半成品能力；多 Skill 场景增加 token 成本与行为漂移。

## 建议修法

- 增加受 manifest 与路径白名单约束的只读 Skill 资源工具：列出、读取，以及把模板显式复制到工作区。
- references 按需读取，不把全部文件直接注入系统提示；scripts 默认不可执行。
- 引入 Skill 指令总预算、稳定排序、截断可观察信息和基础冲突提示。

## 验证

- Agent 能读取已启用 Skill 的声明资源，不能路径穿越或读取其他 Skill/密钥文件。
- 模板只在显式调用后复制进当前项目工作区并产生真实 trace。
- 多 Skill 超过预算时按稳定规则截断并在 loadout trace 中显示，不静默丢失。
