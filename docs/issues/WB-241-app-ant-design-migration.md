---
id: WB-241
title: AgentMate App 仍使用手写组件体系，未统一到 Ant Design 6 与 Pro Components
severity: P1
area: frontend
status: fixed
origin: 🏚 迁移遗留
files:
  - src/App.tsx:1
  - src/main.tsx:1
  - src/components/:1
  - src/views/:1
created: 2026-07-21
---

## 问题

AgentMate Server Console 已迁移到 Ant Design 6.5.1 + Pro Components 3.1.14-2，
但桌面 App 的应用外壳、导航、页面反馈、表单、弹窗、列表和详情面板仍主要由原生标签与手写 CSS 组件组成。
根因是 App 尚未建立统一的 Ant Design `ConfigProvider`、Pro Components 页面边界与兼容既有
WorkBuddy 视觉 token 的组件层。

## 触发场景

打开 App 的首页、项目、自动化、专家、技能、连接器、知识库、文件或设置页面 →
相同语义的按钮、输入框、弹窗、列表和空状态由多套手写实现呈现，交互反馈和可访问性不一致。

## 影响

P1。App 是主要用户端，手写控件规模继续增长会提高主题、键盘操作、加载态、校验、弹窗焦点管理和响应式维护成本，
也无法与已迁移的 Console 形成一致的专业组件基线。

## 建议修法

- 固定依赖为 Ant Design 6.5.1 与 Pro Components 3.1.14-2。
- 在 App 根节点接入 `ConfigProvider`、Ant Design App 上下文和与现有语义 token 对齐的明暗主题算法。
- 使用 ProLayout/ProCard/PageContainer 等建立应用外壳和页面级边界；用 Ant Design 的 Button、Input、
  Select、Modal、Drawer、Tabs、Table/List、Empty、Spin、Badge、Tooltip、Dropdown 等替换手写基础控件。
- 保留既有 Zustand、SSE、路由、Tauri 平台抽象和真实 API 数据流；不重设计业务信息架构。
- 为仍需保持 WorkBuddy 高保真外观的业务组件提供统一适配层，不改变现有业务 class/token 契约。

## 验证

- `npx tsc --noEmit` 与 App/Console 生产构建通过。
- 浏览器实测首页、项目、聊天、自动化、专家/技能/连接器、知识库、文件与设置等主要入口。
- 明暗主题与窄宽布局正常，浏览器控制台无运行时错误。
- API/SSE、项目与会话深链、Tauri 平台调用保持原行为。

## 处理记录（2026-07-21）

- 改动：精确固定 Ant Design 6.5.1 与 Pro Components 3.1.14-2；新增根级 `ConfigProvider`/Ant App
  明暗主题、ProLayout 与 PageContainer；新增兼容既有 WorkBuddy class/token 的 Ant Button、Input、
  TextArea、Select、Checkbox、Slider 适配层；全部业务按钮/表单迁移到适配层，隐藏文件 input 仅作为浏览器
  文件系统边界保留；全部手写遮罩弹窗迁移到 Ant Modal，浮层与全局反馈迁移到 Ant Popover/Message。
- 验证：`pnpm build` 通过（App + Console）；`pnpm test:regression` 39/39 通过；真实 `:8102`
  验收 11 个静态入口均进入 Pro PageContainer、无横向溢出；新建项目 Ant Modal 自动聚焦并支持 Escape，
  工作空间 Ant Popover 支持 Escape；明暗主题均实看；860×720 下侧栏抽屉与内容布局正常。浏览器发现的
  Modal 旧属性提示已改为 Ant Design 6 的 `mask.closable` 新 API，并经 TypeScript 与回归构建复核。
- commit：本提交（WB-241）

## 继续处理（2026-07-21）

- 复核：首阶段完成了依赖、根主题、页面边界与基础控件适配，但主侧栏、页面 Tabs、业务卡片/列表、
  筛选区、表格、空态和加载态仍主要是手写结构，尚未达到本 issue「页面级专业组件统一」的验收口径。
- 范围：继续迁移上述页面结构到 Ant Design / Pro Components，同时保留 WorkBuddy class 与设计 token，
  不改变业务路由、状态和真实 API 数据流。

## 二阶段处理记录（2026-07-21）

- 改动：主侧栏迁移到 Ant Menu/Collapse/List/Dropdown/Badge；设置中心导航迁移到 Ant Menu；首页、项目、
  自动化、助理、专家/技能/连接器、知识库、金山文档、我的文件和项目工作台统一使用 ProCard、Tabs、
  List、Table、Empty、Spin、Result、Upload.Dragger、Statistic、Segmented、Select、Switch、Tag、Breadcrumb
  等页面级组件；保留原 WorkBuddy class 与主题 token，并补齐 Ant 语义 DOM 的明暗/响应式兼容样式。
- 验证：`pnpm build` 通过（App + Console）；`pnpm test:regression` 52/52 通过；本机 Edge 实测首页、
  项目、自动化、技能、助理、知识库、我的文件，明暗主题均正常；860×720 项目页侧栏抽屉与两列模板
  布局正常；源码审计无原生 button/select/textarea/table，唯一原生 input 是浏览器文件选择边界。
- commit：本提交（WB-241）
