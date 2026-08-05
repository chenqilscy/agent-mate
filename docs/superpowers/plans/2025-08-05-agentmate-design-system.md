# AgentMate 设计系统化 · 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有散装 CSS 升级为完整的四层设计 token 体系，消除 60+ 处硬编码暗色覆盖和 30+ 处语义色散落。

**Architecture:** 保持现有 tokens.css 骨架，新增间距/字体/圆角/阴影 token。`--card` 修复为暗色自动翻转，旧覆盖规则逐步移除。语义色统一定义。Ant Design ConfigProvider token 同步更新。

**Tech Stack:** CSS Custom Properties, TypeScript (Ant Design ConfigProvider), no new dependencies.

**Spec:** `docs/superpowers/specs/2025-08-05-agentmate-design-system.md`

## Global Constraints

- 视觉零重设计：CSS class 名不变，只换 token 引用方式
- 暗色主题 = `body.dark` 变量覆盖，不改机制
- 旧 token 名保留为别名，渐进过渡，不一次性删除
- 每次改动后 `npx tsc --noEmit` 必须通过
- 改完需在明暗双主题下目视验收
- 单 token 改动即为一个 commit

---

### Task 1: 重写 tokens.css — 新增设计 token 体系

**Files:**
- Modify: `src/styles/tokens.css` (全量重写)

**Interfaces:**
- Consumes: 无（基础层）
- Produces: 所有新 token 变量供 app.css/antd.css/组件引用
  - 品牌色: `--brand-50` ~ `--brand-900` (保留 `--brand`, `--brand-600`, `--brand-soft`, `--brand-soft2` 为别名)
  - 中性灰: `--neutral-0` ~ `--neutral-900`
  - 文本: `--text`, `--text-2`, `--text-3` (保留旧名，映射到 neutral)
  - 边框: `--border`, `--border-2` (保留旧名)
  - 表面: `--bg-surface` (替代 `--card`), `--bg-page`, `--bg-elevated`, `--bg-chip` (替代 `--chip`)
  - 间距: `--space-xs`(4) `--space-sm`(8) `--space-md`(12) `--space-lg`(16) `--space-xl`(24) `--space-2xl`(32) `--space-3xl`(48)
  - 字体: `--text-xs` ~ `--text-3xl`, `--font`, `--font-size-base`, `--line-height-base`
  - 圆角: `--radius-sm`(6) `--radius-md`(10) `--radius-lg`(14) `--radius-full`(999px)
  - 阴影: `--shadow-sm`, `--shadow-md`, `--shadow-lg`, `--shadow-xl`
  - 语义: `--color-error`, `--color-warning`, `--color-info`
  - hljs: `--hl-comment` ~ `--hl-attr` (不变)

- [ ] **Step 1: 备份当前 tokens.css**

```bash
cp src/styles/tokens.css src/styles/tokens.css.bak
```

- [ ] **Step 2: 写入新 tokens.css**

新文件内容 —— `:root` 块定义所有 light 模式 token，`body.dark` 块覆盖暗色值。

