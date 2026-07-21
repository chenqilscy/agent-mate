# AgentMate Console 管理门户设计

> 状态：Server 管理功能与 React + Ant Design Console 已落地；Skill 发布治理由
> [WB-245～WB-250](issues/README.md) 完成。更新于 2026-07-21。

## 1. 定位

AgentMate Console 是 AgentMate Server 的同源 Web 管理界面，服务于组织管理员、项目管理员和
能力运营者。它不是 AgentMate App 的 Web 版，也不承担本地 agent、LLM、MCP 或文件执行。

```text
AgentMate App      私密执行、工作区、会话、凭据、本机安装
AgentMate Server   账号、组织、项目协作、AgentMate 能力目录权威
AgentMate Console  通过 Server /api 管理控制面
```

数据边界以 [`agentmate-数据分层与同步规范.md`](agentmate-数据分层与同步规范.md) 为准。

## 2. 当前实现

### 2.1 托管形态

Server `:8100` 同源提供 API 与 Console：

- `console/`：React + Ant Design 源码。
- `server/web/console-dist/`：Console 构建产物。
- Server 对全部 Console 稳定路由提供 History API 回退到 `console-dist/index.html`；未知 `/api/*`
  仍返回 404，不会被 HTML 入口伪装成成功。

旧 `server/web/console.html` 已删除；运行时不依赖 Node，构建产物必须随 Server 发布。

### 2.2 已有模块

- 账号登录、平台管理员身份与用户管理；
- 组织及成员；
- 项目、成员/角色、邀请、配置；
- 工作项、里程碑、看板/列表/甘特、活动与评论；
- 项目讨论、@提及、在线状态、通知与团队时间线；
- 专家、专家团、连接器、Skill 定义及各自推荐位；
- 知识库控制面；
- 稳定 URL 与深链回退。

## 3. 数据与权限边界

Console 只能管理 Server 权威数据：

| 可管理 | 不可管理 |
|---|---|
| 账号、组织、项目、成员角色、邀请 | App 本机会话正文与工具轨迹 |
| Server 协作实体与最小时间线元数据 | workspace 文件和产物本体 |
| AgentMate 自有专家/团队/连接器/Skill 定义 | LLM key、连接器 token、OAuth token |
| 能力推荐位、Skill release、审核、灰度与撤回 | 第三方 SkillHub Key、榜单镜像、技能包与安装目录 |

平台管理员才能运营公共目录；项目写操作按 Owner/Admin/Member/Viewer 门禁。Viewer 只读。所有管理
API 仍需由 Server 校验，不能只靠前端隐藏按钮。

## 4. 信息架构

目标导航如下：

```text
AgentMate Console
├─ 概览
├─ 项目
│  └─ 概览 / 任务 / 协作 / 配置
├─ 目录运营
│  ├─ 专家与专家团
│  ├─ 连接器
│  └─ 技能
├─ 知识库
├─ 组织
├─ 用户
├─ 通知
└─ 账号 / 退出
```

React 迁移应保持现有稳定 URL 与 API 契约，逐页替换视图，不以一次性重写阻断管理功能。

## 5. 目录运营

### 5.1 定义与推荐位分离

定义描述“能力是什么、如何运行”，推荐位描述“在哪里、何时、以什么文案展示”。两者生命周期不同：

- 专家定义含稳定 slug、persona、标签和能力元数据；推荐位只引用 expert slug。
- 专家团定义引用稳定成员 expert slug；团队卡不等于多 Agent runtime。
- 连接器定义含 launch spec、工具与凭据变量名；真实 secret 只在 App 本机。
- AgentMate Skill 定义含指令、工具绑定和文件；推荐位可引用 AgentMate 或 SkillHub slug。

推荐位的排序、启停、排期和营销文案不能修改已安装能力的运行快照。

### 5.2 第三方 SkillHub

第三方 SkillHub 由每台 App 直接访问并在本机安装。Console 对 SkillHub 只能维护推荐指针：

```text
provider = skillhub
skill_slug
title / description / icon / category
placement / sort / enabled / starts_at / ends_at
```

Console 不搜索或代理商店，不保存 Key、榜单、安装包、`SKILL.md` 或 references。App 点击推荐后仍走本地
真实安装生命周期。

### 5.3 技能编辑

React 技能页支持列表、搜索/筛选/排序、类型化编辑、工具选择、文件树/编辑；保存会创建新 draft，
不能直接覆盖已发布定义。发布治理页统一处理测试、审核、灰度、撤回和回滚。
Server 必须继续校验：

- slug 与引用完整性；
- 工具名必须来自公开工具契约，未知工具拒绝保存；
- 保留文件名与路径穿越；
- dirty close、删除确认和 Viewer/非管理员门禁；
- 已安装副本的版本差异不能静默覆盖。

## 6. Skill 能力发布中心（已实现）

当前实现：

1. **草稿**：编辑不可变 release 的候选内容。
2. **Test Run**：真实 App 客户端以 Run ID、App/工具版本、trace/产物引用回传成功或失败证据；失败不能审核。
3. **审核**：作者与审核者分离，记录 hash、版本、权限 diff 与审核意见。
4. **发布**：配置通道、比例、最低 App/工具契约版本和生效时间，按账号稳定分桶；组织定向仍待扩展。
5. **监控**：查看兼容覆盖、安装/运行成功率、回滚率与非敏感错误码。
6. **撤回/回滚**：下发 tombstone 或上一 last-known-good 版本，不把网络失败当撤回。

Server 对象、客户端 capability report 与状态机见
[`agentmate-server-架构设计.md`](agentmate-server-架构设计.md)。

## 7. React + Ant Design 维护规则

- 迁移单位是稳定路由，不是散落组件；每迁一页保留原 API 与深链。
- 复用统一的 Layout、Menu、Form、Table、Modal/Drawer、Result、notification 和权限守卫。
- 迁移前后都要覆盖登录失效、403、404、空态、加载、保存失败和窄屏。
- legacy CSS 与 React 样式隔离，避免全局选择器污染；暗色主题必须真实检查。
- 构建产物由 `pnpm build:console` 生成；Server 启动不应在运行时依赖 Node。
- 迁移完成后再删除 `console.html` 与回退逻辑，删除前必须确认所有稳定 URL 都已接管。

## 8. 非目标

- 不在 Console 远程执行 App agent 或访问用户本地文件。
- 不集中保存个人凭据或第三方 SkillHub 内容。
- 不把目录卡、专家团成员表或 Test Run mock 当成真实能力。
- 不在没有签名、兼容门禁和回滚的情况下从网页替换 App 二进制。

## 9. 验收

- Server API 的权限门禁与 Console UI 状态一致，直接请求也不能越权。
- 项目与目录的稳定 URL 可刷新、前进/后退；未知 `/api/*` 保持 404，不被 HTML 回退伪装成 200。
- 构建产物缺失必须明确报错，不能回退到已删除的 legacy 页面。
- SkillHub 数据边界检查不允许 Server 恢复镜像、Key 或技能包。
- Skill 草稿、失败测试不得出现在普通 App 下行；发布/暂停/撤回/回滚必须有审计记录。
