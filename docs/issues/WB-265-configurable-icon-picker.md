---
id: WB-265
title: 多个配置表单仍要求手工输入 Emoji，缺少统一图标选择器
severity: P1
area: ui
status: fixed
origin: 🏚 迁移遗留
files:
  - src/components/expert/CreateExpertModal.tsx:59
  - src/components/channel/AssistantSettingsForm.tsx:79
  - src/components/composer/ModelConfigModal.tsx:371
  - src/views/KnowledgeView.tsx:352
  - console/src/SkillEditor.tsx:306
  - console/src/SkillsPage.tsx:358
  - console/src/pages/ProjectDetailPage.tsx:93
created: 2026-07-21
---

## 问题

AgentMate App 与 Console 的多个配置表单把图标/头像定义为普通文本框，要求用户自行输入 Emoji；App 新建知识库虽提供若干按钮，但仍是页面内临时实现。各入口的默认值、可选范围、预览和键盘操作均不一致。

## 触发场景

创建专家、编辑助理、新增自定义模型、编辑技能/推荐位或新建知识库时，用户看到窄文本框或一排无说明 Emoji，需要自行寻找和输入字符，无法搜索、预览名称或稳定选择。

## 影响

P1：这是高频配置表单的共同交互缺陷，既不符合专业组件化体验，也容易录入空值、组合字符或显示不一致的图标。

## 建议修法

- 建立 App/Console 共享的图标选择器，提供当前值预览、搜索、分组网格、选中态、键盘可达与暗色主题适配。
- 默认保存现有字符串图标值，兼容已有 Emoji 数据和所有现有展示端。
- 支持传入业务专用选项，使知识库继续保存既有 icon key，而不是破坏后端契约。
- 替换全部普通 `icon/avatar` Emoji 文本输入；高级 JSON 保留为高级原始数据入口。

## 验证

- 审计到的 7 个表单全部使用共享图标选择器，不再存在 `aria-label="头像 emoji"` 或图标普通 Input。
- 选择后预览与提交值一致，旧值不在预置列表时仍能展示并可重新选择。
- App/Console TypeScript 检查和生产构建通过。
- App/Console 明暗主题及窄屏下可打开、搜索、键盘选择和关闭选择器。

## 处理记录（2026-07-21）

- 新增 App/Console 共用的 `IconPicker`，提供当前值预览、中文/英文关键词搜索、分组网格、选中态、Tooltip、键盘 Enter 选择与响应式布局。
- 将创建专家、助理设置、自定义模型、App/Console 新建知识库、Console 技能编辑和推荐位管理共 7 个表单入口切换为统一选择器；知识库继续保存原有 icon key，未知存量值仍可展示。
- 全仓扫描确认自由输入 Emoji 的表单入口为 0；App 与 Console TypeScript 检查及生产构建通过。
- 浏览器实测 App/Console：暗色与浅色主题正常，搜索与 Enter 回填正常，Console 在 780px 宽度下无面板溢出；验收期间未提交任何测试表单。
- Commit：本提交。