```css
/* Design tokens — AgentMate Design System v2.
   Four-layer: base → token → component → page.
   Light theme in :root, dark theme as body.dark variable overlay. */

/* ============================================================
   Layer 1: Base — font stack, scrollbar, reset, animations
   ============================================================ */
:root {
  /* Typography base */
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
  --font-size-base: 14px;
  --line-height-base: 1.5714285714;

  /* ===== Layer 2: Design Tokens (Light) ===== */

  /* -- Brand Green Scale -- */
  --brand-50:  #EEFBF5;
  --brand-100: #D7F5E7;
  --brand-300: #6ED8A8;
  --brand-500: #16B37A;
  --brand-600: #0FA06C;
  --brand-700: #0C8A5C;
  --brand-900: #065836;

  /* Aliases for backward compat */
  --brand:      var(--brand-500);
  --brand-soft: var(--brand-50);
  --brand-soft2: #F1FAF5;

  /* -- Neutral Gray Scale -- */
  --neutral-0:   #FFFFFF;
  --neutral-50:  #F8F9FA;
  --neutral-100: #ECEEF1;
  --neutral-200: #D5D9DE;
  --neutral-300: #9AA0A6;
  --neutral-500: #5B6169;
  --neutral-700: #1F2329;
  --neutral-900: #0D1117;

  /* -- Surface Tokens (replace --card, --chip, body bg) -- */
  --bg-surface:  var(--neutral-0);    /* cards, popovers, modals */
  --bg-page:     var(--neutral-50);   /* page background */
  --bg-elevated: var(--neutral-0);    /* elevated surfaces (dropdowns) */
  --bg-chip:     #F4F5F7;            /* chips, tabs, hover */
  --bg-input:    var(--neutral-0);    /* input backgrounds */

  /* -- Text — aliased to neutral for backward compat -- */
  --text:   var(--neutral-700);
  --text-2: var(--neutral-500);
  --text-3: var(--neutral-300);
  --ink:    var(--neutral-700);

  /* -- Border — aliased to neutral for backward compat -- */
  --border:   var(--neutral-100);
  --border-2: #F2F3F5;

  /* Backward compat aliases */
  --card: var(--bg-surface);
  --chip: var(--bg-chip);
  --bg:   var(--bg-page);
  --line: var(--neutral-100);

  /* -- Spacing Scale (4px base) -- */
  --space-xs:  4px;
  --space-sm:  8px;
  --space-md:  12px;
  --space-lg:  16px;
  --space-xl:  24px;
  --space-2xl: 32px;
  --space-3xl: 48px;

  /* -- Typography Scale -- */
  --text-xs:   12px;
  --text-sm:   13px;
  --text-base: 14px;
  --text-lg:   16px;
  --text-xl:   18px;
  --text-2xl:  22px;
  --text-3xl:  28px;

  /* -- Radius -- */
  --radius-sm:   6px;
  --radius-md:   10px;
  --radius-lg:   14px;
  --radius-full: 999px;
  --r: var(--radius-lg);  /* backward compat */

  /* -- Shadows (blue-tint) -- */
  --shadow-sm: 0 1px 2px rgba(20,28,40,.05), 0 6px 18px -12px rgba(20,28,40,.22);
  --shadow-md: 0 10px 34px -14px rgba(20,28,40,.28);
  --shadow-lg: 0 20px 48px -16px rgba(20,28,40,.35);
  --shadow-xl: 0 32px 64px -20px rgba(20,28,40,.45);

  /* -- Semantic Colors -- */
  --color-error:   #E5484D;
  --color-warning: #F59E0B;
  --color-info:    #3B82F6;
  --color-success: #16B37A;

  /* -- highlight.js token colors (GitHub-light) -- */
  --hl-comment: #6a737d;
  --hl-keyword: #d73a49;
  --hl-string:  #22863a;
  --hl-number:  #005cc5;
  --hl-func:    #6f42c1;
  --hl-built:   #005cc5;
  --hl-attr:    #e36209;
}

/* ============================================================
   Dark Theme — variable overrides
   ============================================================ */
body.dark {
  /* Brand — keep primary stable, invert ends */
  --brand-50:  #065836;
  --brand-100: #0C6B42;
  --brand-300: #16B37A;
  --brand-500: #16B37A;  /* stable across themes */
  --brand-600: #1BBD7D;
  --brand-700: #21C985;
  --brand-900: #EEFBF5;
  --brand-soft:  var(--brand-50);
  --brand-soft2: #152A21;

  /* Neutral — flip the scale */
  --neutral-0:   #0D1117;
  --neutral-50:  #141A21;
  --neutral-100: #1F2329;
  --neutral-200: #2B3138;
  --neutral-300: #5B6169;
  --neutral-500: #9AA0A6;
  --neutral-700: #ECEEF1;
  --neutral-900: #FFFFFF;

  /* Surfaces — now auto-flip via neutral refs */
  --bg-chip:   #2A3036;
  --bg-input:  var(--neutral-50);
  --border-2:  #2B3138;

  /* Text/border aliases auto-flip via neutral refs above */

  /* Semantic — slightly adjust for dark contrast */
  --color-error:   #EF7074;
  --color-warning: #F9B83A;
  --color-info:    #6098F8;

  /* hljs dark palette */
  --hl-comment: #8b949e;
  --hl-keyword: #ff7b72;
  --hl-string:  #a5d6ff;
  --hl-number:  #79c0ff;
  --hl-func:    #d2a8ff;
  --hl-built:   #79c0ff;
  --hl-attr:    #7ee787;

  /* Shadows — stronger alpha in dark */
  --shadow-sm: 0 1px 2px rgba(0,0,0,.15), 0 6px 18px -12px rgba(0,0,0,.35);
  --shadow-md: 0 10px 34px -14px rgba(0,0,0,.45);
  --shadow-lg: 0 20px 48px -16px rgba(0,0,0,.55);
  --shadow-xl: 0 32px 64px -20px rgba(0,0,0,.65);

  color-scheme: dark;
}

/* ============================================================
   Global reset & base
   ============================================================ */
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body, #root { height: 100%; }
body {
  font-family: var(--font);
  font-size: var(--font-size-base);
  line-height: var(--line-height-base);
  color: var(--text);
  background: var(--bg-page);
  -webkit-font-smoothing: antialiased;
  display: flex;
  align-items: center;
  justify-content: center;
}
#root { width: 100%; }

/* Dark surface overrides — only for elements that need a specific
   dark tone different from the auto-flipping --bg-surface token.
   This is drastically reduced from the 55-line block in v1. */
body.dark .sc-top { background: linear-gradient(135deg, #20362C, #1E2A36); }
body.dark .mrow .off { background: #3A2326; color: #F98A8E; }
body.dark .pe-badge { background: transparent; }
body.dark .ctool.model .mk { background: var(--brand-50); }
body.dark .bell-dot { border-color: var(--neutral-50); }
body.dark .ov-art:hover { box-shadow: none; }
body.dark .fart .fi { background: var(--neutral-50); }
body.dark .selcard.sel { background: var(--brand-50); }
body.dark .upd, body.dark .upd-x, body.dark .upd .log { background: var(--bg-surface); }
body.dark .np-modal, body.dark .btn-ghost, body.dark .np-tplbtn, body.dark .selcard { background: #1F242A; }

/* Scrollbar */
::-webkit-scrollbar { width: 9px; height: 9px; }
::-webkit-scrollbar-thumb { background: #D7DAE0; border-radius: 9px; }
::-webkit-scrollbar-thumb:hover { background: #C2C6CE; }
body.dark ::-webkit-scrollbar-thumb { background: #4A515B; }
body.dark ::-webkit-scrollbar-thumb:hover { background: #606975; }

:focus-visible { outline: 2px solid var(--brand); outline-offset: 2px; border-radius: 6px; }

@media (prefers-reduced-motion: reduce) {
  * { animation-duration: .01ms !important; transition-duration: .01ms !important; }
}
body.reduce-motion * { animation-duration: .01ms !important; transition-duration: .01ms !important; scroll-behavior: auto !important; }

/* UI scale compensation */
body[data-ui-scale="90"]  .win { zoom: .9;  width: 111.111111%; height: 111.111111vh; }
body[data-ui-scale="95"]  .win { zoom: .95; width: 105.263158%; height: 105.263158vh; }
body[data-ui-scale="105"] .win { zoom: 1.05; width: 95.238095%;  height: 95.238095vh; }
body[data-ui-scale="110"] .win { zoom: 1.1;  width: 90.909091%;  height: 90.909091vh; }

/* Animations */
@keyframes rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
@keyframes pop  { from { opacity: 0; transform: translateY(6px) scale(.98); } to { opacity: 1; transform: none; } }
@keyframes tb   { 0%, 60%, 100% { opacity: .3; transform: translateY(0); } 30% { opacity: 1; transform: translateY(-3px); } }
@keyframes fade { from { opacity: 0; } }
@keyframes rot  { to { transform: rotate(360deg); } }
@keyframes pul  { 50% { opacity: .35; } }
```

