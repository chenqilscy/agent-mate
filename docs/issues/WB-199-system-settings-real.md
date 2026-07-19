---
id: WB-199
title: 系统设置仍是占位页，需要持久化并真实作用于应用
severity: P1
area: fullstack
status: fixed
origin: 既有实现
files:
  - src/components/settings/SettingsModal.tsx:609
  - src/stores/uiStore.ts:51
  - backend/routers/prefs.py:20
  - backend/storage/db.py:2120
created: 2026-07-20
---

## 问题

设置中心的“系统设置”仍由 `Soon` 占位，只展示“即将上线”；用户无法保存任何应用级偏好。
现有主题、权限与启动页面分别散落在前端内存或 localStorage，也没有统一的按用户持久化和启动应用流程。

## 触发场景

打开“设置 → 系统设置” → 只有规划文字，没有可操作项；重开应用后无法按用户恢复界面缩放、
动效偏好、默认权限和默认启动页。

## 影响

P1：核心设置入口不可用，直接影响可读性、无障碍、默认安全行为和多页启动体验。

## 建议修法

- 在现有 `/api/settings` 下增加 owner-scoped 的 system GET/PUT，复用 `user_settings`，对枚举和范围做白名单校验。
- 首期只提供会真实生效的应用级设置：界面缩放、减少动效、默认执行权限、默认启动页；不放无执行链路的假开关。
- 前端新增 system settings store：启动时加载、即时应用到 DOM/执行设置，并在设置页保存与恢复默认。
- 与 WB-197 路由联动：根路径启动时尊重默认启动页，显式 URL 永远优先。
- 所有控件复用现有设置中心 class 与主题 token，补齐键盘可达、禁用/保存/错误状态。

## 验证

- GET 返回默认值；PUT 保存后重启/刷新仍按当前 owner 回读，非法值被拒绝或归一化。
- 缩放、减少动效、默认权限和默认启动页均有可观察的真实效果，不只是保存字段。
- 明暗主题下设置行、分段控件、选择框和按钮均清晰；窄宽设置面板可操作。
- `npx tsc --noEmit`、`npx vite build`、后端 `py_compile` 与设置 API 冒烟通过。

## 处理记录（2026-07-20）

- 新增按 owner 持久化的 `GET/PUT /api/settings/system`，白名单校验界面缩放、减少动效、默认权限和默认启动页。
- 新增 system settings store，启动时真实应用缩放/动效/权限；根路径尊重默认启动页，显式深链优先。
- 系统设置改为参考图的信息层级：宽版双栏、卡片行、字号滑杆、权限/启动页选择与保存/恢复默认；仅提供有执行链路的设置。
- 独立临时后端真实 API 测试 5 项通过：默认值、保存返回、GET 回读、非法值 422、owner 隔离。
- 浏览器实测浅色、深色、800px 窄屏；portal 修复后弹窗位于视口内且水平溢出为 0。
- 后端 `py_compile`、前端类型检查与生产构建通过。

状态：`fixed`（本次提交，见 Git 历史）。
