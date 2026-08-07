---
id: WB-427
title: App 与 Console 项目工作台能力和数据契约严重脱节
severity: P1
area: fullstack
status: in-progress
origin: 用户反馈
files:
  - src/views/ProjectHomeView.tsx:28
  - src/components/project/ProjectWork.tsx:1189
  - src/lib/api.ts:469
  - backend/routers/work_items.py:220
  - backend/server_client.py:470
  - console/src/pages/ProjectDetailPage.tsx:68
  - console/src/components/project/ProjectWorkspace.tsx:231
created: 2026-08-07
---

## 问题

App 与 Console 打开同一个 Server 项目时，展示和可操作的项目能力不是同一套工作台。App 只有“动态 / 计划 / 任务 / 治理 / 资产 / 讨论”六个页签；Console 还提供概览、Backlog、工作量、里程碑、Sprint/迭代、甘特、知识库、协作和项目配置。Console 侧的自定义字段、Sprint、PM 偏好/保存视图、项目活动及知识库管理没有对应的 App API、状态模型或页面入口。

App 的计划视图还保存部分工作台偏好到本地 localStorage；对 Server 项目的知识库入口则直接提示“由 Console 统一管理”，但没有给出同一项目的 Console 管理入口或可见能力边界。结果是用户在 Console 创建或配置项目能力后，回到 App 既看不到完整状态，也无法判断哪些数据是同一来源、哪些操作应在哪里完成。

## 触发场景

在 Console 为团队项目配置自定义字段、Sprint、保存视图、知识库或项目成员/配置 → 使用同一账号在 App 打开该项目 → App 只有缩减后的六个页签，缺少对应状态和操作，知识库只能看到阻断提示；两端的项目工作台因此产生认知和数据断层。

## 影响

P1。项目是 App 与 Console 的核心共享对象；能力缺失会让跨端协作、任务执行和管理配置无法形成闭环，并可能诱导用户在本地视图偏好或错误入口上重复维护项目状态。

## 根因与建议修法

- 建立共享的项目工作台能力契约，明确 Server 权威字段、读写权限、App 可执行能力和 Console 专属管理能力，避免两端各自维护页签和数据模型。
- 为 App 补齐 Server 代理/客户端契约：项目活动、自定义字段、Sprint/迭代、PM 偏好/保存视图、知识库和项目配置的读取；允许的写操作必须沿用 Server 权限并失败关闭，禁止本地副本冒充权威。
- App 项目页展示与 Console 一致的项目导航/能力状态；暂未原生支持的能力应以同一项目 ID 直达 Console，并明确“查看/编辑位置”，不能只显示无后续动作的提示。
- 对任务、里程碑、治理、评论、成员和项目健康统一字段映射、刷新策略和错误语义，增加 App↔Server↔Console 的真实接口回归，保证 Console 写入后 App 能读回、App 允许的写入能在 Console 读回。

## 验证

- App 与 Console 类型检查、生产构建及后端编译/相关回归通过。
- 使用同一真实 Server 项目和同一账号，在 Console 写入项目配置/计划元数据后，App 通过真实 API 读回；反向写入也能被 Console 刷新读回。
- 覆盖 Viewer/Member/Admin 权限、Server 不可达和字段不存在等失败场景；无本地假数据、重复权威源、页面级横向溢出或新增控制台错误。

## 处理记录（2026-08-07，第一阶段）

- 已新增 App 后端到 Server 的项目活动、自定义字段、Sprint 和 PM 偏好读取代理，并复用 Server 身份与项目访问校验；Server 不可达或身份不匹配时明确失败，不回退为假数据。
- App 团队项目页已展示真实 Server 元数据计数，并提供同一项目 ID 的“在 Console 打开此项目”入口；移动端改为纵向布局，避免项目页横向溢出。
- 当前仍保留 Console 专属的配置编辑闭环和 App 计划视图本地偏好，因此本 issue 暂不关闭；下一阶段需要把共享模板/WIP/保存视图和自定义字段/Sprint 编辑统一到 Server 写接口，并补齐 App 的原生页签或明确的 Console 管理边界。
- 已验证：App `npx tsc --noEmit`、App `npx vite build`、Console `pnpm build:console`、后端 `py_compile` 均通过；浏览器 390px 深色/浅色首页“更多”菜单无横向溢出，键盘 Space 可打开。当前环境虽已配置 Server，但没有可用的已登录团队账号/项目，无法伪造真实团队项目双端回读验收，保留为下一阶段硬门槛。

