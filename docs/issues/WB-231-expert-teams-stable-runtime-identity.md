---
id: WB-231
title: 专家团成员没有稳定专家身份，Console 团队目录无法驱动 App 真实人格执行
severity: P1
area: fullstack
status: fixed
origin: 既有实现
files:
  - src/data/catalog.ts:52
  - src/views/ExpertsView.tsx:151
  - backend/agent/runtime.py:323
  - server/catalog_seed.py:32
created: 2026-07-21
---

## 问题

专家团成员目前只有展示用的 `name`/`role`，没有引用 `EXPERT_DEFS.slug`。App 召唤团队时把成员昵称直接写入
`loadout.experts`，而后端运行时只能按专家定义名解析 persona。当前三个团队共 17 个成员，0 个昵称能命中
真实人格定义；Server 也没有播种 `EXP_TEAMS`，App 实际显示的是本地橱窗兜底。

## 触发场景

App → 专家 → 专家团 → 召唤任一团队 → loadout 显示全部成员，但运行时无法把成员映射到 Server/本地专家定义，
只能落入 WB-196 的通用兜底话术。Console 新增或编辑团队也无法保证成员对应可执行人格。

## 影响

P1：专家团最核心的“多人格协作”只是批量展示姓名，没有稳定身份和真实 persona，违反不模拟铁律；同时
Console、Server、App 三端的团队定义没有形成权威下发闭环。

## 建议修法

1. 团队成员增加稳定 `expert_slug`，Server 校验每个引用都指向启用的 `EXPERT_DEFS`。
2. Server 播种默认 `EXP_TEAMS`，并随目录 pull 下发；App 离线保留等价本地兜底。
3. App 召唤团队时写入专家 slug；运行时按 slug 或名称解析 persona，并在 UI/SSE 边界还原展示名。
4. 未解析成员按 WB-196 诚实报告为未就绪，不注入通用假人格。

## 验证

- 默认三个团队的全部成员都有合法 `expert_slug`，且能命中 persona；
- Console 拒绝不存在的专家引用，保存后 App pull 可见并可召唤；
- 团队召唤的 system prompt 只含真实 persona，SSE loadout 显示人类可读专家名；
- Server 不可达时默认团队仍可离线使用。

## 处理记录（2026-07-21）

- 13 个内置专家补齐稳定 slug；3 个默认专家团的 17 名成员全部增加 `expert_slug`，App 离线种子、
  Server 种子与展示目录保持一致，并为既有本地团队执行幂等身份迁移。
- App 召唤专家团改传 slug，运行时按 slug/名称解析真实 persona，Composer/SSE 只在展示边界还原人类可读名称。
- Server 默认播种 3 个专家团；CRUD 校验成员引用必须存在且启用、团队内不得重复，并阻止停用/删除被团队引用的专家。
- 自动化测试 16/16（App backend）与 19/19（Server）通过；实时 SSE 验收软件开发团队 6/6 人格加载；
  App 与隔离 Console 真机确认目录、详情和“角色,显示名,专家 slug”编辑格式。