- [ ] **Step 3: 验证 — 前端类型检查**

```bash
npx tsc --noEmit
```

- [ ] **Step 4: 验证 — 启动前端，检查页面不白屏、token 加载正常**

```bash
# 启动前端后访问 :8102，确认:
# 1. body 背景不是白色（应为 --bg-page）
# 2. 文字颜色正常（--text 已解析）
# 3. 无浏览器控制台 CSS 变量错误
```

- [ ] **Step 5: Commit**

```bash
git add src/styles/tokens.css
git commit -m "refactor(WB-xxx): rewrite design tokens — spacing, radius, shadow, semantic colors, auto-flip dark surfaces" -- src/styles/tokens.css
```

---

### Task 2: 更新 typography.css — 合并字体 token 到 tokens.css

**Files:**
- Modify: `src/styles/typography.css`

**Interfaces:**
- Consumes: 字体 token 已在 Task 1 的 tokens.css 中定义
- Produces: typography.css 简化，移除重复的 `:root` 块

`typography.css` 当前内容已合并到 tokens.css。此文件简化为只保留 Ant Design 菜单覆盖：

```css
.ant-menu-item {
  font-weight: 600;
}
```

- [ ] **Step 1: 写入简化版**

- [ ] **Step 2: `npx tsc --noEmit` 验证**

