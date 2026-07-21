# AgentMate Issues 登记册

本目录是项目的问题登记与处理台账。**所有发现的问题先登记为一条 issue，再处理**。
处理流程与规范由 skill `issue-tracker` 定义（`.agents/skills/issue-tracker/SKILL.md`），
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
| [WB-023](WB-023-low-severity-tail.md) | ✅ | P3 | misc | 低危备忘集合（13 项，已完成审计） |
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
| [WB-053](WB-053-shared-worktree-commit-discipline.md) | ✅ | P3 | misc | 共享工作区提交纪律 —— 并发会话下别整文件 git add，按 hunk 暂存 |
| [WB-054](WB-054-skillhub-skills-page.md) | ✅ | P2 | frontend | SkillHub 技能页落地（精选/商店网格+下载星标/分类过滤/安装·关闭·编辑·卸载） |
| [WB-055](WB-055-skillhub-install-backend.md) | ✅ | P2 | backend | SkillHub 已安装技能落到后端 + 会话真正挂载（真实安装/发现/注入） |
| [WB-056](WB-056-skill-detail-view.md) | ✅ | P2 | frontend | 技能详情页（渲染 SKILL.md + 预览/源码 + 去试试/启用/打开文件夹/卸载） |
| [WB-057](WB-057-skill-detail-preview-before-install.md) | ✅ | P2 | backend | 技能详情支持"安装前预览"（从 SkillHub 拉取，而非仅本地磁盘） |
| [WB-058](WB-058-hub-control-plane-epic.md) | ✅ | P1 | backend | AgentMate Server —— local-first 执行 + 云端控制平面重构（总纲/epic） |
| [WB-059](WB-059-catalog-definitions-to-db.md) | ✅ | P2 | backend | 目录「真定义」入库 —— 内置专家人格 + 连接器启动注册表 从硬编码迁到 DB |
| [WB-060](WB-060-catalog-showcase-to-db.md) | ✅ | P2 | frontend | 橱窗目录入库 —— catalog.ts 静态商品卡迁到 DB + API，前端改从接口取 |
| [WB-061](WB-061-hub-service-skeleton.md) | ✅ | P1 | backend | Server 服务骨架 —— 独立中心服务：账号/组织/项目/成员/邀请权威源 + 鉴权签发 |
| [WB-062](WB-062-local-hub-sync-protocol.md) | ✅ | P1 | backend | 本地 ⇄ Server 同步协议 —— 下行拉取(身份/项目/成员/目录) + 上行 outbox 回传(执行产出) |
| [WB-063](WB-063-hub-migration-and-local-fallback.md) | ✅ | P2 | backend | 迁移与 local-first 回退 —— 存量导入 Server、目录权威切 Server 下发、离线/未登录回退 |
| [WB-064](WB-064-skillhub-live-catalog.md) | ✅ | P2 | backend | SkillHub 浏览列表使用真实 rankings/search；Server 镜像与本机实时来源分层，移除静态假统计 |
| [WB-065](WB-065-deeper-collab-comments-mentions-presence.md) | ✅ | P2 | backend | 更深协作 —— 评论 / @提及 / 在线状态（分层：v1 REST+轮询，实时作增强） |
| [WB-066](WB-066-hub-catalog-admin-downlink.md) | ✅ | P2 | backend | Server 目录运营 Admin + 下发覆盖 —— 激活已预埋的 catalog capability |
| [WB-067](WB-067-app-frontend-hub-surface.md) | ✅ | P2 | frontend | App 前端接 Server —— 协作面板(评论/在线/通知) + 连接/导入入口（SkillHub 目录已由 WB-070 接） |
| [WB-068](WB-068-hub-web-console.md) | ✅ | P2 | backend | Server web 管理控制台 —— Server 自带的 web UI（账号/项目/成员/邀请/目录 Admin/通知） |
| [WB-069](WB-069-hub-skillhub-catalog-sync.md) | ✅ | P2 | backend | Server 定时镜像 SkillHub 目录（按分类）+ Server 统一查询代理（复用 CLI；榜单∪去重；本地降级兜底） |
| [WB-070](WB-070-frontend-hub-skillhub-catalog.md) | ✅ | P2 | frontend | 前端接入 Server SkillHub 镜像目录 + 搜索代理（触发下行 pull + catalogStore 承载 skill 类 + ExpertsView 改读 + 搜索接线） |
| [WB-071](WB-071-local-skill-browse-real-fallback.md) | ✅ | P2 | frontend | 未接 Server 时技能浏览用真实 rankings 兜底，替掉静态假数据（铁律#1；仅 api.ts + catalogStore.ts） |
| [WB-072](WB-072-telegram-assistant-channel.md) | ✅ | P2 | backend | 助理外部渠道（一）—— Telegram 长轮询桥接：收发消息驱动真实 agent（白名单+/start 配对，默认关） |
| [WB-073](WB-073-hub-status-linked-ignores-token.md) | ✅ | P1 | backend | /api/server/status 的 linked 判定忽略当前 Server token，登录后讨论 UI 不解锁（WB-067 真机 E2E 发现） |
| [WB-074](WB-074-presence-never-seen-epoch.md) | ✅ | P3 | frontend | 讨论面板在线状态：从未上线的成员显示「最后活跃 20641 天前」（WB-067 真机 E2E 发现） |
| [WB-075](WB-075-linked-hub-modal-unreachable.md) | ✅ | P2 | frontend | 已连接 Server 后无入口打开连接弹窗，导入/通知/断开成死代码 —— 加「管理」入口（WB-067 真机 E2E 发现） |
| [WB-076](WB-076-global-hub-connect-entry.md) | ✅ | P2 | frontend | 连接 Server 入口只在项目讨论面板内，零项目新用户无法首次连接 —— 账号菜单加全局入口（WB-067 复盘） |
| [WB-077](WB-077-assistant-settings-panel.md) | ✅ | P2 | frontend | 助理设置面板 —— 齿轮点开的真配置（名字/人格/模型/开关/绑定/token 存 DB，write-only 不回传前端） |
| [WB-078](WB-078-buddywebmgr-epic.md) | ✅ | P1 | frontend | BuddyWebMgr —— Server 控制台升级为完整 Web 管理门户（总纲/epic；六子任务全落地，设计见 docs/agentmate-console-管理门户设计.md） |
| [WB-079](WB-079-buddywebmgr-rename-nav.md) | ✅ | P2 | frontend | BuddyWebMgr 品牌更名 + 导航重构（门户骨架；仅 Web 品牌层，不动 server/·AGENTMATE_SERVER_URL 内部标识） |
| [WB-080](WB-080-portal-project-config.md) | ✅ | P2 | frontend | 门户项目管理面 —— 配置编辑（指令 + 连接器/专家/技能 picker，读目录、写 PATCH /projects） |
| [WB-081](WB-081-hub-work-items-sync.md) | ✅ | P2 | fullstack | 团队计划/任务 —— Server work_items 模型 + 路由 + 门户看板（本地⇄Server 同步拆二期 WB-091） |
| [WB-082](WB-082-catalog-experts-teams-crud.md) | ✅ | P2 | fullstack | 目录运营中心框架 + 专家/专家团 类型化 CRUD（替裸 JSON，客户端 pull 下发；后端加 ?all=true 含停用项） |
| [WB-083](WB-083-catalog-connectors-crud.md) | ✅ | P2 | frontend | 目录运营中心 —— 连接器 类型化 CRUD（launch spec 编辑器：内置/stdio；secret_env 仅变量名） |
| [WB-084](WB-084-catalog-skills-skillhub.md) | ✅ | P2 | fullstack | 目录运营中心 —— 技能 + SkillHub（浏览/搜索/上架/手动同步；接已就绪的 WB-069 后端） |
| [WB-085](WB-085-assistant-page-toolbar-real.md) | ✅ | P2 | frontend | 助理页顶栏按钮接真实 transcript —— 对话内搜索/分享导出/历史提问（去掉 toast 占位，复用 ChatView） |
| [WB-086](WB-086-multi-assistant-multi-channel-epic.md) | ✅ | P1 | fullstack | 多助理·多渠道 —— 助理子系统重构（总纲/epic；设计见 docs/agentmate-助理-架构设计.md；S1-087/S2-088/S3+S4-089） |
| [WB-087](WB-087-multi-assistant-backend-model.md) | ✅ | P1 | backend | 多助理 S1 —— 后端模型(assistants/channels) + CRUD + 多 bot 渠道管理器 + run_chat 接 workspace/mode + 迁移 |
| [WB-088](WB-088-multi-assistant-frontend.md) | ✅ | P1 | frontend | 多助理 S2 —— 前端多助理管理 UI（主从：列表/新建/设置/对话/渠道；合并 S3 前端） |
| [WB-089](WB-089-multi-assistant-consolidate.md) | ✅ | P1 | fullstack | 多助理 S3+S4 收尾 —— 移除兼容层 + 端到端验证 + 关闭 epic WB-086 |
| [WB-091](WB-091-local-hub-work-items-sync.md) | ✅ | P3 | backend | 本地 App ⇄ Server work_items 双向同步（WB-081 二期；server-origin 项目 work-items 读代理+镜像/写代理，前端零改，离线兜底） |
| [WB-092](WB-092-skillhub-tab-parity.md) | ✅ | P3 | frontend | BuddyWebMgr SkillHub 页向真站对齐（左筛选：发布来源/排序/场景 + 富卡片图标/来源/★/⬇；api-key 与飙升排序无数据诚实不做） |
| [WB-093](WB-093-assistant-token-visible-env-cleanup.md) | ✅ | P2 | fullstack | 助理渠道 token 本机可见（撤销 write-only）+ 移除 .env Telegram 配置 + 铁律#4 同步（用户显式决定，local-first） |
| [WB-094](WB-094-skillhub-cli-to-http.md) | ✅ | P3 | backend | SkillHub 取数 CLI→直连 HTTP（showcase/search 公开无需 key；拿到 created_at 补「最近上新」；企业 key 可选拉私有 registry） |
| [WB-095](WB-095-skillhub-api-key-setting.md) | ✅ | P3 | fullstack | BuddyWebMgr 设置页保存 SkillHub API key（Server 服务端存储/打码回显/注入取数；skh_ 个人·sk-ent- 企业） |
| [WB-096](WB-096-email-channel.md) | ✅ | P2 | fullstack | 助理邮件渠道 —— IMAP 收 + SMTP 发（多渠道新类型，白名单+暗号，接入多助理，复用 ChannelManager） |
| [WB-097](WB-097-channel-typemenu-clipped.md) | ✅ | P2 | ui | 助理「新增渠道」类型菜单被滚动容器裁切 —— 改用 Popover（fixed 定位不裁切，复用 .pop-item） |
| [WB-098](WB-098-email-self-reply-loop.md) | ✅ | P1 | backend | 邮件渠道自我回复循环 —— 回信打 X-AgentMate-Assistant 头，收信跳过自己回信（防邮件风暴） |
| [WB-099](WB-099-console-grid-overflow.md) | ✅ | P3 | ui | BuddyWebMgr SkillHub 页横向溢出 —— grid 1fr→minmax(0,1fr)（SkillHub/看板/grid2 同修） |
| [WB-100](WB-100-console-experts-showroom.md) | ✅ | P2 | frontend | BuddyWebMgr 专家/专家团升级为 App 同款浏览橱窗（精选场景+子标签+分类+富卡片+详情弹窗；替裸 CRUD，管理动作进弹窗；纯 vanilla 无后端改） |
| [WB-101](WB-101-console-connector-gallery.md) | ✅ | P3 | ui | BuddyWebMgr 连接器补「浏览橱窗」—— 目录管理旁加 App 风格双列卡片橱窗（读同一 CONN_DEFS，cg- 前缀防撞并发） |
| [WB-102](WB-102-console-skill-gallery.md) | ✅ | P2 | frontend | BuddyWebMgr 技能补「浏览橱窗」（整页技能）—— 精选+换一换/推荐·SkillHub·套件/分类/富卡★⬇/详情/搜索，读同一目录数据，sg- 前缀防撞并发 |
| [WB-103](WB-103-professional-pm-epic.md) | ✅ | P1 | fullstack | BuddyWebMgr 专业项目管理 + App 数据打通（总纲/epic）—— 完整 PM(负责人/优先级/截止/标签/子任务/里程碑/活动流/列表·看板·甘特) + 本地⇄Server 打通；子任务 WB-104~108 |
| [WB-104](WB-104-hub-pm-data-model.md) | ✅ | P1 | backend | Server 专业 PM 数据模型 + 迁移 —— work_items 增 priority/due/start/labels/parent_id/milestone_id + 新表 milestones/work_item_activity（非破坏 ALTER，CRUD 扩展） |
| [WB-105](WB-105-hub-pm-api.md) | ✅ | P1 | backend | Server 专业 PM API —— work_items 全字段+子任务+活动流端点 + milestones CRUD 路由；assignee/priority 宽松校验保护同步（TestClient 冒烟 20 项全过） |
| [WB-108](WB-108-app-hub-pm-integration.md) | ✅ | P1 | fullstack | App↔Server 专业 PM 打通 —— 本地模型/迁移/同步扩展新字段+里程碑 + App 工作台任务 UI（优先级/标签/里程碑接卡片·详情·新建）；冒烟 25+12+HTTP E2E 全过、tsc/build 过、明暗双主题 CDP 实截核对过 |
| [WB-106](WB-106-portal-task-professional.md) | ✅ | P1 | frontend | BuddyWebMgr 门户任务专业化 —— 看板卡片富信息(优先级/负责人/截止/标签/里程碑/子任务) + 任务详情抽屉(全字段+子任务+活动流) + 里程碑条；全 pm- 前缀内联样式防撞并发；隔离 Server CDP 实测无报错 |
| [WB-107](WB-107-portal-task-views-filters.md) | ✅ | P2 | frontend | BuddyWebMgr 门户任务 列表视图 + 甘特/时间线视图 + 筛选/排序 —— 视图切换器(看板/列表/甘特) + 搜索/状态/优先级/负责人/里程碑筛选；续 pm- 前缀内联样式，hunk 提交；隔离 Server CDP 三视图实测无报错 |
| [WB-110](WB-110-portal-kanban-drag-activity.md) | ✅ | P2 | frontend | BuddyWebMgr 门户 PM 增强 —— 看板拖拽换列(快速改状态,Viewer 不可拖) + 项目级任务活动流面板(消费 WB-105 activity 端点,变更自动刷新)；CDP DragEvent 实测 Server 真变+活动入流 |
| [WB-109](WB-109-app-featured-consume-hub.md) | ✅ | P3 | frontend | App 精选技能区消费 Server SKILLHUB_FEATURED —— 打通 mgr「加入精选」→ App（渲染真图标，回退静态兜底；纯前端，数据链路 E2E 实测） |
| [WB-123](WB-123-app-kanban-enhancements.md) | ✅ | P2 | frontend | App 对齐片7 看板增强 —— WIP 上限(超限红)+泳道分组(按负责人/里程碑)+保存视图(per-project localStorage，抽 renderKanban 复用；对齐 Console WB-113) |
| [WB-122](WB-122-app-task-templates.md) | ✅ | P2 | frontend | App 对齐片6 任务模板 —— 详情「存为模板」+ 看板「从模板」新建(per-project localStorage，对齐 Console WB-114) |
| [WB-121](WB-121-app-gantt-view.md) | ✅ | P2 | frontend | App 对齐片5 甘特视图 —— 项目页加「甘特」tab(相对时间横条+今天线+月度刻度+优先级色条，对齐 Console pmViewGantt) |
| [WB-120](WB-120-app-tasklist-inline.md) | ✅ | P2 | frontend | App 对齐片4 任务列表增强 —— TaskList 行内状态/优先级改可内联编辑 pill(复用 StatusPill/PriorityPill) + 负责人头像 |
| [WB-119](WB-119-app-workload-view.md) | ✅ | P2 | frontend | App 对齐片3 工作量视图 —— 项目页加「负载」tab(按负责人聚合状态分布+完成率+逾期+工时Σ，对齐 Console pmViewWorkload) |
| [WB-118](WB-118-app-task-comments.md) | ✅ | P2 | fullstack | App 对齐片2 任务级评论 —— App 后端代理 Server 任务评论端点 + 任务详情评论区（复用 WB-115 Server 端点，仅 server-origin 可用） |
| [WB-117](WB-117-app-pm-alignment.md) | ✅ | P2 | fullstack | App 端项目管理对齐 Console（epic，七片全 done）—— 工时全链路 + 任务评论 + 工作量/甘特视图 + 列表内联 + 任务模板 + 看板 WIP/泳道/保存视图；App 工作台 tab 动态/计划/任务/负载/甘特/资产/讨论 与 Console 能力对齐 |
| [WB-116](WB-116-pm-effort-hours.md) | ✅ | P2 | fullstack | PM 细化之四 计划与度量(片1) 工时预估与投入 —— Server work_items 加 estimate_h/spent_h + 控制台抽屉工时输入 + 工作量/概览汇总（Console 侧） |
| [WB-115](WB-115-pm-workload-task-comments.md) | ✅ | P2 | fullstack | PM 细化之三 协作联动 —— 按负责人工作量视图(前端聚合) + 任务级评论(Server comments 加 work_item_id + 任务级端点 + 控制台抽屉评论区) |
| [WB-114](WB-114-pm-task-templates-inline-edit.md) | ✅ | P2 | frontend | PM 细化之二（纯前端）任务模板 + 列表内联编辑(状态/优先级/负责人/里程碑点选即改) + 子任务进度条；依赖/自定义字段/附件需后端另设计 |
| [WB-113](WB-113-pm-board-view-enhancements.md) | ✅ | P2 | frontend | PM 细化之一 看板/视图增强 —— 泳道分组(按负责人/里程碑) + 列 WIP 上限(超限标红·localStorage) + 保存的筛选视图 + 列表批量操作(改状态/负责人/里程碑/删除)；纯前端 console，续 pm- 前缀 |
| [WB-112](WB-112-manager-positioning-data-spec.md) | 🟡 | P1 | fullstack | AgentMate Manager（Console 管理端）定位 epic —— a/b/c 已核实；d 动态回读与 e `id+updated_at` 冲突安全镜像已完成；f 已交付任务模板等连续切片，自定义字段、依赖/关键路径、Sprint/燃尽、PM 导出仍待做，保持 in-progress |
| [WB-111](WB-111-portal-pm-workspace-redesign.md) | ✅ | P1 | frontend | BuddyWebMgr 门户项目管理专业化重构 —— 项目详情改标签页工作台(概览/任务/协作/配置) + Linear 风看板/列表/甘特(统计条·进度条·列容器·富卡片·头像·逾期高亮·今天线)；纯前端消费既有 WB-104/105 API，Server :8100 四 tab×三视图 CDP 实测+拖拽真落库，0 报错 |
| [WB-124](WB-124-model-management-custom-models.md) | ✅ | P2 | fullstack | 模型管理 —— 自定义模型全栈（多厂商 base/key、DB 按用户隔离、内置项可隐藏、切换真生效）：底部模型下拉「配置自定义模型」落地 + resolve 按 owner 路由到各厂商 base/key |
| [WB-125](WB-125-merge-skillhub-into-skills-tab.md) | ✅ | P2 | frontend | 目录运营中心「SkillHub」顶层 tab 与「技能」tab 冗余 —— 把顶层 SkillHub 降为「技能」的第三子视图（浏览橱窗｜目录管理｜SkillHub 同步），与「连接器」范式对齐，顶层 5→4 tab（console.html 纯前端） |
| [WB-126](WB-126-skillhub-sync-http-leftover.md) | ✅ | P2 | fullstack | SkillHub 同步 HTTP 化后的收尾 —— 前端手动同步文案仍写死「跑 CLI」（误导，实际直连公开 HTTP、无需 key）；后台定期同步被 `cli_available()` 卡住，无 CLI 环境一次都不启动（hub/web/console.html:1617 + server/main.py:38） |
| [WB-127](WB-127-skillhub-sync-list-no-detail.md) | ✅ | P3 | frontend | 目录运营中心「SkillHub 同步」列表无查看技能详情入口 —— 卡片描述截断且不可点，复用现成 `sgDetail()` 弹窗给列表项加点击详情（纯前端 console.html） |
| [WB-128](WB-128-builtin-provider-channels.md) | ✅ | P2 | fullstack | 模型管理重构 —— 内置改「厂商渠道」（DeepSeek/智谱/MiniMax/Kimi/通义/OpenAI，真实 base+模型，填 key 即用）+ 移除假 Auto/倍率 + resolve 按 @provider 路由(含非标 chat_path) + 自定义作兜底 |
| [WB-129](WB-129-provider-editable-base-live-models.md) | ✅ | P2 | fullstack | 厂商渠道 base_url/请求路径可显示可编辑（按 owner 覆盖预置，resolve 用有效值）+ 「拉取最新」在线列举厂商真实模型（打 `{base}/models`，治模型名过时）；实测真拉到用户 DeepSeek 的 v4-flash/pro |
| [WB-130](WB-130-console-skill-detail-files.md) | ✅ | P3 | fullstack | 技能「文件信息」收敛到 Console —— Server 加单技能预览代理(HTTP 富元数据+CLI SKILL.md) + App 改走 Console 取数(不再直连 SkillHub，本地兜底) + Console 控制台弹窗懒加载渲染 SKILL.md/参考文件/版本来源 |
| [WB-131](WB-131-manager-nav-ia-redesign.md) | ✅ | P2 | frontend | AgentMate Console 导航/IA 专业化重构 —— 扁平混杂菜单改分区侧栏(工作区/目录/系统)+顶栏(组织切换·通知铃铛·账号)+新增概览页+收编 SkillHub/高级JSON、去运营黑话；纯前端 console.html，沿用现有 token（关联 epic WB-112 管理端定位） |
| [WB-132](WB-132-model-capabilities-cost-meta.md) | ✅ | P2 | fullstack | 模型能力/成本元数据（模态/工具/推理 + 每百万token 输入·输出单价 + 上下文，启发式默认可编辑，为 Auto 铺路）+ 接入地址简化为仅 Base URL + 模型管理提到全局菜单入口（账号菜单，uiStore flag） |
| [WB-133](WB-133-drop-hide-restore-unify-delete.md) | ✅ | P3 | frontend | 去掉厂商模型「隐藏/恢复」二层机制，预置/自加统一为一个「删除」（删的不再显示，要用再拉取/手填加回；复用既有端点，前端过滤 hidden） |
| [WB-134](WB-134-curated-model-defaults-tiered-pricing.md) | ✅ | P2 | fullstack | 内置厂商按官方文档建准确「能力+定价」默认表（DeepSeek/智谱，preset 优先于名字启发式）+ 定价 schema 加缓存命中价/币种 + 更新过时 seed（DeepSeek→v4-flash/pro、智谱现役 GLM）；model_meta ALTER 迁移，reset 回 preset |
| [WB-135](WB-135-glm-official-pricing.md) | ✅ | P2 | backend | 补齐智谱 GLM 官方定价（文本+视觉，人民币/基础档+note 标分档/缓存命中价）+ seed 对齐现役旗舰(glm-5.2/4.7/4.5-air/4.6v) + 视觉补 image/video 能力；只收 chat 模型（生成/语音/向量/重排非 chat、按次计费，如实不纳入） |
| [WB-136](WB-136-ui-default-model-not-env.md) | ✅ | P2 | fullstack | 「默认模型」改为在「配置模型」里选择、按 owner 存 DB，彻底不读 .env：backstop 名字/运行时空选择解析都改走 DB 默认，无默认则诚实报错；新增 `PUT /api/models/default` + 配 key 时自动设默认；前端加「设为默认」+ 去掉 App.tsx 首屏回填 |
| [WB-137](WB-137-home-ctray-stub-buttons.md) | ✅ | P2 | frontend | 首页「选择工作空间/默认权限」两个 tray 按钮是 toast 桩：接 projectStore(startProject) 做真空间选择 + 复用 PermPopover 设默认权限 |
| [WB-138](WB-138-model-mgmt-to-left-menu.md) | ✅ | P2 | frontend | 模型管理入口从输入框模型下拉的「配置模型」移到左侧「更多」菜单（+移除账号菜单重复入口、runtime.py 报错文案改「模型管理」）；ModelPicker 只做选模型，空态文案改指向「更多·模型管理」 |
| [WB-139](WB-139-local-voice-input-asr.md) | ✅ | P2 | fullstack | 语音输入落地 —— 本地 ASR 小模型（faster-whisper base），按住说话松开转写：后端 /api/asr（懒加载单例·PyAV 直解 webm·依赖未装诚实 503）+ 前端 Composer 麦克风真录音（pointer 按住·红点脉冲·转写态·权限兜底）+ api.transcribeAudio；音频不出本机 |
| [WB-140](WB-140-kdocs-sidebar-panel.md) | ✅ | P2 | fullstack | 侧栏「更多 → 金山文档」从 toast 桩变真面板：后端 GET /api/connectors/kdocs/files（最近/搜索云文档，归一化 items、诚实降级）+ 前端 KdocsView（连接态引导·搜索·点开跳转 kdocs.cn，复用既有 class）；复用 WB-052 已打通的 kdocs 连接器/OAuth |
| [WB-141](WB-141-glm-knowledge-base-rag-epic.md) | ✅ | P1 | fullstack | GLM 知识库 RAG 接入（总纲/epic）—— 本地 backend 执行(建库/传档/文档管理/文本+全模态检索/上下文增强，key 只存本地) + 检索接进 agent 工具循环 + Console 目录橱窗管理下发；子任务 WB-142~145 全落地实测 |
| [WB-142](WB-142-glm-kb-backend-engine.md) | ✅ | P1 | backend | GLM 知识库 Phase A —— 本地 backend 真·知识库引擎 glm_kb.py(httpx) + routers/knowledge.py(建库/传档/文档管理/检索/全模态/用量)，key 走 db.get_provider_key(owner,zhipu)；真机建库→传档→向量化→检索全通 |
| [WB-143](WB-143-glm-kb-agent-retrieve-tool.md) | ✅ | P1 | backend | GLM 知识库 Phase B —— knowledge_retrieve 工具接进 agent 工具循环(照抄 set_work_context contextvar) + ChatBody.knowledge_ids loadout 透传；SSE 真出 knowledge_retrieve 事件+引用来源作答 |
| [WB-144](WB-144-glm-kb-app-frontend.md) | ✅ | P1 | frontend | GLM 知识库 Phase C —— App 前端 KnowledgeView(建库/传档/进度/用量/模板) + knowledgeStore + Composer loadout 选择器 + Sidebar 入口；CDP 实截渲染真 GLM 用量+模板 |
| [WB-145](WB-145-glm-kb-manager-console.md) | ✅ | P2 | frontend | GLM 知识库 Phase D —— Console console 知识库橱窗+目录管理(kb- 前缀，仿 WB-101) + catalog_items 新 category KB_TPLS 下发(零 schema 改动)；隔离 Server CDP 实截 CRUD+橱窗 |
| [WB-146](WB-146-settings-center-shell.md) | ✅ | P1 | frontend | 统一「设置中心」弹窗 —— 双栏外壳 + 迁移已有标签(模型/助理设置/外观·个性化) + 其余标签诚实占位「即将上线」；账号浮层加入口 |
| [WB-147](WB-147-personalization-backend.md) | ✅ | P1 | fullstack | 个性化真后端 —— 回复风格预设 + 自定义指令(按 owner 存 KV，注入 agent 系统提示真生效) + /api/settings 路由；系统设置里需前端基建的项(语言/字号/欢迎语)不做以免假开关 |
| [WB-148](WB-148-memory-backend.md) | ✅ | P1 | fullstack | 记忆真后端 —— user_memories 表 + 注入 agent 系统提示(真生效) + 开启后从对话自动抽取(一次性 LLM，去重入库，默认关) + 手动增删清 + 前端记忆 tab |
| [WB-149](WB-149-data-management-backend.md) | ✅ | P2 | fullstack | 数据管理真后端 —— 数据导出(真 dump user+settings+memories+sessions) + 清空个人对话(真删 kind=chat·级联消息·二次确认) + /api/data 路由；删除保护等策略项诚实占位 |
| [WB-150](WB-150-agent-settings-backend.md) | ✅ | P2 | fullstack | 智能体设置真后端 —— 工具步数上限 + 回复发散度(temperature)，按 owner 存 KV 且 run_chat 真读真用(暗号读取实验证明步数上限 govern 循环) + /api/settings/agent |
| [WB-151](WB-151-glm-kb-review-fixes.md) | ✅ | P2 | fullstack | GLM 知识库 WB-141 审查修复 —— 向量化轮询闭包 bug(interval 用 openId state 恒 null→用 id 参数) + 无扩展名文件误拒 + 上传先查 key 再缓冲 body + _unwrap 2xx 空 body 当成功 + capacity 形状守卫；真机验 M2 三态 |
| [WB-152](WB-152-security-center-backend.md) | ✅ | P2 | fullstack | 安全中心真后端 —— 命令安全策略(黑名单·真拦截 run_command) + 审计日志(真记录执行/拦截，audit_log 表) + /api/security；文件/网络域名/数据网关诚实占位 |
| [WB-153](WB-153-shared-backend-project-access-control.md) | ✅ | P0 | backend | 共享后端多用户隔离漏洞 —— 会话可绑他人项目、Viewer 可执行/写、/stop·/answer 无 owner 校验 |
| [WB-154](WB-154-inproc-connector-sandbox-leak.md) | ✅ | P1 | backend | 内置连接器经 os.environ 传 workspace 目录 —— 并发 run 串项目沙箱 |
| [WB-155](WB-155-assistant-shared-session-cross-user-reply.md) | ✅ | P1 | backend | 助理多渠道共享 session —— 并发 run 交错 + before 快照把他人回复当自己的返回（跨用户串信） |
| [WB-156](WB-156-hub-invite-reuse-and-viewer-writes.md) | ✅ | P1 | backend | Server 访问控制 —— 邀请码可无限重用/永不失效 + Viewer 越权（timeline 上报 / org 建项目） |
| [WB-157](WB-157-hub-pm-referential-integrity.md) | ✅ | P2 | backend | Server PM 引用完整性 —— parent_id/milestone_id 跨项目未校验 + 级联删除/清空无 project 过滤 |
| [WB-158](WB-158-hub-origin-offline-write-data-loss.md) | ✅ | P2 | backend | server-origin 项目离线新建 work_item/milestone 被下次镜像删除（数据丢失） |
| [WB-159](WB-159-frontend-store-robustness.md) | ✅ | P2 | frontend | 前端 store 健壮性 —— 看板乐观更新不回滚 / answer 失败挂起 agent / send finally 无流守卫 / connect 不 reload |
| [WB-160](WB-160-backend-hardening-tail.md) | 🟡 | P2 | backend | 后端加固尾集 —— 6 项代码均已落地；邮件 PEEK/精确 Seen/重启去重待真实 IMAP+SMTP 验收 |
| [WB-161](WB-161-authoritative-docs-correction.md) | ✅ | P2 | misc | 权威现状文档纠偏 —— CLAUDE.md/README/实现方案 对 Server/auth/LLM key/CSS/Tauri 的错误陈述 |
| [WB-162](WB-162-memory-mechanism-optimization.md) | ✅ | P2 | fullstack | 记忆机制优化 —— 注入预算化(优先手动+最近·超预算截断) + 结构化抽取(add/update 合并·更替过时矛盾) + 抽取输入预算 + 手动编辑一条(PUT+内联编辑 UI) |
| [WB-163](WB-163-manager-user-management.md) | ✅ | P1 | backend | Console 用户管理 —— 平台账号 admin CRUD(列表/建/改人格套餐管理员/重置密码/删，含删自己·最后管理员·有项目守卫) + console「用户」页(um- 前缀) |
| [WB-164](WB-164-app-login-via-manager.md) | ✅ | P1 | backend | App 登录经 Console 验证 + 两端打通 —— Console 权威(ok 用 Server token 镜像) + 离线兜底(login 回退本地/register 诚实 503) + server_login_ex 判别式；未接 Server 零变化 |
| [WB-165](WB-165-cognitive-memory-epic.md) | ✅ | P2 | fullstack | 认知记忆机制移植(参考 AgentOS·epic) —— 强度/衰减/使用强化 + 本地语义检索 + 白盒管理（WB-166~168 三档累加） |
| [WB-166](WB-166-memory-strength-decay-lifecycle.md) | ✅ | P2 | backend | 认知记忆 档一 —— 强度(importance×recency衰减×usage)排序注入+命中强化 + 软状态生命周期(active/superseded/archived 不硬删) + decay_gc（无嵌入） |
| [WB-167](WB-167-memory-local-semantic-retrieval.md) | ✅ | P2 | backend | 认知记忆 档二 —— 本地嵌入(fastembed bge-small-zh·可选依赖懒加载) + 语义去重/自动更替 + 按当前对话相关性 top-K 注入 |
| [WB-168](WB-168-memory-whitebox-management-ui.md) | ✅ | P2 | fullstack | 认知记忆 档三 —— 白盒管理(API: stats/search/importance/archive/rollback/trace/decaying + 设置·记忆面板升级) |
| [WB-169](WB-169-console-kb-tpl-dim-slice-dropdowns.md) | ✅ | P2 | frontend | Console 知识库模板编辑器 —— 新增「向量维度」联动下拉(跟随模型·真实生效·不碰铁律#1) + 切片方式改下拉(GLM 真实枚举) + 切片字数仅自定义切片时显示 |
| [WB-170](WB-170-memory-embedding-backend-configurable.md) | ✅ | P2 | fullstack | 记忆嵌入后端可配置 —— 本地(fastembed bge-small-zh) ⇄ 在线(GLM embedding-3) 用户可选 + 跨模型 tag 惰性重嵌入迁移（知识库档位选择 WB-144/169 已就绪，本条只补记忆侧） |
| [WB-171](WB-171-hub-knowledge-base-document-backend.md) | ✅ | P2 | backend | Server 真·知识库 + 文档后端(项目级) —— 建库/传档(字节存 Server)/文档管理 + 有文档后锁向量维度(400 拦截)；Console 不算向量(向量化交执行面，且只调 GLM 嵌入接口、不用 GLM 知识库功能) |
| [WB-172](WB-172-manager-project-knowledge-base-tab.md) | ✅ | P2 | frontend | Console 项目「知识库」tab —— 真·建库(向量维度联动下拉/切片方式下拉)+文档上传/列/删+有文档后维度 select 锁定+诚实未向量化状态(kbm- 前缀)；配 WB-171 |
| [WB-176](WB-176-trim-experts-showcase-data.md) | ✅ | P3 | fullstack | 精简专家/专家团橱窗数据 —— 三层数据源(前端静态兜底/后端种子/运行库)同步裁剪至 专家7·团3·场景3·分类6，避开「删空即重种」与「兜底顶上来」两个复活陷阱 |
| [WB-177](WB-177-connectors-showcase-weknora.md) | ✅ | P3 | fullstack | 连接器橱窗改版 —— 三层同步去掉 ima知识库/乐享知识库/腾讯文档/TAPD/企查查(12→8)，新增 WeKnora知识库 卡 + CONN_META 详情(工具清单逐字镜像后端真 knowledge_retrieve/knowledge_add) |
| [WB-178](WB-178-skills-subsystem-epic.md) | ✅ | P1 | fullstack | 技能子系统重构（总纲/epic）—— 以 slug 为主键焊死「橱窗/loadout/磁盘」三层；WB-179~186 已全部完成并经真实功能门禁验收 |
| [WB-179](WB-179-skill-identity-and-fallback-prompt.md) | ✅ | P1 | fullstack | 技能身份断裂已修：未知技能诚实跳过；即时/项目/助理/Server 全链路存 slug，历史展示名幂等迁移，展示名只在 UI/SSE 边界使用 |
| [WB-180](WB-180-skill-picker-ignores-installed.md) | ✅ | P1 | frontend | ＋菜单技能选择器只读静态 SK_GRID —— 真实已安装的技能在会话里选不到（装机与使用两条路断开）；改为「内置(新增 /skills/builtin，SK_GRID 里藏着 6 个真内置技能差点被砍) + 已装未停用」，静态假卡不再出现；CDP 自驱实测 23 项(12 张真卡/明暗双主题对比度/窄宽/loadout chip 真出) |
| [WB-181](WB-181-skills-page-fake-interactions.md) | ✅ | P1 | frontend | 技能页假交互**清零** —— 推荐段＋号(纯 useState+toast)改按真实身份分派(实测 16 张=内置6/可装3/上游不存在7；内置→挂载+跳 composer 走既有 summon 范式，其余→真安装，装不到诚实报错) + 说谎的「综合评分」排序控件移除 + 「＋添加技能」真聚焦搜索 + 「安装套件」随 WB-182 删除 |
| [WB-182](WB-182-skill-kits-fabricated.md) | ✅ | P2 | fullstack | 「套件」100% 虚构（前端 4 条静态卡·技能数手写、后端零代码、Server 无源、DB 无表、安装按钮只 toast）—— **取「删」**，五层同步移除(catalog.ts/ExpertsView/catalog_showcase.json/db.py 的 SHOWCASE_SKIP/**Console console.html**——WB-102 镜像时连套件一起搬过去了，差点留孤儿 tab)；真做方案留在原处注释，等 WB-183 目录入库后建 kit 表 |
| [WB-183](WB-183-catalog-skills-to-db.md) | ✅ | P2 | fullstack | catalog_skills 成为技能定义/推荐权威源；slug 全链路、Server APP_SKILLS CRUD 下发、同 slug 覆盖、本机离线兜底、孤儿与分类快照清理全部完成 |
| [WB-184](WB-184-skill-browse-sources-convergence.md) | ✅ | P2 | frontend | 推荐与 SkillHub 保留正确职责边界但各自只剩真实数据源；静态假统计/精选/分类快照删除，推荐分类改读 catalog_skills 真 category |
| [WB-185](WB-185-skills-api-attack-surface.md) | ✅ | P2 | backend | /api/skills 攻击面 —— App 侧 install/preview 的 slug 未校验（WB-160 第6项只修了 hub 孪生站点，App 侧漏网）已修+两侧口径统一+顺带硬化前导`-`（实测 CLI argparse 真被 `--dir` 噎住）；零鉴权项 ⏸ deferred（current_user 从不拒绝，需共享后端鉴权策略横切决策） |
| [WB-186](WB-186-skills-backend-consistency-tail.md) | ✅ | P3 | backend | 技能后端一致性尾集（5 项全清）—— rankings 补齐 Console 代理(顺带：Server 走 HTTP 无需 CLI，没装 CLI 的本机终于能拿真实榜单而非静态假数据) + 预览缓存 TTL 对齐 Server + 合冗余分支 + **plan 过滤统一到 Tool.plan_safe(默认 False 保守，_PLAN_TOOLS 降为一致性断言)** + schema 改从已去重的 active_tools 生成；**顺带堵掉真 live bug：kb_tools 同样绕过 plan 过滤，而 knowledge_add 是写——计划模式下 agent 真能改知识库，违反「plan, don't execute」** |
| [WB-187](WB-187-resolve-slug-installs-wrong-skill.md) | ✅ | P2 | backend | 按名安装取搜索首条 —— 名字不存在时静默装上无关技能并贴上用户输入的名字（截图里「腾讯微云」的＋号实测会装成 self-improving-agent，真微云技能在搜索第4条被跳过）；resolve_slug 改仅精确命中，实测 38 张静态卡 37 命中/1 诚实404 |
| [WB-188](WB-188-weknora-config-form.md) | ✅ | P2 | fullstack | WeKnora 连接配置改 UI 表单 —— 从「只能改 .env + 重启」改为按 owner 入库(key 存 provider_keys 只写不回读/url 存 KV)、DB 优先 .env 兜底、连接器弹窗内真表单 + 测试连接 |
| [WB-189](WB-189-project-connectors-picker-cleanup.md) | ✅ | P3 | fullstack | 新建项目的连接器选择器/模板仍留着已下架的连接器 —— NP_CONNS 删 乐享知识库/腾讯文档/TAPD(13→10) + NP_TPLS 清引用；且模板提示词点名「在 TAPD 中跟进…同步到腾讯文档」指挥 agent 用不存在的连接器(铁律#1)；配 WB-177 |
| [WB-190](WB-190-skills-tencent-docs-cleanup.md) | ✅ | P3 | frontend | 技能侧「腾讯文档」清理 —— SK_GRID(17→16,DB 供给三层同步)/SK_RECO(死代码)/SKILLHUB_GRID(不入库,仅静态层) 与连接器侧下架不一致；后端本无该技能定义(零能力卡)；配 WB-177/189；⚠️只清掉「我们自己的目录」那半 —— SkillHub 段是上游商店镜像、不受影响，另见 WB-191 |
| [WB-191](WB-191-skillhub-mirror-no-delisting.md) | ⏸ | P3 | fullstack | SkillHub 上游真镜像的本地下架策略（全局名单或本机过滤）待产品决策；不影响技能安装/运行链路 |
| [WB-192](WB-192-run-command-inherits-secrets.md) | ✅ | P1 | backend | run_command 子进程继承后端全部密钥 —— 模型一句  即可读走并上传给 LLM 厂商；WB-011 只把连接器那条路收成无密钥白名单，run_command 从未收口(WB-014 以「如实标注」结案)；实证子进程读到 LLM_API_KEY(35 字符) |
| [WB-193](WB-193-knowledge-add-url-and-mcp-verdict.md) | ✅ | P3 | backend | knowledge_add 支持 path/url 二选一、WeKnora >=0.2.12 fail-closed、owner REST 凭据与可操作 SSRF 错误；真实 URL/path/SSRF、无 workaround LLM 会话及检索闭环通过；manual 暂不做；继续维持**不接官方 WeKnora MCP server** |

| [WB-194](WB-194-connector-card-add-lost-on-navigate.md) | ✅ | P2 | frontend | 连接器卡「添加到本会话」改走 summon 范式：挂载连接器后直接进入新草稿，避免导航时被会话 reset 清空；目录卡与详情弹窗行为统一 |
| [WB-195](WB-195-reco-category-chips-cannot-filter.md) | ✅ | P3 | frontend | 推荐分类由 catalog_skills.category 动态生成并真实过滤；浏览器验证开发编程 6→2 张，明暗主题与窄屏通过 |

| [WB-196](WB-196-expert-persona-fallback-fake.md) | ✅ | P2 | backend | 专家人格通用兜底已删除；未知专家诚实报告未就绪，只有真实 persona 才注入运行时 |

| [WB-197](WB-197-app-url-routing-theme-audit.md) | ✅ | P1 | frontend | 应用内存态单页导航改为可直达多页路由，并审查明暗主题样式 |
| [WB-198](WB-198-project-knowledge-base-config.md) | ✅ | P1 | fullstack | 项目配置缺少知识库挂载与持久化，项目执行无法自动使用项目知识 |
| [WB-199](WB-199-system-settings-real.md) | ✅ | P1 | fullstack | 系统设置仍是占位页，需要持久化并真实作用于应用 |
| [WB-200](WB-200-httpx-secret-url-logging.md) | ✅ | P1 | backend | 第三方 HTTP 请求日志会把 URL 路径中的连接凭据写入开发日志 |
| [WB-201](WB-201-automation-home-reference-layout.md) | ✅ | P2 | frontend | 自动化主页空态缺少顶部分页，模板与真实创建入口的信息层级不一致 |
| [WB-202](WB-202-app-navigation-settings-menu-groups.md) | ✅ | P2 | ui | 左侧导航与设置中心功能菜单扁平混杂，缺少按使用、配置与治理的语义分组 |
| [WB-203](WB-203-remove-top-text-menus.md) | ✅ | P3 | ui | 顶部自绘菜单栏整行已移除；侧栏恢复改为不占布局高度的边缘入口 |
| [WB-204](WB-204-skill-regression-gate.md) | ✅ | P2 | test | 新增离线身份/Hub覆盖/category 契约门禁与 npm 入口；真 LLM 技能/连接器测试同步改为 slug 并 15/15 通过 |
| [WB-205](WB-205-skills-grid-horizontal-overflow.md) | ✅ | P2 | ui | Skills 页卡片网格改用 minmax(0,1fr)，长技能描述不再撑宽内容区；明暗主题与 1280/960/900/860px 实测无横向滚动 |
| [WB-206](WB-206-add-skill-import-create-flow.md) | ✅ | P1 | fullstack | 添加技能补齐上传导入与对话创建，查找复用顶栏搜索框 |
| [WB-207](WB-207-edit-installed-skill-fake-flow.md) | ✅ | P2 | fullstack | 已安装技能的编辑入口挂载不存在的旧技能且不能保存修改 |
| [WB-208](WB-208-rename-product-agentmate.md) | ✅ | P1 | fullstack | 产品品牌、路径、环境变量与构建标识已全部统一为 AgentMate |
| [WB-209](WB-209-sidecar-missing-numpy.md) | ✅ | P1 | backend | PyInstaller sidecar 缺少 numpy，打包后端无法启动 |
| [WB-210](WB-210-rename-hub-manager-server-console.md) | ✅ | P1 | fullstack | Hub/Manager 全面更名为 Server/Console |
| [WB-211](WB-211-unify-product-version-1-0-0.md) | ✅ | P2 | fullstack | 产品版本在侧栏显示 v5.2.3 且发布配置仍为 0.1.0 |
| [WB-212](WB-212-issue-index-stale-renamed-doc-links.md) | ✅ | P2 | misc | Issue 索引来源段落仍引用更名前的架构文档路径 |
| [WB-213](WB-213-reassign-local-stack-ports-8100-8102.md) | ✅ | P1 | fullstack | 本地三层服务端口统一调整为 8100、8101、8102 |
| [WB-214](WB-214-recommended-skill-skillhub-interaction-parity.md) | ✅ | P2 | fullstack | 推荐技能与 SkillHub 卡片交互不一致，内置技能缺少详情入口 |
| [WB-215](WB-215-local-skillhub-and-installed-only-content.md) | ✅ | P1 | fullstack | SkillHub 错误由 Server 集中管理，未安装技能可读取文件内容 |
| [WB-216](WB-216-recommended-skills-real-install.md) | ✅ | P1 | fullstack | 推荐技能错误按内置免安装处理，与 SkillHub 安装模型不一致 |
| [WB-217](WB-217-server-managed-skill-recommendations.md) | ✅ | P1 | fullstack | 技能定义与推荐位配置耦合，推荐内容无法独立运营 |
| [WB-218](WB-218-console-url-routing.md) | ✅ | P1 | frontend | AgentMate Console 内存态视图改为可直达多页面路由 |
| [WB-219](WB-219-console-skill-editor-files.md) | ✅ | P1 | fullstack | Console 技能编辑缺少弹窗与真实文件管理 |
| [WB-220](WB-220-server-managed-connector-recommendations.md) | ✅ | P1 | fullstack | 连接器定义与推荐位未由 Server 管理且 App 缺少本地运行态映射 |
| [WB-221](WB-221-server-managed-expert-recommendations.md) | ✅ | P1 | fullstack | 专家定义与推荐位未由 Server 管理且 App 缺少本地人格映射 |
| [WB-222](WB-222-console-catalog-editors-modal-consistency.md) | ✅ | P2 | frontend | Console 目录 CRUD 编辑器与列表混排，交互边界不一致 |
| [WB-223](WB-223-console-skill-file-browser-editor.md) | ✅ | P2 | ui | Console 技能文件页缺少文件浏览器与就地编辑器 |
| [WB-224](WB-224-console-allows-uninstallable-skill-definition.md) | ✅ | P1 | fullstack | Console 可保存 App 无法查看和安装的不完整技能定义 |
| [WB-225](WB-225-skill-slug-mutable-breaks-local-references.md) | ✅ | P1 | fullstack | 技能稳定 slug 可改删导致本地引用和安装快照失联 |
| [WB-226](WB-226-server-skill-edit-has-no-installed-update-flow.md) | ✅ | P1 | fullstack | Server 技能编辑后已安装副本没有版本与更新闭环 |
| [WB-227](WB-227-skill-tool-binding-free-text-silent-drop.md) | ✅ | P2 | fullstack | 技能工具绑定为自由文本，未知工具会静默失效 |
| [WB-228](WB-228-skill-editor-missing-destructive-and-dirty-guards.md) | ✅ | P2 | ui | 技能编辑与整项删除缺少防误操作保护 |
| [WB-229](WB-229-skill-list-lacks-search-filter-and-ordering.md) | ✅ | P3 | ui | 技能目录列表缺少搜索筛选与可见排序能力 |
| [WB-230](WB-230-langfuse-agent-observability.md) | ✅ | P2 | backend | Agent 运行缺少 Langfuse 可观测链路 |
| [WB-231](WB-231-expert-teams-stable-runtime-identity.md) | ✅ | P1 | fullstack | 专家团 17 名成员已绑定稳定 expert_slug，Server 校验/下发与 App 真实 persona 执行闭环完成 |
| [WB-232](WB-232-skill-functional-gate-requires-install.md) | ✅ | P1 | test | 技能功能门禁按真实安装模型运行并恢复原状态，15/15 实时回归通过 |
| [WB-233](WB-233-custom-connector-toast-only-entry.md) | ✅ | P2 | frontend | App 已移除只弹 toast 的“自定义连接器”伪入口 |
| [WB-234](WB-234-console-ant-design-migration.md) | ✅ | P1 | frontend | AgentMate Console 技能管理的单文件手写 UI 难以形成专业一致的管理体验 |
| [WB-235](WB-235-capability-release-docs-workbuddy-reference.md) | ✅ | P1 | misc | 能力目录发布升级设计与 WorkBuddy 产品参考缺少统一文档沉淀 |
| [WB-236](WB-236-console-remaining-pages-ant-design.md) | ✅ | P1 | frontend | AgentMate Console 其余 legacy 页面尚未迁移到统一组件体系 |
| [WB-237](WB-237-app-production-build-type-errors.md) | ✅ | P1 | frontend | AgentMate App 生产构建被现有 TypeScript 错误阻断 |
| [WB-238](WB-238-stale-authoritative-docs-cleanup.md) | ✅ | P1 | misc | 权威文档残留过时架构、端口与能力边界，且以勘误掩盖正文冲突 |
| [WB-239](WB-239-task-delivery-roadmap-epic.md) | 🟡 | P1 | fullstack | AgentMate 功能主线尚未围绕可验收任务交付闭环组织（路线图 epic） |
| [WB-240](WB-240-home-task-control-center.md) | ✅ | P1 | frontend | 首页只能发起新任务，无法看到真实执行状态与最近交付（WB-239 R0） |
| [WB-241](WB-241-app-ant-design-migration.md) | ✅ | P1 | frontend | AgentMate App 仍使用手写组件体系，未统一到 Ant Design 6 与 Pro Components |
| [WB-242](WB-242-run-artifact-delivery-kernel.md) | ✅ | P1 | fullstack | Session 执行缺少独立 Run 与可验收 Artifact 交付内核（WB-239 R1） |
| [WB-243](WB-243-office-artifact-tools-golden-gate.md) | ✅ | P1 | backend | 缺少 DOCX/XLSX/PPTX/PDF 专用生成校验工具与黄金任务门禁（WB-239 R1） |
| [WB-244](WB-244-browser-tool-login-state-confirmation.md) | ✅ | P1 | backend | 缺少可复用登录态且提交前强制确认的真实浏览器工具（WB-239 R1） |
| [WB-245](WB-245-skill-immutable-release-snapshot.md) | ✅ | P0 | fullstack | Skill 已安装指令与实时工具绑定可形成混合版本且 Run 缺少不可变快照 |
| [WB-246](WB-246-skill-tombstone-capability-sync.md) | ✅ | P0 | fullstack | Skill 下行缺少 tombstone、客户端能力报告与增量兼容门禁 |
| [WB-247](WB-247-skill-runtime-resources-and-composition.md) | ✅ | P1 | backend | Skill references 与模板运行时不可达且多 Skill 指令缺少总预算和冲突规则 |
| [WB-248](WB-248-skill-permission-and-worker-isolation.md) | ✅ | P1 | backend | Skill 工具权限只有 plan_safe 粗粒度标记且长任务无法可靠取消隔离 |
| [WB-249](WB-249-skill-installation-scope-and-locking.md) | ✅ | P1 | backend | Skill 安装启停为机器全局状态且并发安装卸载缺少事务锁与恢复能力 |
| [WB-250](WB-250-skill-release-console-lifecycle.md) | ✅ | P1 | fullstack | Console Skill 管理仍是可变 CRUD，缺少测试审核灰度撤回和运行指标闭环 |
| [WB-251](WB-251-reliable-automation-delivery-governance.md) | ✅ | P1 | backend | 自动化缺少真实失败判定、持久幂等重试、DLQ、成本上限与结果投递（WB-239 R2） |
| [WB-252](WB-252-assistant-page-height-chain.md) | ✅ | P0 | ui | 助理页被长对话撑高并整体移出视口 |
| [WB-253](WB-253-app-ui-migration-polish.md) | ✅ | P1 | ui | App 组件迁移后残留暗色、布局、侧栏与分类细节问题 |
| [WB-254](WB-254-console-responsive-detail-polish.md) | ✅ | P1 | ui | Console 概览栅格与高级 JSON 窄屏操作不可达 |
| [WB-255](WB-255-work-item-run-artifact-collaboration.md) | ✅ | P1 | fullstack | 项目工作项无法直接发起、跟踪和验收本地 Run 与 Artifact（WB-239 R3） |
| [WB-256](WB-256-antd6-list-deprecation.md) | ✅ | P2 | ui | App 与 Console 仍使用 Ant Design 6 已弃用的 List 组件 |
| [WB-257](WB-257-production-desktop-update-service.md) | ✅ | P1 | fullstack | 桌面更新仍是占位 endpoint，缺少可配置发布服务、灰度回滚和真实入口（WB-239 R4） |
| [WB-258](WB-258-evidence-gated-multi-agent-dag.md) | ✅ | P1 | fullstack | 专家团仍是多 persona 同时注入，缺少独立 Run、DAG、审稿预算和对照评测（WB-239 R5） |
| [WB-259](WB-259-antd-version-gate-drift.md) | ✅ | P2 | frontend | Ant Design 依赖声明与精确版本门禁漂移，完整回归持续失败 |
| [WB-260](WB-260-wbbutton-hover-border-jitter.md) | ✅ | P1 | ui | WbButton 无边框控件悬浮时被 Ant 补边框导致内容抖动 |
| [WB-261](WB-261-app-console-typography-unification.md) | ✅ | P1 | ui | AgentMate App 与 Console 字体体系和基础排版密度不一致 |
| [WB-262](WB-262-antd6-spin-tip-deprecation.md) | ✅ | P2 | frontend | App 与 Console 仍使用 Ant Design 6 已弃用的 Spin tip 属性 |
| [WB-263](WB-263-console-project-workspace-parity.md) | ✅ | P1 | frontend | Console React 迁移后项目工作台缩水并与 App 项目模型失配 |
| [WB-264](WB-264-project-settings-assistants-automations.md) | ✅ | P1 | frontend | 项目配置缺少助手与自动化的真实绑定管理 |
| [WB-265](WB-265-configurable-icon-picker.md) | ✅ | P1 | ui | 多个配置表单仍要求手工输入 Emoji，缺少统一图标选择器 |
| [WB-266](WB-266-unified-managed-built-in-tool-catalog.md) | ✅ | P1 | fullstack | 内置工具目录分裂且仅有四项，缺少数据库权威源与 Console 管理 |
| [WB-267](WB-267-managed-skill-categories.md) | ✅ | P1 | fullstack | Skill 分类是自由文本，缺少独立分类目录与引用治理 |
| [WB-268](WB-268-full-regression-contract-drift.md) | ✅ | P1 | frontend | 全量回归门禁与已落地 Ant 及项目工作台实现漂移，持续集成仍有三项失败 |
| [WB-269](WB-269-settings-center-mobile-overlap.md) | ✅ | P1 | ui | 设置中心在手机宽度仍保持双栏导致内容挤压重叠 |
| [WB-270](WB-270-tauri-webview2loader-missing.md) | ✅ | P0 | misc | GNU Tauri 安装包遗漏 WebView2Loader.dll 导致桌面端无法启动 |
| [WB-271](WB-271-duplicate-attachment-feedback.md) | ✅ | P3 | frontend | 重名附件被静默丢弃却仍提示添加成功 |
| [WB-272](WB-272-plan-ask-mode-conflict.md) | ✅ | P3 | fullstack | Plan 与 Ask 可叠加并产生冲突系统提示 |
| [WB-273](WB-273-plan-connector-transparency.md) | ✅ | P3 | backend | Plan 模式静默忽略已选连接器 |
| [WB-274](WB-274-legacy-model-id-colon.md) | ✅ | P3 | backend | 旧模型选择解析会截断含冒号的真实模型 ID |
| [WB-275](WB-275-files-usage-full-scan.md) | ✅ | P3 | backend | files usage 连续请求每次全量遍历工作区 |
| [WB-276](WB-276-llm-stream-close-on-stop.md) | ✅ | P3 | backend | 停止生成时 LLM HTTP 流未被立即关闭 |
| [WB-277](WB-277-list-messages-missing-return.md) | ✅ | P1 | backend | list_messages 丢失返回体导致全部对话运行失败 |
| [WB-278](WB-278-text-3-contrast-design-contract.md) | 🚫 | P3 | ui | text-3 二级文字对比度低于 WCAG AA（原型保真约束，本轮不改） |
| [WB-279](WB-279-skill-catalog-test-server-gate.md) | ✅ | P2 | test | Skill catalog 同步回归未开启 Server gate |
| [WB-280](WB-280-regression-test-state-isolation.md) | ✅ | P2 | test | 回归测试泄漏 DB 与安全上下文导致顺序相关失败 |
| [WB-281](WB-281-chatsearch-cross-node-match.md) | ✅ | P3 | frontend | ChatSearch 无法匹配跨 Markdown 文本节点短语 |

## 来源

本批 issue 来自 2026-07-06 的一次三路并行代码审查（前端逻辑 / 后端逻辑 / UI·CSS）
+ 浏览器实测复查。🆕 标记为近期改动（＋菜单 loadout、⌘F 搜索、响应式抽屉）引入；
其余为原型迁移遗留或既有实现。

WB-058～063 来自 2026-07-07 的架构讨论：把「能力定义入库」与「多用户协作管理平台」
两项诉求整合为 **AgentMate Server（local-first 执行 + 云端控制平面）** 重构。总设计见
[`docs/agentmate-server-架构设计.md`](../agentmate-server-架构设计.md)，WB-058 为总纲、WB-059～063 为分阶段子任务。

WB-078～084 来自 2026-07-08 用户检查 Server 站点后的诉求：把 Server 控制台升级为完整 Web 管理门户并更名
**BuddyWebMgr**（项目管理面 + 目录运营中心 + SkillHub）。总设计见
[`docs/agentmate-console-管理门户设计.md`](../agentmate-console-管理门户设计.md)，WB-078 为总纲、WB-079～084 为分阶段子任务。

WB-178～186 来自 2026-07-16 用户要求对**技能功能的设计从头审查**（前端 / 后端 / Server 三路梳理 + 逐条源码核实）。
结论：技能是「橱窗」与「真引擎」两套互不相认的系统贴在一起，根因是**技能没有稳定身份**（展示名 / slug / 磁盘目录名三层无映射），
后端用一句兜底话术把"找不到"伪装成"有效果"。WB-178 为总纲、WB-179～186 为子任务，范围含 Server/Console 侧。
