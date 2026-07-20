---
id: WB-195
title: 「推荐」段分类 chip 点了不过滤 —— SK_GRID 数据形状里根本没有分类字段
severity: P3
area: frontend
status: fixed
origin: 🏚 迁移遗留
files:
  - src/views/ExpertsView.tsx:481
  - src/data/catalog.ts:110
  - docs/workbuddy-v2.html:1363
created: 2026-07-17
---

## 问题

技能页「推荐」段（`RecoView`）的分类 chips 是**装饰**：

```tsx
const [cat, setCat] = useState('全部')
...
{SK_CATS.map((c) => <div className={`cat ${cat === c ? 'active' : ''}`} onClick={() => setCat(c)}>{c}</div>)}
...
{SK_GRID.map(([ic, n, d]) => ( ... ))}      // ← 从头到尾没用 cat 过滤
```

点分类只把 chip 高亮，列表**纹丝不动**。

根因不是忘了写过滤，而是**数据形状里没有分类**：`SK_GRID` 是 `[icon, name, desc]` 三元组
（`catalog.ts:110`），每条卡没有 category 字段 —— 以当前数据**过滤无从实现**。
原型 `docs/workbuddy-v2.html:1363` 同样是无过滤的 `SK_GRID.map(...)`，属迁移遗留的装饰。

对比：同页「SkillHub」段的分类 chip **是真的**（`SkillHubView` 按 `card.category`/`skillCats` 过滤）
—— 因为镜像卡带 category。所以同一个面板上下两段，分类 chip 一真一假，外观完全一样。

## 触发场景

技能页 → 推荐 → 点「办公效率」→ chip 高亮，下面 16 张卡一张没变。

## 影响

P3。不误导用户做错事，但它是个不兑现的交互（铁律#1 的边缘）；且与同页 SkillHub 段的
真分类 chip 外观一致、行为不同，更易让人以为是 bug。

## 建议修法

**依赖 WB-183（技能目录入库）**：`catalog_skills` 表带 `category` 字段后，`SK_GRID` 类目录卡
才有分类可过滤，这时把 `RecoView` 的过滤补上即可（一行 `.filter()`）。

在那之前不要单独修 —— 没有数据源，任何「过滤」都只能靠前端硬编码一张
`名字 → 分类` 映射表，那是又一处硬编码假数据（铁律#1）。

若 **WB-184**（四套数据源 + 两套分类收敛）先落地并把「推荐」段合并进统一浏览面板，
本条随之消失（届时只有一套带真 category 的卡 + 一套分类）。

## 验证

- 点任一分类 → 列表**真的**只剩该分类的卡；点「全部」→ 恢复；
- 该分类下无卡时给诚实空态（同 SkillHub 段的「该分类下暂无技能」）；
- 分类值来自 DB/目录，不是前端硬编码的映射表。

## 处理记录（2026-07-20）

推荐卡改由 `/api/catalog` 中基于 `catalog_skills` 生成的对象供给，卡片自带真实 `slug/category`；
分类 chips 从这些定义动态生成并参与 `.filter()`。浏览器实测点「开发编程」后 6 张缩为
`Web Access（浏览器自动化）`、`技能创建指南` 两张；「全部」可恢复，空分类有诚实空态。
浅色、深色与 860px 窄屏均无横向溢出。状态改为 `fixed`。