- [ ] **Step 3: Commit**

```bash
git add src/styles/typography.css
git commit -m "refactor(WB-xxx): simplify typography.css — font tokens moved to tokens.css"
```

---

### Task 3: 修复 antd.css — 消除未定义 token 引用

**Files:**
- Modify: `src/styles/antd.css`

**Interfaces:**
- Consumes: Task 1 定义的新 token (`--bg-page`, `--bg-elevated`)
- Produces: antd.css 中所有 token 引用均有定义

- [ ] **Step 1: 替换 `--bg` 引用**

`.agentmate-antd-app` 的 `background: var(--bg)` 改为 `background: var(--bg-page)`：

```css
/* Line 44 — was: background: var(--bg); */
.agentmate-antd-app {
  color: var(--text);
  background: var(--bg-page);
}
```

- [ ] **Step 2: 更新 `--bg-elevated` 回退值**

Popover 背景已有 fallback `#fff`，token 现已定义，移除 fallback：

```css
/* Line 153 — was: background: var(--bg-elevated, #fff); */
.wb-ant-popover .ant-popover-inner {
  background: var(--bg-elevated);
}
```

- [ ] **Step 3: 暗色 popover 背景改用 token**

```css
/* Line 168-170 — was: background: #242a31; */
body.dark .wb-ant-popover .ant-popover-inner {
  background: var(--bg-elevated);
}
```

- [ ] **Step 4: `npx tsc --noEmit`**

- [ ] **Step 5: Commit**

```bash
git add src/styles/antd.css
git commit -m "fix(WB-xxx): resolve undefined --bg and --bg-elevated in antd.css"
```

---

### Task 4: 更新 AppThemeProvider — 同步 Ant Design ConfigProvider token

**Files:**
- Modify: `src/components/ui/AppThemeProvider.tsx`

**Interfaces:**
- Consumes: Task 1 的新语义色 token
- Produces: Ant Design 组件使用更新后的颜色映射

- [ ] **Step 1: 更新共享 token 中的颜色引用**

`colorWarning` 从 `'#f0a020'` 改为 `'#f59e0b'`，与 `--color-warning` 一致：

```tsx
const sharedToken: ThemeConfig['token'] = {
  colorPrimary: '#16b37a',
  colorInfo: '#3b82f6',        // was '#1677ff', now matches --color-info
  colorSuccess: '#16b37a',
  colorWarning: '#f59e0b',     // was '#f0a020', now matches --color-warning
  colorError: '#e5484d',       // unchanged, matches --color-error
  borderRadius: 10,
  borderRadiusLG: 14,
  controlHeight: 36,
  ...uiTypographyToken,
}
```

- [ ] **Step 2: 更新暗色背景 token 映射**

将硬编码的暗色 hex 改为接近新 neutral token 的值：

```tsx
token: {
  ...sharedToken,
  colorBgBase:       dark ? '#0d1117' : '#ffffff',   // ~neutral-0
  colorBgContainer:  dark ? '#141a21' : '#ffffff',   // ~neutral-50
  colorBgElevated:   dark ? '#1f2329' : '#ffffff',   // ~neutral-100
  colorTextBase:     dark ? '#eceef1' : '#161a1d',   // ~neutral-700
  colorBorder:       dark ? '#2b3138' : '#e6e8eb',   // ~neutral-200
},
```

- [ ] **Step 3: `npx tsc --noEmit`**

- [ ] **Step 4: Commit**

```bash
git add src/components/ui/AppThemeProvider.tsx
git commit -m "refactor(WB-xxx): sync Ant Design ConfigProvider tokens with new design system"
```

---

### Task 5: app.css 暗色覆盖清理 — bulk 替换

**Files:**
- Modify: `src/styles/app.css`

**Interfaces:**
- Consumes: Task 1 的新 token 体系
- Produces: app.css 中 `background: #fff` 替换为 `background: var(--bg-surface)`，暗色自动翻转

