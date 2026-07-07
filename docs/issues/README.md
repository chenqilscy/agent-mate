# WorkBuddy Issues 登记册

本目录是项目的问题登记与处理台账。**所有发现的问题先登记为一条 issue，再处理**。
处理流程与规范由 skill `issue-tracker` 定义（`.claude/skills/issue-tracker/SKILL.md`），
可在会话中用 `/issue-tracker` 调起。

## 约定

- 每个问题 = 一个文件：`WB-<编号>-<短横线英文 slug>.md`（如 `WB-001-zombie-message-on-stop.md`）。
- 编号 `WB-###` 三位递增、不复用；新 issue 取当前最大编号 +1。
- 文件头 frontmatter 是**权威状态**；下方这张表是它的镜像，修改 issue 状态时**两处都要更新**。
- 状态流转：`open → in-progress → fixed`（或 `wontfix` / `deferred`）。
- 严重度：`P0` 立即修 · `P1` 尽快修 · `P2` 择机修 · `P3` 备忘。

## 台账

> 状态：⬜ open · 🟡 in-progress · ✅ fixed · ⏸ deferred · ⛔ wontfix

| ID | 状态 | 严重度 | 领域 | 标题 |
|----|------|--------|------|------|
| [WB-001](WB-001-zombie-message-on-stop.md) | ✅ | P0 | frontend | 停止/连接失败后助手消息永久卡在「执行中…」（+ 未处理 rejection） |
| [WB-002](WB-002-blocking-event-loop.md) | ✅ | P0 | backend | 工具同步执行阻塞事件循环、期间 `/stop` 失效、全部会话 SSE 卡死 |
| [WB-003](WB-003-loadout-leak-into-project.md) | ✅ | P0 | frontend | ad-hoc loadout（专家/技能/连接器）泄漏进项目执行 |
| [WB-004](WB-004-refpicker-plus-invisible.md) | ✅ | P0 | ui | RefPicker「＋」按钮浅色主题下白字白底不可见 |
| [WB-005](WB-005-model-overwritten-on-boot.md) | ✅ | P0 | frontend | 启动时用后端默认模型覆盖用户已保存的选择 |
| [WB-006](WB-006-refs-cleared-on-failed-send.md) | ✅ | P1 | frontend | 发送失败/被停止时，一次性 refs 仍被清空 |
| [WB-007](WB-007-chatsearch-stream-jitter.md) | ✅ | P1 | frontend | ChatSearch 流式抖动 + 当前高亮陈旧 |
| [WB-008](WB-008-dark-mode-gaps.md) | ✅ | P1 | ui | 暗色主题遗漏（btn-dark:disabled / add-btn / mrow.off） |
| [WB-009](WB-009-sqlite-single-connection.md) | ✅ | P1 | backend | 全局单 sqlite 连接被线程池 + 事件循环并发共享 |
| [WB-010](WB-010-refs-unbounded-payload.md) | ✅ | P1 | backend | refs 无数量/总量上限、name 不截断、`/chat` 无请求体上限 |
| [WB-011](WB-011-env-leak-to-connectors.md) | ✅ | P1 | backend | 连接器子进程继承整个 `os.environ`（含 `LLM_API_KEY`） |
| [WB-012](WB-012-session-status-not-reset-on-disconnect.md) | ✅ | P1 | backend | 客户端断开后会话状态永久停在 running/waiting |
| [WB-013](WB-013-owner-isolation-not-enforced.md) | ✅ | P2 | backend | owner_id 隔离未在路由生效（files 可跨项目读） |
| [WB-014](WB-014-run-command-not-sandboxed.md) | ✅ | P2 | backend | `run_command` 非真沙箱（`shell=True`，仅钉 cwd） |
| [WB-015](WB-015-concurrent-same-session-run.md) | ✅ | P2 | backend | 同一 session 并发 run 串道（`_stop_events`/`_answers` 按 session 共享） |
| [WB-016](WB-016-clickable-div-a11y.md) | ✅ | P2 | ui | 可点击 `<div>` 无键盘可达 / 焦点 |
| [WB-017](WB-017-upload-reads-full-body.md) | ✅ | P2 | backend | 上传先把整个请求体读进内存再判大小 |
| [WB-018](WB-018-chip-title-truncation.md) | ✅ | P2 | ui | 长文件名 chip / 长会话标题不截断 |
| [WB-019](WB-019-late-events-pollute-session.md) | ✅ | P2 | frontend | 迟到 SSE 事件污染新会话（onEvent 不校验当前流） |
| [WB-020](WB-020-sse-last-frame-flush.md) | ✅ | P2 | frontend | SSE 末帧无空行不冲刷、末尾多字节可能丢失 |
| [WB-021](WB-021-navopen-resize-residual.md) | ✅ | P2 | frontend | navOpen 跨 resize 残留（窄→宽→窄抽屉自开） |
| [WB-022](WB-022-context-window-zero-div.md) | ✅ | P2 | backend | `CONTEXT_WINDOW=0` 触发 usage 除零 |
| [WB-023](WB-023-low-severity-tail.md) | ⬜ | P3 | misc | 低危备忘集合（13 项，见文件内清单） |
| [WB-024](WB-024-sidebar-header-icons-stub.md) | ✅ | P2 | frontend | 侧栏头部三个图标按钮（收起/搜索/筛选）仅弹 toast、未实现 |
| [WB-025](WB-025-attach-file-size-limit-too-small.md) | ✅ | P2 | frontend | ＋菜单「添加文件」上限 200KB 过小（且被后端 8000 字符截断掩盖） |
| [WB-026](WB-026-plan-todo-detail-and-create-modals.md) | ✅ | P2 | frontend | 计划 · 待办详情弹窗 + 新建待办弹窗 + WorkItem 数据模型扩展 |
| [WB-027](WB-027-plan-toolbar-filter-batch-search.md) | ✅ | P2 | frontend | 计划 · 顶部工具条（归属/来源筛选 + 批量操作 + 搜索） |
| [WB-028](WB-028-plan-add-datasource-picker-placeholder.md) | ✅ | P2 | frontend | 计划 · 「添加数据源」选择器（占位，明确「敬请期待」，不伪造授权） |
| [WB-029](WB-029-plan-add-to-input-as-ref-chip.md) | ✅ | P2 | ui | 计划 · 「添加到输入框」应作为独立引用 chip 显示，而非混入正文 |
| [WB-030](WB-030-agent-work-item-status-tools.md) | ✅ | P2 | backend | 计划 · 计划项作为可执行任务，agent 能查看并回写其状态 |
| [WB-031](WB-031-live-work-item-sse-sync.md) | ✅ | P3 | frontend | 计划 · agent 改状态时实时回写看板（SSE 事件），而非仅返回刷新 |
| [WB-032](WB-032-sidebar-task-list-no-scroll.md) | ✅ | P2 | ui | 侧栏「任务/空间」列表会话多时不滚动，超出部分被挤压/裁掉 |
| [WB-033](WB-033-automation-runnow-stuck-running.md) | ✅ | P2 | frontend | 「立即运行」自动化后状态永久卡在「运行中」（前端只刷新一次、无轮询） |
| [WB-034](WB-034-automation-view-live-poll.md) | ✅ | P3 | frontend | 自动化看板不反映「到点自动触发」的运行（视图级自适应轮询） |
| [WB-035](WB-035-automation-run-sessions-unreachable.md) | ✅ | P2 | frontend | 自动化产出的会话除「上次运行」外全部不可达（无运行历史入口） |
| [WB-036](WB-036-automation-editor-shell-workspace-model.md) | ✅ | P2 | frontend | 自动化编辑器向目标设计对齐（一期）：全屏编辑器骨架 + 工作空间绑定 + 模型选择 |
| [WB-037](WB-037-automation-unbind-workspace-silent-noop.md) | ✅ | P3 | frontend | 编辑自动化时「解绑工作空间」静默失败（UI 已清空 + 提示已保存，实际仍绑定） |
| [WB-038](WB-038-automation-edit-pins-default-model.md) | ✅ | P3 | frontend | 编辑 model=null（跟随默认）的自动化时，保存会把它悄悄钉死到某个模型 |
| [WB-039](WB-039-automation-editor-runs-panel-not-live.md) | ✅ | P3 | frontend | 自动化编辑器右侧「运行历史」侧栏点「立即运行」后不刷新 |
| [WB-040](WB-040-automation-run-now-no-inflight-dedup.md) | ✅ | P3 | backend | 「立即运行」不与在飞的运行去重，连点/与到点触发并发会重复跑同一自动化 |
| [WB-041](WB-041-sidebar-automation-runs-group.md) | ✅ | P2 | frontend | 自动化产出的会话在侧栏不可见——加独立「自动化」分组 |
| [WB-042](WB-042-more-menu-detached-position.md) | ✅ | P2 | ui | 侧栏「更多」弹出菜单位置脱离按钮（固定 bottom:118px，飘到右下角） |
| [WB-043](WB-043-automation-run-records-tab.md) | ✅ | P2 | frontend | 自动化「运行记录」tab —— 逐次运行状态/摘要持久化 + 跨自动化运行列表 + 详情弹窗 |
| [WB-044](WB-044-automation-view-restructure-tabs-list-templates.md) | ✅ | P2 | frontend | 自动化视图重构：定时任务/运行记录 tab + 工具条 + 紧凑列表 + 从模版添加独立页 |
| [WB-045](WB-045-bound-automation-runs-belong-to-space.md) | ✅ | P3 | frontend | 绑定了工作空间的自动化，其运行会话应归入该「空间」而非「自动化」分组 |
| [WB-046](WB-046-file-endpoints-missing-auth-token.md) | ✅ | P1 | frontend | 登录用户上传/下载文件不带 Bearer token（uploadFile 原生 fetch / downloadUrl 明文 URL 绕过鉴权） |
| [WB-047](WB-047-plan-exec-activity-feed-uninformative-title.md) | ✅ | P2 | frontend | 「动态」tab 中执行计划项的记录只显示随手指令（如「执行它」），看不出执行的是哪个计划项 |
| [WB-048](WB-048-experts-hub-browse-interactions.md) | ✅ | P2 | frontend | 专家/专家团页交互落地（专家团切换 + 分类过滤 + 详情弹窗 + 召唤进会话） |
| [WB-049](WB-049-my-experts-custom-expert-fullstack.md) | ✅ | P2 | backend | 我的专家 —— 自定义专家全栈（后端持久化 + 人格注入 + 前端创建/列表/召唤） |
| [WB-050](WB-050-chat-foreign-project-access-not-gated.md) | ✅ | P2 | backend | 非成员可把 /chat 指向他人项目（新建会话分支未校验 project 访问权，run 在该项目沙箱内执行） |
| [WB-051](WB-051-telegram-connector.md) | ✅ | P2 | backend | 新增 Telegram 连接器（内置 MCP server，Bot API 收发消息） |
| [WB-052](WB-052-kdocs-connector-fullstack.md) | ✅ | P2 | backend | 金山文档连接器全栈落地（后端 kdocs-cli 桥接 MCP + 前端连接器详情弹窗/接入 loadout） |
| [WB-053](WB-053-shared-worktree-commit-discipline.md) | ⬜ | P3 | misc | 共享工作区提交纪律 —— 并发会话下别整文件 git add，按 hunk 暂存 |
| [WB-054](WB-054-skillhub-skills-page.md) | ✅ | P2 | frontend | SkillHub 技能页落地（精选/商店网格+下载星标/分类过滤/安装·关闭·编辑·卸载） |
| [WB-055](WB-055-skillhub-install-backend.md) | ✅ | P2 | backend | SkillHub 已安装技能落到后端 + 会话真正挂载（真实安装/发现/注入） |
| [WB-056](WB-056-skill-detail-view.md) | ✅ | P2 | frontend | 技能详情页（渲染 SKILL.md + 预览/源码 + 去试试/启用/打开文件夹/卸载） |
| [WB-057](WB-057-skill-detail-preview-before-install.md) | ✅ | P2 | backend | 技能详情支持"安装前预览"（从 SkillHub 拉取，而非仅本地磁盘） |
| [WB-058](WB-058-hub-control-plane-epic.md) | ✅ | P1 | backend | WorkBuddy Hub —— local-first 执行 + 云端控制平面重构（总纲/epic） |
| [WB-059](WB-059-catalog-definitions-to-db.md) | ✅ | P2 | backend | 目录「真定义」入库 —— 内置专家人格 + 连接器启动注册表 从硬编码迁到 DB |
| [WB-060](WB-060-catalog-showcase-to-db.md) | ✅ | P2 | frontend | 橱窗目录入库 —— catalog.ts 静态商品卡迁到 DB + API，前端改从接口取 |
| [WB-061](WB-061-hub-service-skeleton.md) | ✅ | P1 | backend | Hub 服务骨架 —— 独立中心服务：账号/组织/项目/成员/邀请权威源 + 鉴权签发 |
| [WB-062](WB-062-local-hub-sync-protocol.md) | ✅ | P1 | backend | 本地 ⇄ Hub 同步协议 —— 下行拉取(身份/项目/成员/目录) + 上行 outbox 回传(执行产出) |
| [WB-063](WB-063-hub-migration-and-local-fallback.md) | ✅ | P2 | backend | 迁移与 local-first 回退 —— 存量导入 Hub、目录权威切 Hub 下发、离线/未登录回退 |
| [WB-065](WB-065-deeper-collab-comments-mentions-presence.md) | ✅ | P2 | backend | 更深协作 —— 评论 / @提及 / 在线状态（分层：v1 REST+轮询，实时作增强） |
| [WB-066](WB-066-hub-catalog-admin-downlink.md) | ✅ | P2 | backend | Hub 目录运营 Admin + 下发覆盖 —— 激活已预埋的 catalog capability |
| [WB-067](WB-067-app-frontend-hub-surface.md) | ✅ | P2 | frontend | App 前端接 Hub —— 协作面板(评论/在线/通知) + 连接/导入入口（SkillHub 目录已由 WB-070 接） |
| [WB-068](WB-068-hub-web-console.md) | ✅ | P2 | backend | Hub web 管理控制台 —— Hub 自带的 web UI（账号/项目/成员/邀请/目录 Admin/通知） |
| [WB-069](WB-069-hub-skillhub-catalog-sync.md) | ✅ | P2 | backend | Hub 定时镜像 SkillHub 目录（按分类）+ Hub 统一查询代理（复用 CLI；榜单∪去重；本地降级兜底） |
| [WB-070](WB-070-frontend-hub-skillhub-catalog.md) | ✅ | P2 | frontend | 前端接入 Hub SkillHub 镜像目录 + 搜索代理（触发下行 pull + catalogStore 承载 skill 类 + ExpertsView 改读 + 搜索接线） |
| [WB-071](WB-071-local-skill-browse-real-fallback.md) | ✅ | P2 | frontend | 未接 Hub 时技能浏览用真实 rankings 兜底，替掉静态假数据（铁律#1；仅 api.ts + catalogStore.ts） |
| [WB-072](WB-072-telegram-assistant-channel.md) | ✅ | P2 | backend | 助理外部渠道（一）—— Telegram 长轮询桥接：收发消息驱动真实 agent（白名单+/start 配对，默认关） |

## 来源

本批 issue 来自 2026-07-06 的一次三路并行代码审查（前端逻辑 / 后端逻辑 / UI·CSS）
+ 浏览器实测复查。🆕 标记为近期改动（＋菜单 loadout、⌘F 搜索、响应式抽屉）引入；
其余为原型迁移遗留或既有实现。

WB-058～063 来自 2026-07-07 的架构讨论：把「能力定义入库」与「多用户协作管理平台」
两项诉求整合为 **WorkBuddy Hub（local-first 执行 + 云端控制平面）** 重构。总设计见
[`docs/workbuddy-hub-架构设计.md`](../workbuddy-hub-架构设计.md)，WB-058 为总纲、WB-059～063 为分阶段子任务。
