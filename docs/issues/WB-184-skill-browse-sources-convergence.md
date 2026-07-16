---
id: WB-184
title: 技能浏览面板四套数据源 + 两套分类体系并存 —— 收敛为一个面板一套分类
severity: P2
area: frontend
status: open
origin: 既有实现
files:
  - src/views/ExpertsView.tsx:337
  - src/views/ExpertsView.tsx:427
  - src/views/ExpertsView.tsx:473
  - src/views/ExpertsView.tsx:463
  - src/stores/catalogStore.ts:100
  - src/stores/catalogStore.ts:125
  - src/data/catalog.ts:101
created: 2026-07-16
---

## 问题

一个技能面板里摞了**四套来源不同、质量不等的数据**，外加**两套互不相干的分类体系**：

| 段 | 组件 | 数据源 | 兜底层数 |
|---|---|---|---|
| 精选技能 | `FeaturedSkills` L337 | Hub `SKILLHUB_FEATURED` 下发 → 静态 `SKILLHUB_FEATURED` | 2 |
| 推荐 | `RecoView` L473 | `/api/catalog` → `catalog_showcase` 表（内容仍是静态 `SK_GRID`） | 1 |
| SkillHub | `SkillHubView` L427 | Hub 镜像 → `/skills/rankings`（真实）→ 静态 `SKILLHUB_GRID` | **3** |
| 套件 | `KitView` L495 | 纯静态（见 WB-182） | 0 |

**概念重叠且质量倒挂**：「推荐」和「SkillHub」都是"可浏览的技能列表"，但推荐段的卡
（`.scard`）**没有安装按钮、没有详情入口、没有已装态**，＋ 号还是假的（WB-181）；
SkillHub 段的卡（`.hcard`）才是全功能的。用户看到两段外观相似、能力天差地别的列表。

**两套分类**：推荐段用 `SK_CATS`（14 项），SkillHub 段用 `SKILLHUB_CATS`（13 项）——
**完全不同的分类体系上下并排**在同一面板。且静态兜底态下 `SKILLHUB_GRID` 实际只覆盖 7 个分类，
点「教育学习」「行业专业」**必然空白**（L467「该分类下暂无技能」）。

**兜底链竞态**（`catalogStore.ts:125-129`）：启动串行跑 `load()` → `syncFromHub()` → `fallbackToRankings()`。
`fallbackToRankings` 用 `skillMirror.length > 0` 跳过（L100），但 `syncFromHub` 仅在 `r.catalog > 0`
时重载（L92）—— **若 Hub 已连但本次 pull 无新目录，`skillMirror` 保持空，会被 rankings 覆盖**。
用户看到的"SkillHub"内容取决于启动时序。

**死代码**：`SK_RECO`（`catalog.ts:101-106`）前端**零消费**（仅存在于 `catalogStore` 的类型与 FALLBACK 中）。

## 触发场景

- 技能页 → 「推荐」段点某卡 → 无反应（无详情弹窗）；同一技能在「SkillHub」段点 → 有详情、能装。
- 静态兜底态（未连 Hub 且无 CLI）→ SkillHub 段点分类「教育学习」→ 永远空白。
- 连了 Hub 但某次 pull 无新目录 → 刷新几次，「SkillHub」段内容在镜像与 rankings 之间跳变。

## 影响

P2。不阻塞功能，但这是"橱窗"侧复杂度失控的集中体现：四套源三层兜底，
维护者与用户都无法预期某一刻看到的是什么。也是 WB-181 假交互与 WB-179 假技能的温床。

## 建议修法

1. **合并「推荐」与「SkillHub」为一个浏览面板**，统一用全功能富卡片（`.hcard`，带安装/详情/已装态）；
   「推荐」若要保留语义，降为该面板的一个**排序/筛选档**（接 `rankings?type=recommended`，后端已支持）。
2. **一套分类**：以 Hub 下发的 `skill-category`（SkillHub 12 场景）为准；
   删掉 `SK_CATS`；分类 chip 按 `count > 0` 动态生成（L446 已有此逻辑，推广到兜底态）。
3. **兜底链去竞态**：改为「镜像为空 → 才跑 rankings」的单一判定，且在 `syncFromHub` 完成后
   （而非按 `r.catalog > 0`）重新求值；或干脆串成一个 `resolveSkillCatalog()`。
4. **删静态假数据**：`SKILLHUB_GRID` 39 条（含写死 downloads/stars）、`SK_RECO`（死代码）、
   `SK_CATS`；与 WB-183 的孤儿清理一并做。
5. 沿用既有 class 与 token（`.hcard` / `.cathead` / `.sk-sort` …），不新增样式（铁律#2）。

## 验证

- `npx tsc --noEmit` 过。
- 三态实测（连 Hub / 未连 Hub 有 CLI / 全离线）：每态下面板内容来源可预期，**无静态假数据出现**；
  分类 chip 点任意一个都有内容或诚实空态。
- 反复刷新 10 次（连 Hub 态），SkillHub 段内容稳定，不在镜像/rankings 间跳变。
- 明暗双主题都看。
