---
id: WB-216
title: 推荐技能错误按内置免安装处理，与 SkillHub 安装模型不一致
severity: P1
area: fullstack
status: fixed
origin: 产品边界复查
files:
  - src/views/ExpertsView.tsx
  - src/components/skill/SkillDetail.tsx
  - src/stores/skillStore.ts
  - backend/routers/skills.py
  - backend/agent/skills.py
  - backend/agent/skills_store.py
created: 2026-07-20
---

## 问题

“推荐”Tab 将 AgentMate 目录技能视为无需安装的内置能力：卡片右上角显示向右三角，点击后直接挂载；SkillHub 卡片则显示 `+` 并执行真实安装。推荐只是目录位置，不应改变技能的安装生命周期，当前实现让未落盘的技能看起来已经可用，也与 WorkBuddy 的统一安装交互不一致。

## 触发场景

1. 打开“技能 / 推荐”，未安装的推荐技能右上角显示向右三角。
2. 点击后直接进入对话并挂载技能，磁盘技能目录没有对应安装记录。
3. 切到 SkillHub，同类未安装技能却显示 `+` 并先完成真实安装。

## 影响

P1：同一类技能存在两套生命周期，用户无法根据控件判断技能是否已安装；运行时可绕过安装状态读取目录定义，也破坏了“安装后才能查看文件内容”的边界。

## 建议修法

- 推荐与 SkillHub 统一使用真实安装状态：未安装显示 `+`，已安装显示已安装控制。
- 为 AgentMate 推荐目录增加本地安装接口，把目录定义写入本机技能目录，不依赖第三方 SkillHub。
- 目录技能只有本机已安装且启用时才进入 loadout 和运行时解析；卸载后立即不可用。
- 未安装详情只展示目录描述元数据，安装后再展示本地 SKILL.md、打开目录、启停和卸载。

## 验证

- 推荐与 SkillHub 的未安装卡片均显示 `+`，不再出现向右三角。
- 点击推荐卡 `+` 后生成真实本地技能目录、已安装数量增加，刷新后状态保持。
- 安装前详情无源码/文件内容；安装后可查看本地 SKILL.md、打开目录、启停和卸载。
- 卸载后技能无法挂载或由运行时解析。
- 前后端检查、相关回归、明暗主题和窄屏验证通过。

## 处理记录（2026-07-20）

- 推荐与 SkillHub 卡片统一使用安装语义：未安装显示 `+`，已安装显示 `✓/⋯`，推荐卡不再提供三角形“直接使用”入口。
- 新增 AgentMate 目录技能本地安装接口，把目录定义以 `source=agentmate` 的真实 `SKILL.md` 快照写入本机技能目录；安装、扫描、详情、启停、打开目录和卸载复用同一套磁盘生命周期。
- 未安装目录详情只返回名称、描述、来源和分类，不返回指令、工具或源码；安装后才读取本地文件并开放完整详情。
- loadout 清单与运行时解析均增加真实安装/启用门禁；未安装或停用的目录技能不再能绕过磁盘状态生效。
- 补充目录技能安装前、安装后、停用和卸载的离线回归覆盖。

### 验证结果

- `python -m unittest backend.tests.regression.test_skill_catalog_contract backend.tests.regression.test_skill_market_boundary backend.tests.regression.test_skill_import`：11/11 通过。
- `npx tsc --noEmit`、`npx vite build`、变更 Python 文件 `py_compile` 与 `git diff --check` 通过；构建仅保留既有的大 chunk 提示。
- 硬重启 App backend `:8101` 后，真 API 安装前返回 `installed=false`、空源码/工具；推荐技能安装后已安装数量从 0 变 1并生成真实本地目录，卸载后恢复 0 且运行时解析返回 `None`。
- 真浏览器验证：推荐 6 张未安装卡全部显示安装按钮、三角使用按钮为 0；安装后首卡显示 `✓/⋯` 并可查看本地源码、启停和卸载；明暗主题及 800px 窄屏均无横向溢出。验证后已恢复深色主题并卸载测试技能。
