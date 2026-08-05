# AgentMate 设计系统化 · 设计文档

**日期**：2025-08-05
**状态**：已确认
**Ardot 文件**：AgentMate 项目 → `🎨 Design System` 页面

## 背景

AgentMate 当前 CSS 体系存在以下结构性问题（来自代码审计）：

- `--r` token（12px）定义但从未使用，所有圆角硬编码散落 100+ 处
- `--card` 在暗色模式下不翻转，导致 60+ 条 `body.dark` 单独覆盖
- `--bg`、`--bg-elevated`、`--line` 被引用但从未定义
- 错误红 `#E5484D` 在 CSS 和 TSX 中硬编码 30+ 次
- 无间距系统、无字体层级变量
- 5 个独立的语义色系（error/warning/link/success/brand）无统一 token

## 目标

建立可维护的设计 token 体系，以 Chat/Home/Projects 三个核心页面验证可行性。

## 设计系统架构（四层）

```
页面层   Chat · Home · Projects
组件层   按钮/输入框/卡片/弹窗/消息气泡
Token层  颜色/字体/间距/圆角/阴影
基础层   明暗主题引擎 · UI缩放
```

## 色彩系统

### 品牌色阶（Green）

| Token | Light | Dark | 用途 |
|-------|-------|------|------|
| `brand-50` | `#EEFBF5` | `#065836` | 极浅底 |
| `brand-100` | `#D7F5E7` | `#0C6B42` | 选中/悬浮 |
| `brand-300` | `#6ED8A8` | `#16B37A` | 边框/装饰 |
| `brand-500` | `#16B37A` | `#16B37A` | **主品牌色** |
| `brand-600` | `#0FA06C` | `#1BBD7D` | hover 加深 |
| `brand-700` | `#0C8A5C` | `#21C985` | active 按下 |
| `brand-900` | `#065836` | `#EEFBF5` | 深底反白 |

### 中性灰（Neutral）

| Token | Light | Dark | 用途 |
|-------|-------|------|------|
| `neutral-0` | `#FFFFFF` | `#0D1117` | 卡片/表面白 |
| `neutral-50` | `#F8F9FA` | `#141A21` | 页面底色 |
| `neutral-100` | `#ECEEF1` | `#1F2329` | 边框/分割线 |
| `neutral-200` | `#D5D9DE` | `#2B3138` | 输入框边框 |
| `neutral-300` | `#9AA0A6` | `#5B6169` | 占位文字 |
| `neutral-500` | `#5B6169` | `#9AA0A6` | 辅助文字 |
| `neutral-700` | `#1F2329` | `#ECEEF1` | 正文 |
| `neutral-900` | `#0D1117` | `#FFFFFF` | 标题/强调 |

### 语义色

| Token | Light | 用途 |
|-------|-------|------|
| `semantic-red` | `#E5484D` | 错误/删除/危险 |
| `semantic-orange` | `#F59E0B` | 警告/等待 |
| `semantic-blue` | `#3B82F6` | 链接/信息 |

## 字体层级

| Token | 字号/字重/行高 | 用途 |
|-------|---------------|------|
| `text-3xl` | 28px / 700 / 1.2 | 主标题（Home 等） |
| `text-2xl` | 22px / 600 / 1.3 | 页面标题 |
| `text-xl` | 18px / 600 / 1.4 | 面板标题 |
| `text-lg` | 16px / 500 / 1.5 | 卡片标题 |
| `text-base` | 14px / 400 / 1.6 | 正文 |
| `text-sm` | 13px / 400 / 1.5 | 辅助说明 |
| `text-xs` | 12px / 400 / 1.5 | 时间戳/Badge |

字体栈沿用现有：`-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", Arial, sans-serif`

## 间距阶梯

| Token | 值 | 用途 |
|-------|-----|------|
| `space-xs` | 4px | 紧凑内边距、图标文字间距 |
| `space-sm` | 8px | 标签内边距、小间距 |
| `space-md` | 12px | 卡片内边距、列表间距 |
| `space-lg` | 16px | 组件间距、输入框内边距 |
| `space-xl` | 24px | 内容区间距 |
| `space-2xl` | 32px | 页面内边距 |
| `space-3xl` | 48px | 页面级分隔 |

## 圆角

| Token | 值 | 用途 |
|-------|-----|------|
| `radius-sm` | 6px | 标签/Badge/小按钮 |
| `radius-md` | 10px | 输入框/下拉 |
| `radius-lg` | 14px | 卡片/弹窗/面板 |
| `radius-full` | 999px | 药丸按钮/头像 |

## 阴影（保持现有 blue-tint 方向）

| Token | 用途 |
|-------|------|
| `shadow-sm` | 悬浮卡片 |
| `shadow-md` | 弹窗/下拉 |
| `shadow-lg` | 模态框/抽屉 |
| `shadow-xl` | 全屏覆盖层（新增） |

暗色模式下阴影 alpha 值适当加大以保持可见性。

## 代码落地策略

### Phase 1：Token 层迁移
- `tokens.css` 重写，新 token 替换旧 token
- `--card` 修复为暗色自动翻转，消除 60+ 条 `body.dark` 覆盖
- 定义 `--bg`、`--bg-elevated`、`--line`（之前缺失）
- 旧 token 保留为别名，渐进过渡

### Phase 2：组件层对齐
- `AppThemeProvider.tsx` 的 Ant Design token 映射同步更新
- `WbButton`/`WbInput` 等基础组件走新 token

### Phase 3：页面落地
- Chat/Home/Projects 三个页面优先替换硬编码值为 token 引用
- 语义色（error/warning/link）集中定义，消除散落

## 验证

- 前端 `npx tsc --noEmit` 类型检查通过
- 明暗双主题目视验收
- 窄屏（≤900px）侧栏抽屉验收
- 三个核心页面（Chat/Home/Projects）确认无视觉退化
