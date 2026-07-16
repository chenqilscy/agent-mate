---
id: WB-181
title: 技能页假交互清理 —— 推荐段＋号/安装套件/排序/＋添加技能 全是 toast 桩（铁律#1）
severity: P1
area: frontend
status: open
origin: 既有实现
files:
  - src/views/ExpertsView.tsx:45
  - src/views/ExpertsView.tsx:505
  - src/views/ExpertsView.tsx:440
  - src/views/ExpertsView.tsx:745
  - src/views/ExpertsView.tsx:91
  - src/views/ExpertsView.tsx:723
created: 2026-07-16
---

## 问题

技能页（`ExpertsView.tsx`）上多个按钮**只弹 toast，无任何副作用**，UI 对用户撒谎。逐条已核实：

1. **`ExpertsView.tsx:45-60` `AddBtn`** —— 「推荐」段每张卡右上的 ＋ 号。
   `onClick={() => { setOn(v => !v); toast(!on ? '已添加' : '已移除') }}`
   —— 只翻转组件内 `useState`，**不进 loadout、不安装、不落任何地方**，刷新即复原。
   对比：连接器卡的 `ConnAddBtn`（L579）是真的，受控于 `loadoutStore.connectors`。
2. **`ExpertsView.tsx:505` 「安装套件」** —— `onClick={() => toast('安装套件 · ' + name)}`，
   **不装任何技能**（套件本身的虚构问题见 WB-182）。
3. **`ExpertsView.tsx:440` 排序** —— `onClick={() => toast('排序 · 综合评分')}`，不排序。
4. **`ExpertsView.tsx:745` 「＋ 添加技能」** —— `onClick={() => toast('添加技能')}`，右上主按钮无功能。
5. **`ExpertsView.tsx:91-92`** 专家段「最热 / 最新」两个 subtab —— 无 onClick、无状态，纯装饰。
6. **`ExpertsView.tsx:723` `onAct`** —— `skills`/`connectors` 分支只 toast 标签名。

另有**写死的假统计**：`SKILLHUB_GRID`（`catalog.ts:323-362`）39 条卡的 `downloads`/`stars`
全部手写（`'174k', 109` / `'131k', 183` / …），在离线/无 CLI 时**照常渲染给用户看**。
WB-071 已把它降级为第 3 层兜底，但未删除。★/⬇ 也**只是展示数字，无 onClick，不是收藏功能**。

## 触发场景

技能页 → 「推荐」子 tab → 点任意卡的 ＋ → toast「已添加」→ 回首页看 loadout：**什么都没有**。
刷新技能页 → ＋ 号复原。

## 影响

P1，违反铁律#1。这批是本项目反复出现的"占位桩"类问题（同 WB-024/WB-028/WB-137/WB-085），
按既有处理惯例：**要么接真实现，要么诚实占位**，不能假装成功。

## 建议修法

逐条二选一（接真 / 诚实占位），建议：

1. `AddBtn`（推荐段）：接 `loadoutStore.toggle('skill', slug)`，与 SkillHub 段的 `InstallBtn` 语义统一；
   若该段在 WB-184 收敛后消失，则随之删除。
2. 「安装套件」：依赖 WB-182 的结论 —— 真做则接批量安装端点，删则连同 `KitView` 一并移除。
3. 排序：接 `/api/skills/rankings?type=` 已支持的枚举（featured/hot/newest/recommended/trending），
   后端已就绪（`skills.py:47`），前端只是没接；接不了的排序项不显示。
4. 「＋ 添加技能」：接「从本地目录导入 / 打开 SkillHub 搜索」之一，或删除。
5. 专家段「最热/最新」：接排序或删（注：专家段测试按用户要求可跳过，但假按钮仍应清理）。
6. `SKILLHUB_GRID` 静态假统计：WB-071 已提供真实 rankings 兜底，**删除这 39 条**及其写死的
   downloads/stars（与 WB-184 的数据源收敛一并做）。

## 验证

- `npx tsc --noEmit` 过。
- grep `ExpertsView.tsx` 确认无「只 toast 不做事」的 onClick 残留。
- Playwright/CDP 逐个点击：每个按钮要么产生可观测的真实状态变化（loadout / 安装 / 排序结果变化），
  要么明确显示「即将上线」（参考 WB-028 的诚实占位范式）。
- 明暗双主题都看（`.add-btn` 有暗色历史坑，见 WB-008）。
