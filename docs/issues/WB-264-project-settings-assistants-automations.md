---
id: WB-264
title: 项目配置缺少助手与自动化的真实绑定管理
severity: P1
area: frontend
status: fixed
origin: 既有实现
files:
  - src/views/ProjectHomeView.tsx:207
  - src/components/project/ProjectBindingsModal.tsx:1
  - src/styles/app.css:1243
  - src/lib/api.ts:147
  - src/stores/automationStore.ts:17
  - backend/tests/regression/test_project_bindings_contract.py:1
created: 2026-07-21
---

## 问题

项目配置侧栏已能管理指令、连接器、专家、技能、知识库和成员，但“自动化”仍是一段无操作入口的静态说明，
且完全没有“助手”配置。现有真实数据契约其实已经支持绑定：自动化用 `project_id`，助手用
`workspace=project:<id>`；项目页没有读取和维护这些关系，导致能力存在但项目配置不可见、不可操作。

## 触发场景

打开 AgentMate App 任意项目 → 查看右侧“项目配置”：无法看到当前绑定的助手和自动化，也不能把已有助手或
自动化加入项目、移出项目。用户必须离开项目，分别进入助手设置或自动化编辑器才能维护归属。

## 影响

P1：项目配置无法完整描述“谁来执行、何时执行”。同一个项目的专家、技能和知识都能就地配置，唯独助手与
自动化被拆散到全局页面，造成项目能力模型缺口和明显的发现性问题。

## 建议修法

- 在 App 项目配置新增“助手”和可操作的“自动化”区块，展示真实绑定数量与对象。
- 打开选择器时读取当前账号的助手/自动化；选中助手保存为 `workspace=project:<project_id>`，取消时仅将当前
  项目内已绑定助手恢复为 `default`，不改动属于其他项目或专属工作区的助手。
- 自动化选择保存为 `project_id=<project_id>`；取消当前项目绑定时写 `project_id=null`，不抢占已绑定其他
  项目的自动化，界面明确展示其现有归属并禁用选择。
- 权限沿用项目配置语义：Owner/Admin 可改，Member/Viewer 只读；失败必须提示且重新回读，不能乐观伪成功。
- Server/Console 不复制这两个本地执行面对象；Console 保持控制平面边界。

## 验证

- 项目配置展示助手与自动化数量、名称/图标和添加入口。
- 绑定/解绑后 `/api/assistants` 的 `workspace` 与 `/api/automations` 的 `project_id` 真值正确，刷新项目仍一致。
- 已绑定其他项目或专属工作区的对象不会被静默抢占；Viewer/Member 不出现修改入口。
- `npx tsc --noEmit`、相关回归测试通过；明暗主题和 800px 窄屏选择器可用且无控制台错误。

## 处理记录

- 2026-07-21：项目配置新增“助手”和“自动化”真实绑定区块，并增加统一选择器；选择器直接维护既有
  `workspace=project:<id>` / `project_id` 契约，支持绑定、解绑、数量与头像展示、空状态跳转和保存失败回读。
- 归属保护：属于其他项目或 `dedicated` 工作区的助手、属于其他项目的自动化仅展示归属且禁用，项目页不会
  静默抢占；Member/Viewer 沿用既有 `canManage` 权限，不显示修改入口。
- 验证：`npx tsc --noEmit`、`npx vite build`、新增 2 条绑定契约回归测试均通过；真机浏览器完成助手
  绑定→项目显示→解绑→API 回读闭环，空自动化展示创建入口，600px 窄屏无横向溢出，明暗主题均正常，
  浏览器控制台无错误；测试绑定已恢复，当前助手均为 `default`。
- 全量 `pnpm test:regression` 的既有 Ant Design 迁移检查仍因并行改动中的
  `src/components/ui/IconPicker.tsx` 报 1 条失败（其余 87 条通过），与本 issue 改动无关。
