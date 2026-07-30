---
id: WB-338
title: Skill 缺少命名组合与平台环境适用性门禁
severity: P2
area: backend
status: open
origin: 既有实现
files:
  - src/stores/loadoutStore.ts:24
  - backend/agent/skills_store.py:298
  - backend/agent/runtime.py:379
created: 2026-07-31
---

## 问题

项目和会话可以组合多个 Skill，但组合不能命名、跨项目复用；Skill frontmatter 也不表达平台、
项目环境和所需工具契约，导致不适用 Skill 仍进入候选或依赖运行时失败才暴露。

## 触发场景

- 用户每次手工组合相同的一组研发、发布或事故响应 Skill。
- Windows 环境展示只适用于 Linux/macOS 的 Skill。
- Skill 所需工具或项目类型不满足时仍被推荐。

## 影响

P2：重复配置增加操作成本，不适用能力增加发现噪音和失败率。

## 建议修法

- 增加用户级命名 Skill bundle，解析时保留稳定顺序并如实报告缺失项。
- 支持 `platforms`、`environments`、`requires_tools` 等声明，候选索引和加载都执行门禁。
- 项目 loadout 保持权威，不让 bundle 覆盖更高优先级安全和权限规则。

## 验证

- bundle 可创建、调用、编辑、删除并跨项目复用；缺失 Skill 被跳过且可见。
- 不适用 Skill 不进入自动候选，显式调用时返回明确原因。
- Windows/Linux 和工具契约边界有回归测试。