## 处理记录（2026-08-07，第二阶段）

- 已定位并修正本机运行配置的实际连接错误：`backend/.env` 原先将 App Server 客户端指向远端 `:8101`，导致 App 把另一个 AgentMate 后端当成 Console/Server；现已改为远端 Console/Server `:8100`。该文件为本机忽略配置，不进入提交。
- 已新增 `PUT /api/server/projects/{project_id}/pm-preferences` 代理及严格 Server 写入客户端；团队项目看板的模板、WIP 和保存视图现在从 Server 读取，写入也沿用 Server 的项目角色权限；本机项目仍使用原有 localStorage 离线路径。
- 已使用真实 `admin` 团队账号和远端项目 `buddy` 验收：App 项目页实时展示 `Sprint 2 · 活动 7`，计划页真实加载任务；代理 PM 偏好读取 `templates=0/views=0/wip={}`，无副本数据。通过本地代理执行同值 WIP PUT 后，Server 回读仍为 `{}`。
- 已验证：`npx tsc --noEmit`、`npx vite build`、`pnpm build:console`、后端 `py_compile` 通过；App 项目页在真实登录态下可读回 Server 数据。由于真实项目当前无模板/保存视图，未通过创建持久测试数据来污染项目，模板/视图的完整写回还需在用户确认可接受的测试数据后继续验收。
- 本 issue 继续保持 `in-progress`：自定义字段/Sprint 原生编辑入口、Console 侧完整双端回读、Viewer/Member 权限矩阵及断网回归尚未全部完成。

## 处理记录（2026-08-07，第三阶段）

- App 项目工作台新增“项目数据”页签，直接展示同一 Server 项目的自定义字段、Sprint、共享工作台偏好与最近活动；接口未返回时显示读取中、空态或部分数据提示，不生成模拟数据。
- 每个数据卡提供回到同一项目 Console 的管理入口，并明确 App 负责查看项目事实，字段、Sprint 与 Console 专属配置仍由 Console 管理；本机项目显示独立说明空态，避免出现空白页。
- 使用真实 `admin` 账号打开 `buddy` 项目进行浏览器验收：页面显示 Server 权威接口、Sprint-0815 与 Sprint-0830、最近项目活动 7 条，自定义字段 0、共享工作台偏好 0，与 Server 数据一致。
- 验证：`npx tsc --noEmit`、`npx vite build`、`git diff --check` 已通过；浏览器真实 DOM 已读回项目数据，390px 窄屏 `scrollWidth=390` 且无浏览器 error 日志。
- 本 issue 继续保持 `in-progress`：自定义字段与 Sprint 的原生编辑 API、完整权限回归、离线/Server 不可达回归仍未完成，暂不关闭。

## 处理记录（2026-08-07，第四阶段）

- 补齐 App → Server 的字段/Sprint 严格写入代理：新增创建、更新、删除路由，复用 Server 原生 CRUD 和角色校验；Server 的 4xx 拒绝会原样映射，网络/5xx 失败返回 503，不写入本地副本。
- App“项目数据”面板对可写且 Server 可达的团队项目提供字段/Sprint 新增、编辑、删除表单；只读角色或 Server 不可达时自动保留 Console 管理入口和只读展示，本机项目路径不受影响。
- 使用真实 `admin` / `buddy` 项目验收：页面显示“新增字段”“新增 Sprint”、现有 Sprint 编辑/删除入口；表单可打开，390px 下 `scrollWidth=390`。未提交任何真实新增或删除，项目仍保持 Sprint 2、活动 7、字段 0。
- 失败语义回归：无效字段类型和反向日期 Sprint 请求均返回 400，未污染项目数据；Server PM 字段测试 4 项通过。
- 验证：`npx tsc --noEmit`、`npx vite build`、后端 `py_compile`、`git diff --check` 已通过；最终页面回归未产生新的控制台错误。本轮早期异步 Form 警告已改为受控草稿表单并移除。
- 本 issue 继续保持 `in-progress`：Viewer/Member 完整权限矩阵、Server 不可达的真实 UI 回归、Console 反向写入后刷新回读仍需补齐，暂不关闭。
