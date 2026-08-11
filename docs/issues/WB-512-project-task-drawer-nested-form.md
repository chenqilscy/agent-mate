---
id: WB-512
title: Console 项目任务抽屉将评论表单嵌套在任务编辑表单内
severity: P2
area: frontend
status: open
origin: 🆕 近期改动
files:
  - console/src/components/project/ProjectWorkspace.tsx:985
  - console/src/components/project/ProjectWorkspace.tsx:1548
created: 2026-08-11
---

## 问题
项目任务详情抽屉以一个 Ant Design `Form` 包裹任务编辑内容，又在“任务协作”区域渲染独立评论 `Form`，最终生成 `<form>` 嵌套 `<form>` 的无效 HTML。React 在真实浏览器中明确报告 hydration/DOM nesting 错误。

## 触发场景
平台管理员打开任一可写项目的真实任务详情抽屉；只要评论输入区域渲染，浏览器控制台就出现 `form cannot be a descendant of form` 与 `form cannot contain a nested form` 两条错误。

## 影响
无效表单结构可能导致 Enter 提交命中错误处理器、任务保存与评论发送互相干扰，也会让浏览器和辅助技术对控件归属产生歧义。该入口涉及真实任务变更与评论写入，按 P2 跟踪。

## 建议修法
拆分任务编辑与评论提交的 DOM 表单边界：优先把评论表单移出外层任务 `Form`，或让其中一层使用 `component={false}` 并显式绑定独立提交按钮；同时补渲染测试，断言任务抽屉不存在嵌套 `<form>`。

## 验证
真实项目任务抽屉中分别验证任务保存、Enter 行为和评论发送；DOM 中不存在嵌套 `<form>`，控制台无 React nesting/hydration 错误，评论和任务保存仍各自只触发一次请求。
