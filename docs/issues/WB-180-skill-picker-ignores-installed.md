---
id: WB-180
title: ＋菜单技能选择器只读静态 SK_GRID —— 真实已安装的技能在会话里选不到
severity: P1
area: frontend
status: open
origin: 既有实现
files:
  - src/components/project/NewProjectModal.tsx:215
  - src/stores/skillStore.ts:40
  - src/stores/loadoutStore.ts:53
  - src/views/ProjectHomeView.tsx:26
created: 2026-07-16
---

## 问题

Composer ＋ 菜单的技能选择器 `PickerOverlay`（[NewProjectModal.tsx:215-229](../../src/components/project/NewProjectModal.tsx)）
`kind === 'skill'` 分支**只渲染静态 `SK_GRID`**（17 张商品卡），
**完全不读 `skillStore.installed`**：

```tsx
{kind === 'skill' && (
  <div className="selgrid">
    {SK_GRID.filter((s) => match(s[1]) || match(s[2])).map((s) => { ... onToggle(s[1]) ... })}
  </div>
)}
```

全仓库 grep `useSkillStore` 只有两处 import：`ExpertsView.tsx` 与 `SkillDetail.tsx`。
**loadout 路径上一处都没有。**

后果是**装机流程与使用流程是断开的两条路**：

- 用户在技能页真安装的技能 → ＋ 菜单里**不存在**，无法加入会话。
- `SK_GRID` 里的卡即使**没装**也能"选中"并显示已挂载 → 落到 WB-179 的兜底话术。

`ProjectHomeView.tsx:26` 同样用 `SK_GRID` 反查图标，真实已装技能拿不到图标。

## 触发场景

1. 技能页 → SkillHub → 安装任意技能（如 `鹅厂辟谣助手`），安装成功、「我安装的」计数 +1。
2. 回首页 → 点 ＋ → 技能 → **列表里没有它**，搜索也搜不到（`match` 只过滤 `SK_GRID`）。
3. 该技能只能在项目 loadout（经 Manager 门户 WB-080）里配，或**根本用不上**。

## 影响

P1。技能的**安装功能与使用功能事实上不连通** —— 用户装完技能后无路可走，
这让整条 SkillHub 安装链路（WB-054/055/056/057）在会话侧失去意义。

## 建议修法

1. `PickerOverlay` 的 `skill` 分支改读 `useSkillStore().installed`（真相源，后端磁盘扫描），
   与技能页「我安装的」同源；`onToggle` 传 **slug**（配合 WB-179）。
2. **未安装的目录卡也可展示**，但点击走「安装 → 启用 → 加入」而非直接选中
   （把两条路合成一条）；或明确分区「已安装 / 可安装」。
3. 首次打开 picker 时触发 `skillStore.load()`（若尚未加载）。
4. `ProjectHomeView.tsx:26` 的图标反查改走已装清单 + 目录兜底。
5. 复用既有 `.selgrid` / `.selcard` / `.sc-ic` / `.sc-n` / `.sc-d` class，不引新样式（铁律#2）。

## 验证

- `npx tsc --noEmit` 过。
- Playwright/CDP 实测：安装一个技能 → ＋ 菜单能看到并选中 → chip 显示 → 发消息 → 后端
  system prompt 里出现其真实 SKILL.md；卸载后该项从 ＋ 菜单消失。
- 明暗双主题下 picker 卡片样式正常（`.selcard.sel` 选中态）。
