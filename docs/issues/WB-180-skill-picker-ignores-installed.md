---
id: WB-180
title: ＋菜单技能选择器只读静态 SK_GRID —— 真实已安装的技能在会话里选不到
severity: P1
area: frontend
status: fixed
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

## 处理记录（2026-07-16）

### 差点漏掉的回归：picker 里还藏着 6 个**真**内置技能

原计划「把 `SK_GRID` 换成 `skillStore.installed`」**会砍掉真能力**：`SK_GRID` 的 17 张卡里，
除了 11 张后端零能力的假卡（WB-179），还含 **6 个真·内置技能**（Web Access / MarkItDown /
Excel 文件处理 / 技能创建指南 / Word 文档生成 / 股票综合分析器）——它们定义在
`agent/skills.py` 的 `SKILLS` dict、带真工具，**不在磁盘上**，所以 `GET /api/skills` 的
磁盘扫描列不出它们。直接换成「只列已装」会让这 6 个真能力从 UI 上消失。

故补了它们的真实来源：

- `backend/agent/skills.py` 加 `builtin_list()`（name / description / tools）；
- `backend/routers/skills.py` 加 `GET /api/skills/builtin`
  —— **必须定义在 `/skills/{key}` 之前**，否则被它当 `key="builtin"` 吃掉（已在代码注释里钉住）。

### 前端

- `src/stores/skillStore.ts` 加 `builtin: BuiltinSkill[]`，`load()` 里另取一次
  （失败不阻塞已装清单）。
- `src/components/project/NewProjectModal.tsx` 的 `PickerOverlay` skill 分支改为
  **内置 + 已安装且未停用**，照 `kb` 分支的动态项范式（空态引导去「技能」页安装）。
  - **停用的不列**：后端 `instructions_for` 对 `disabled` 返回 `None`，列出来等于骗用户（铁律#1）。
  - 复用既有 class（`.selgrid`/`.selcard`/`.sc-ic`/`.sc-n`/`.sc-d`/`.conn-tag`），零新样式。

### 绕开并发争用

`src/lib/api.ts` 与 `src/lib/types.ts` 正被并发会话（WB-177/188 WeKnora）占用，故 builtin
走 `skillStore` 内的裸 `fetch`（该文件已有先例——`install` 就是裸 fetch），`BuiltinSkill`
类型就近定义在 `skillStore.ts`。**待 WB-183 技能目录入库时，应把它收回 `api.ts`/`types.ts` 的常规分层。**

### 实测抓到的视觉 bug（已修）

首轮 CDP 截图发现 `.conn-tag` 被挤成**竖排**（一字一行），卡片布局塌了。原因：
`.conn-tag` 的 CSS 是 `margin-left: 7px; vertical-align: middle`，**被设计成内联在文本后**，
我却把它当 flex 子项。改为内联进 `.sc-n` 内（与连接器 picker 的 `.pn` 用法逐字一致），
并把标签缩短为「内置」/「已安装」，与既有「内置」/「需配置」同节奏。

### 未做（如实记录）

- **「未安装的目录卡也可展示 → 点击走安装」**（原修法第 2 条）未做：安装流程在 `ExpertsView.tsx`，
  该文件正被并发会话占用；且目录卡本身要等 WB-184 收敛完才知道该展示什么。picker 现在只列
  **真的会生效**的技能，空态引导去「技能」页安装 —— 已闭合本条的核心缺口。
- **`ProjectHomeView.tsx:26` 图标反查**（原修法第 4 条）未做：`InstalledSkill` 结构里**没有
  图标字段**，"改走已装清单"无从谈起。现状仍是 `SK_GRID` 查图标 + `🧩` 兜底（picker 沿用同一
  逻辑保持一致）。待 WB-183 的 `catalog_skills` 带上 `iconUrl` 后才有真实数据可用。

### 验证

- `npx tsc --noEmit` 过；`py_compile` 过。
- `GET /api/skills/builtin` → 6 条，路由未被 `{key}` 吃掉（TestClient 断言）。
- **真浏览器实测**：Playwright MCP 浏览器被并发会话独占（"Browser is already in use"），
  改用独立 headless Edge + Node 内置 WebSocket 走 CDP 自驱（`:5174`，因 `:5173` 被并发会话的
  vite 占用；后端因 stale code 硬重启过）。**23 项断言全过**：
  - picker 渲染 **12 张真实技能卡**（6 内置 + 6 已装），描述来自各自真实的 SKILL.md front-matter；
  - **静态假卡「腾讯微云」「腾讯自选股」「NeoData金融搜索」「QQ音乐助手」均已不在 picker**；
  - 选中「网络工程师」→ loadout chip 真出现 `["网络工程师"]`；
  - **明暗双主题各自显式设一遍**（应用默认已是暗色，不显式设会让「暗色测试」空跑）：
    两主题各渲染 12 张，卡片/标签的文字与底色亮度差 light 221/132、dark 198/66
    —— 无「白底白字 / 深底深字」（WB-004/008 老坑）；
  - 窄宽 860px：卡片正常、标签不竖排、无横向溢出。
- 后端链路已验证（本条不依赖 WB-179 的 slug 迁移）：`_index()` 的 key 含 `_skillhub_meta.json`
  的 `name`，实测 6 个已装技能**全部**能经 `skill_def(展示名)` 解析出真实 SKILL.md
  （网络工程师 3580 字符 / 文章去AI味工具 6017 字符 …），即 picker 选中后**真生效**。

- commit：未提交（待用户确认）。