**策略**：app.css 中约 60 处 `background: #fff`（light 模式卡片/面板背景），逐一替换为 `background: var(--bg-surface)`。由于 `--bg-surface` 在 body.dark 下自动翻转为 `#0D1117`，可删除对应的 55 行 `body.dark` 单独覆盖规则。

- [ ] **Step 1: 批量替换 `background: #fff` → `background: var(--bg-surface)`**

在 app.css 中搜索 `background: #fff`，共约 60+ 处。替换所有用于卡片/面板/弹窗表面的出现：

受影响的 class（代表性）：
`.win`, `.sidebar`, `.main`, `.composer`, `.tpl`, `.ecard`, `.scard`, `.conn`, `.pop`, `.profile`, `.more-menu`, `.scene`, `.qchip`, `.search-box`, `.cap-act`, `.btn-line`, `.my-proj`, `.ctool`, `.cicon`, `.insp`, `.inst-card`, `.activity`, `.scene-card`, `.fcard`, `.hcard`, `.card-menu`, `.skd-card`, `.skd-viewtoggle-btn.on`, `.home-metric`, `.home-run`, `.kd-item`, `.seg2 b.on`, `.mf-type`, `.np-modal`, `.btn-ghost`, `.selcard`, `.auto-tab.on`

- [ ] **Step 2: 替换 `background: #fff` → `background: var(--bg-surface)`**

```bash
# 不直接 sed — 使用 Edit 工具逐处替换，每处确认上下文
```

- [ ] **Step 3: 删除已不需要的 body.dark 单独覆盖**

移除 tokens.css 和 app.css 中所有 `body.dark .xxx { background: #22272D; }` 形式的规则（这些 class 现在通过 `var(--bg-surface)` 自动翻转）。

保留仍需特定暗色的规则：`.sc-top`, `.mrow .off`, `.ctool.model .mk`, `.selcard.sel`, `.upd/.upd-x`, `.np-modal/.btn-ghost/.np-tplbtn/.selcard`（这些不是纯表面色，有特殊色调）。

- [ ] **Step 4: 替换硬编码红色 → `var(--color-error)`**

在 app.css 中搜索 `#E5484D` 和 `#e5484d`，替换为 `var(--color-error)`：

受影响的 class：`.auto-chip.err`, `.pop-item.danger`, `.step .del`, `.mf-check .bx`, `.cmt`, `.home-metric.danger`, `.msg-unread`, `.insp-f .hea.on`, `.bell-dot`, `.auto-detail-path .err`, `.run-st.err`, `body.dark .mrow .off`

- [ ] **Step 5: 替换硬编码 amber → `var(--color-warning)`**

搜索 `#F0A020` / `#f0a020`，替换为 `var(--color-warning)`：
`.home-run-dot.waiting`, CTS popover system prompt

- [ ] **Step 6: 替换硬编码 blue → `var(--color-info)`**

搜索 `#2E7FF2` → `var(--color-info)`：
`.step a`, `.pv-md a`, `.pv-note a`, `.code-ln .k`, `.oa-ic`, `.pe-product-badge`

- [ ] **Step 7: 替换硬编码 brand → `var(--brand)`**

搜索 `#16B37A` / `#16b37a` → `var(--brand)`：
app.css 中所有非 token 定义的品牌色引用

- [ ] **Step 8: `npx tsc --noEmit`**

- [ ] **Step 9: 明暗双主题目视验收**

在 :8102 切换主题，确认卡片/面板/弹窗背景正确，暗色模式下无白底卡片。

- [ ] **Step 10: Commit**

```bash
git add src/styles/app.css src/styles/tokens.css
git commit -m "refactor(WB-xxx): migrate app.css to new design tokens — auto-flip dark surfaces, semantic colors"
```

---

### Task 6: TSX 组件硬编码颜色清理

**Files:**
- Modify: `src/components/chat/MessageList.tsx`
- Modify: `src/components/expert/TeamOrchestrationPanel.tsx`
- Modify: `src/components/connector/ConnectorDetailModal.tsx`
- Modify: `src/components/composer/CtxPopover.tsx`
- Modify: `src/components/project/ProjectWork.tsx`
- Modify: `src/lib/icons.tsx`

**Interfaces:**
- Consumes: Task 1 的 CSS 变量，通过 `var(--color-*)` 在 inline style 中引用
- Produces: 所有硬编码颜色改为 token 引用

- [ ] **Step 1: MessageList.tsx — 替换 `color: '#E5484D'`**

