---
id: WB-334
title: Skill 缺少可发现的渐进加载，项目技能正文常驻系统提示
severity: P1
area: backend
status: in-progress
origin: 既有实现
files:
  - backend/agent/runtime.py:457
  - backend/agent/skills.py:530
  - backend/agent/skill_resources.py:21
created: 2026-07-31
---

## 问题

Runtime 只有 loadout 中已显式挂载的 Skill，并在 Run 开始时把其 `SKILL.md` 正文整体注入系统提示；
未挂载但已安装的 Skill 对 Agent 不可发现。附件已经支持按需读取，但正文仍缺少
“精简索引 → 加载正文 → 加载具体资源”的渐进披露闭环。

## 触发场景

- 项目长期配置多个 Skill，每次对话即使任务无关也消耗正文 token，并增加指令冲突概率。
- 用户用自然语言提出已安装 Skill 能处理的任务但未手工挂载，Agent 不知道该 Skill 存在。
- Agent 运行中发现需要某个 Skill 时，无法按固定 release 加载正文及随附工具。

## 影响

P1：Skill 数量增长后系统提示持续膨胀，项目默认能力难以扩展；能力发现依赖用户手工选择，
也无法形成可审计的按需激活。

## 建议修法

- 增加只读的 Skill 精简索引与 `skill_view` 工具，只暴露当前 owner 已安装、启用且完整性有效的定义。
- 项目 Skill 作为候选池写入精简索引；会话显式选择仍立即加载，保持用户明确意图。
- `skill_view` 加载时固定 release snapshot，下一轮才暴露该 Skill 声明的工具与资源。
- loadout、Run 权限快照和运行指标必须记录实际加载的 release，不把候选误报为已启用。

## 验证

- 项目候选 Skill 正文不常驻 system prompt，但名称/描述可发现并能通过 `skill_view` 加载。
- 会话显式选择仍立即生效；未安装、停用、撤回、hash 损坏或工具契约不兼容的 Skill 无法加载。
- 加载后下一轮能调用该 Skill 工具并读取其 release 资源；Run 快照记录实际 release。
- 多 Skill 预算、ask/plan 门禁、现有 loadout SSE 与旧回归保持通过。
