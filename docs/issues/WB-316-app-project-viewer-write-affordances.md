---
id: WB-316
title: App 项目 Viewer 仍显示任务、评论与执行写入口
severity: P1
area: ui
status: open
origin: 既有实现
files:
  - src/views/ProjectHomeView.tsx:300
  - src/components/project/ProjectWork.tsx:647
  - src/components/project/ProjectWork.tsx:955
  - src/components/server/ServerCommentsPanel.tsx:97
  - backend/routers/chat.py:101
  - backend/routers/work_items.py:267
created: 2026-07-24
---

## 问题

项目详情只用 `project.role` 隐藏项目配置和成员管理操作，没有把 Viewer 只读状态传给项目计划、任务详情、
任务表、讨论面板和底部执行 Composer。Viewer 因此仍能看到并操作新建、拖拽、批量删除、字段编辑、评论、
Agent 执行与产物验收等写入口；后端会在请求后返回 403，但 UI 仍呈现为可用功能。

## 触发场景

以 Viewer 身份打开 Server 团队项目 → 计划页点击“新建待办”或拖动卡片、任务页修改状态/删除、讨论页发送
评论，或在底部输入任务发起执行 → 操作入口均可见，提交后才出现泛化的失败提示或请求被拒绝。

## 影响

P1。安全门禁仍由后端兜底，没有直接越权写入，但“只读”角色在核心工作台中表现为一组持续失败的可写控件，
用户无法在操作前判断权限，批量或复杂编辑后才失败会造成明显时间损失，也与 Console 的 Viewer 只读体验不一致。

## 建议修法

- 在项目工作区统一派生 `canWrite = role !== 'Viewer'`，传给计划、任务、详情、讨论和执行 Composer。
- Viewer 隐藏或禁用所有持久化写入口，保留查看、筛选、下载和只读详情；显示明确的“只读”状态说明。
- 使用交付接口已有的 `can_write` 约束执行/验收按钮，避免只靠提交后的 403。
- 保留后端 Viewer 403 作为防御纵深。

## 验证

- Viewer 打开项目时不出现新建、拖拽、批量写、删除、字段编辑、评论发送、执行和验收入口。
- Owner/Admin/Member 原有项目操作保持可用并真落 Server。
- 明暗主题和窄屏下只读提示可见；后端 Viewer 写请求仍返回 403。