Line 42: `style={{ color: '#E5484D' }}` → `style={{ color: 'var(--color-error)' }}`

- [ ] **Step 2: TeamOrchestrationPanel.tsx — 替换两处 `#E5484D`**

Lines 125, 135: `'#E5484D'` → `'var(--color-error)'`

- [ ] **Step 3: ConnectorDetailModal.tsx — 替换 `#C77700`**

Line 180: `color: '#C77700'` → `color: 'var(--color-warning)'`

- [ ] **Step 4: CtxPopover.tsx — 替换 COLORS 对象中的硬编码**

```tsx
// was:
const COLORS = { 系统提示词: '#16B37A', 工具及子智能体: '#F0A020', ... }
// now:
const COLORS = { 系统提示词: 'var(--brand)', 工具及子智能体: 'var(--color-warning)', ... }
```

- [ ] **Step 5: ProjectWork.tsx — 替换 DOT 常量**

```tsx
// was:
const DOT = { todo: '#9AA0A6', doing: '#3D6BFF', paused: '#F0A020', review: '#8B5CF6', done: '#16B37A' }
// now:
const DOT = { todo: 'var(--text-3)', doing: 'var(--color-info)', paused: 'var(--color-warning)', review: '#8B5CF6', done: 'var(--brand)' }
```

同时修复 line 933 的 `color: '#EF4444'` → `color: 'var(--color-error)'`（之前用的是 #EF4444，与 #E5484D 不一致）

- [ ] **Step 6: icons.tsx — 替换 SVG fill 硬编码**

Line 75-78: `fill="#16B37A"` → `fill="var(--brand)"`, `fill="#0E8A5F"` → `fill="var(--brand-700)"`, `fill="#eafff6"` → `fill="var(--brand-50)"`

- [ ] **Step 7: `npx tsc --noEmit`**

- [ ] **Step 8: Commit**

```bash
git add src/components/chat/MessageList.tsx src/components/expert/TeamOrchestrationPanel.tsx src/components/connector/ConnectorDetailModal.tsx src/components/composer/CtxPopover.tsx src/components/project/ProjectWork.tsx src/lib/icons.tsx
git commit -m "refactor(WB-xxx): replace hardcoded colors in TSX with CSS variable references"
```

---

### Task 7: 页面级验证 — Chat / Home / Projects

**Files:**
- (所有已修改文件)

**验证清单（不做代码改动，只验收）：**

- [ ] **Step 1: 启动前后端，确认服务正常**

```bash
# 确认 :8100 :8101 :8102 都在运行
```

- [ ] **Step 2: Chat 页面 — 明暗双主题**

1. 打开 Chat 页面，发一条消息
2. 确认消息气泡颜色正确（用户=品牌绿，AI=中性灰）
3. 切换到暗色主题，确认气泡颜色仍可读
4. 确认 `.chat-head`, `.chat-scroll`, `.composer` 背景正常
5. 确认 AskUserCard 在暗色下可见

- [ ] **Step 3: Home 页面 — 明暗双主题**

1. 打开 Home 页面
2. 确认 hero title、scene selector、quick chips 颜色
3. 确认 home-console 卡片背景在暗色下为暗色
4. 确认 mascot SVG 可见（颜色使用新的 token 引用）
5. 切换暗色，确认无白底卡片

- [ ] **Step 4: Projects 页面 — 明暗双主题**

1. 打开 Projects 页面
2. 确认 project cards (`.my-proj`) 背景
3. 确认 health portfolio 卡片
4. 确认 filter/search bar
5. 切换暗色，确认所有卡片背景翻转
6. 确认 `.projects-context` banner 各 tone 变体正常

- [ ] **Step 5: 窄屏验收（≤900px）**

1. 缩小窗口到 ≤900px
2. 确认侧栏抽屉打开时背景/文字正确
3. 确认 `.nav-scrim` 遮罩正常

- [ ] **Step 6: 运行类型检查**

```bash
npx tsc --noEmit
```

---

### Task 8: 收尾 — 清理备份文件

- [ ] **Step 1: 删除备份**

```bash
rm src/styles/tokens.css.bak
```

- [ ] **Step 2: 最终类型检查**

```bash
npx tsc --noEmit
```

- [ ] **Step 3: 提交所有剩余变更**

```bash
git add -A  # 谨慎：只应在确认无夹带变更后执行
git commit -m "chore(WB-xxx): finalize design system migration — remove backup, verify"
```
