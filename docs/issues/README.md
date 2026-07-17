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
| [WB-073](WB-073-hub-status-linked-ignores-token.md) | ✅ | P1 | backend | /api/hub/status 的 linked 判定忽略当前 Hub token，登录后讨论 UI 不解锁（WB-067 真机 E2E 发现） |
| [WB-074](WB-074-presence-never-seen-epoch.md) | ✅ | P3 | frontend | 讨论面板在线状态：从未上线的成员显示「最后活跃 20641 天前」（WB-067 真机 E2E 发现） |
| [WB-075](WB-075-linked-hub-modal-unreachable.md) | ✅ | P2 | frontend | 已连接 Hub 后无入口打开连接弹窗，导入/通知/断开成死代码 —— 加「管理」入口（WB-067 真机 E2E 发现） |
| [WB-076](WB-076-global-hub-connect-entry.md) | ✅ | P2 | frontend | 连接 Hub 入口只在项目讨论面板内，零项目新用户无法首次连接 —— 账号菜单加全局入口（WB-067 复盘） |
| [WB-077](WB-077-assistant-settings-panel.md) | ✅ | P2 | frontend | 助理设置面板 —— 齿轮点开的真配置（名字/人格/模型/开关/绑定/token 存 DB，write-only 不回传前端） |
| [WB-078](WB-078-buddywebmgr-epic.md) | ✅ | P1 | frontend | BuddyWebMgr —— Hub 控制台升级为完整 Web 管理门户（总纲/epic；六子任务全落地，设计见 docs/buddywebmgr-管理门户设计.md） |
| [WB-079](WB-079-buddywebmgr-rename-nav.md) | ✅ | P2 | frontend | BuddyWebMgr 品牌更名 + 导航重构（门户骨架；仅 Web 品牌层，不动 hub/·HUB_URL 内部标识） |
| [WB-080](WB-080-portal-project-config.md) | ✅ | P2 | frontend | 门户项目管理面 —— 配置编辑（指令 + 连接器/专家/技能 picker，读目录、写 PATCH /projects） |
| [WB-081](WB-081-hub-work-items-sync.md) | ✅ | P2 | fullstack | 团队计划/任务 —— Hub work_items 模型 + 路由 + 门户看板（本地⇄Hub 同步拆二期 WB-091） |
| [WB-082](WB-082-catalog-experts-teams-crud.md) | ✅ | P2 | fullstack | 目录运营中心框架 + 专家/专家团 类型化 CRUD（替裸 JSON，客户端 pull 下发；后端加 ?all=true 含停用项） |
| [WB-083](WB-083-catalog-connectors-crud.md) | ✅ | P2 | frontend | 目录运营中心 —— 连接器 类型化 CRUD（launch spec 编辑器：内置/stdio；secret_env 仅变量名） |
| [WB-084](WB-084-catalog-skills-skillhub.md) | ✅ | P2 | fullstack | 目录运营中心 —— 技能 + SkillHub（浏览/搜索/上架/手动同步；接已就绪的 WB-069 后端） |
| [WB-085](WB-085-assistant-page-toolbar-real.md) | ✅ | P2 | frontend | 助理页顶栏按钮接真实 transcript —— 对话内搜索/分享导出/历史提问（去掉 toast 占位，复用 ChatView） |
| [WB-086](WB-086-multi-assistant-multi-channel-epic.md) | ✅ | P1 | fullstack | 多助理·多渠道 —— 助理子系统重构（总纲/epic；设计见 docs/workbuddy-助理-架构设计.md；S1-087/S2-088/S3+S4-089） |
| [WB-087](WB-087-multi-assistant-backend-model.md) | ✅ | P1 | backend | 多助理 S1 —— 后端模型(assistants/channels) + CRUD + 多 bot 渠道管理器 + run_chat 接 workspace/mode + 迁移 |
| [WB-088](WB-088-multi-assistant-frontend.md) | ✅ | P1 | frontend | 多助理 S2 —— 前端多助理管理 UI（主从：列表/新建/设置/对话/渠道；合并 S3 前端） |
| [WB-089](WB-089-multi-assistant-consolidate.md) | ✅ | P1 | fullstack | 多助理 S3+S4 收尾 —— 移除兼容层 + 端到端验证 + 关闭 epic WB-086 |
| [WB-091](WB-091-local-hub-work-items-sync.md) | ✅ | P3 | backend | 本地 App ⇄ Hub work_items 双向同步（WB-081 二期；hub-origin 项目 work-items 读代理+镜像/写代理，前端零改，离线兜底） |
| [WB-092](WB-092-skillhub-tab-parity.md) | ✅ | P3 | frontend | BuddyWebMgr SkillHub 页向真站对齐（左筛选：发布来源/排序/场景 + 富卡片图标/来源/★/⬇；api-key 与飙升排序无数据诚实不做） |
| [WB-093](WB-093-assistant-token-visible-env-cleanup.md) | ✅ | P2 | fullstack | 助理渠道 token 本机可见（撤销 write-only）+ 移除 .env Telegram 配置 + 铁律#4 同步（用户显式决定，local-first） |
| [WB-094](WB-094-skillhub-cli-to-http.md) | ✅ | P3 | backend | SkillHub 取数 CLI→直连 HTTP（showcase/search 公开无需 key；拿到 created_at 补「最近上新」；企业 key 可选拉私有 registry） |
| [WB-095](WB-095-skillhub-api-key-setting.md) | ✅ | P3 | fullstack | BuddyWebMgr 设置页保存 SkillHub API key（Hub 服务端存储/打码回显/注入取数；skh_ 个人·sk-ent- 企业） |
| [WB-096](WB-096-email-channel.md) | ✅ | P2 | fullstack | 助理邮件渠道 —— IMAP 收 + SMTP 发（多渠道新类型，白名单+暗号，接入多助理，复用 ChannelManager） |
| [WB-097](WB-097-channel-typemenu-clipped.md) | ✅ | P2 | ui | 助理「新增渠道」类型菜单被滚动容器裁切 —— 改用 Popover（fixed 定位不裁切，复用 .pop-item） |
| [WB-098](WB-098-email-self-reply-loop.md) | ✅ | P1 | backend | 邮件渠道自我回复循环 —— 回信打 X-WorkBuddy-Assistant 头，收信跳过自己回信（防邮件风暴） |
| [WB-099](WB-099-console-grid-overflow.md) | ✅ | P3 | ui | BuddyWebMgr SkillHub 页横向溢出 —— grid 1fr→minmax(0,1fr)（SkillHub/看板/grid2 同修） |
| [WB-100](WB-100-console-experts-showroom.md) | ✅ | P2 | frontend | BuddyWebMgr 专家/专家团升级为 App 同款浏览橱窗（精选场景+子标签+分类+富卡片+详情弹窗；替裸 CRUD，管理动作进弹窗；纯 vanilla 无后端改） |
| [WB-101](WB-101-console-connector-gallery.md) | ✅ | P3 | ui | BuddyWebMgr 连接器补「浏览橱窗」—— 目录管理旁加 App 风格双列卡片橱窗（读同一 CONN_DEFS，cg- 前缀防撞并发） |
| [WB-102](WB-102-console-skill-gallery.md) | ✅ | P2 | frontend | BuddyWebMgr 技能补「浏览橱窗」（整页技能）—— 精选+换一换/推荐·SkillHub·套件/分类/富卡★⬇/详情/搜索，读同一目录数据，sg- 前缀防撞并发 |
| [WB-103](WB-103-professional-pm-epic.md) | 🟡 | P1 | fullstack | BuddyWebMgr 专业项目管理 + App 数据打通（总纲/epic）—— 完整 PM(负责人/优先级/截止/标签/子任务/里程碑/活动流/列表·看板·甘特) + 本地⇄Hub 打通；子任务 WB-104~108 |
| [WB-104](WB-104-hub-pm-data-model.md) | ✅ | P1 | backend | Hub 专业 PM 数据模型 + 迁移 —— work_items 增 priority/due/start/labels/parent_id/milestone_id + 新表 milestones/work_item_activity（非破坏 ALTER，CRUD 扩展） |
| [WB-105](WB-105-hub-pm-api.md) | ✅ | P1 | backend | Hub 专业 PM API —— work_items 全字段+子任务+活动流端点 + milestones CRUD 路由；assignee/priority 宽松校验保护同步（TestClient 冒烟 20 项全过） |
| [WB-108](WB-108-app-hub-pm-integration.md) | ✅ | P1 | fullstack | App↔Hub 专业 PM 打通 —— 本地模型/迁移/同步扩展新字段+里程碑 + App 工作台任务 UI（优先级/标签/里程碑接卡片·详情·新建）；冒烟 25+12+HTTP E2E 全过、tsc/build 过、明暗双主题 CDP 实截核对过 |
| [WB-106](WB-106-portal-task-professional.md) | ✅ | P1 | frontend | BuddyWebMgr 门户任务专业化 —— 看板卡片富信息(优先级/负责人/截止/标签/里程碑/子任务) + 任务详情抽屉(全字段+子任务+活动流) + 里程碑条；全 pm- 前缀内联样式防撞并发；隔离 Hub CDP 实测无报错 |
| [WB-107](WB-107-portal-task-views-filters.md) | ✅ | P2 | frontend | BuddyWebMgr 门户任务 列表视图 + 甘特/时间线视图 + 筛选/排序 —— 视图切换器(看板/列表/甘特) + 搜索/状态/优先级/负责人/里程碑筛选；续 pm- 前缀内联样式，hunk 提交；隔离 Hub CDP 三视图实测无报错 |
| [WB-110](WB-110-portal-kanban-drag-activity.md) | ✅ | P2 | frontend | BuddyWebMgr 门户 PM 增强 —— 看板拖拽换列(快速改状态,Viewer 不可拖) + 项目级任务活动流面板(消费 WB-105 activity 端点,变更自动刷新)；CDP DragEvent 实测 Hub 真变+活动入流 |
| [WB-109](WB-109-app-featured-consume-hub.md) | ✅ | P3 | frontend | App 精选技能区消费 Hub SKILLHUB_FEATURED —— 打通 mgr「加入精选」→ App（渲染真图标，回退静态兜底；纯前端，数据链路 E2E 实测） |
| [WB-123](WB-123-app-kanban-enhancements.md) | ✅ | P2 | frontend | App 对齐片7 看板增强 —— WIP 上限(超限红)+泳道分组(按负责人/里程碑)+保存视图(per-project localStorage，抽 renderKanban 复用；对齐 Manager WB-113) |
| [WB-122](WB-122-app-task-templates.md) | ✅ | P2 | frontend | App 对齐片6 任务模板 —— 详情「存为模板」+ 看板「从模板」新建(per-project localStorage，对齐 Manager WB-114) |
| [WB-121](WB-121-app-gantt-view.md) | ✅ | P2 | frontend | App 对齐片5 甘特视图 —— 项目页加「甘特」tab(相对时间横条+今天线+月度刻度+优先级色条，对齐 Manager pmViewGantt) |
| [WB-120](WB-120-app-tasklist-inline.md) | ✅ | P2 | frontend | App 对齐片4 任务列表增强 —— TaskList 行内状态/优先级改可内联编辑 pill(复用 StatusPill/PriorityPill) + 负责人头像 |
| [WB-119](WB-119-app-workload-view.md) | ✅ | P2 | frontend | App 对齐片3 工作量视图 —— 项目页加「负载」tab(按负责人聚合状态分布+完成率+逾期+工时Σ，对齐 Manager pmViewWorkload) |
| [WB-118](WB-118-app-task-comments.md) | ✅ | P2 | fullstack | App 对齐片2 任务级评论 —— App 后端代理 Hub 任务评论端点 + 任务详情评论区（复用 WB-115 Hub 端点，仅 hub-origin 可用） |
| [WB-117](WB-117-app-pm-alignment.md) | ✅ | P2 | fullstack | App 端项目管理对齐 Manager（epic，七片全 done）—— 工时全链路 + 任务评论 + 工作量/甘特视图 + 列表内联 + 任务模板 + 看板 WIP/泳道/保存视图；App 工作台 tab 动态/计划/任务/负载/甘特/资产/讨论 与 Manager 能力对齐 |
| [WB-116](WB-116-pm-effort-hours.md) | ✅ | P2 | fullstack | PM 细化之四 计划与度量(片1) 工时预估与投入 —— Hub work_items 加 estimate_h/spent_h + 控制台抽屉工时输入 + 工作量/概览汇总（Manager 侧） |
| [WB-115](WB-115-pm-workload-task-comments.md) | ✅ | P2 | fullstack | PM 细化之三 协作联动 —— 按负责人工作量视图(前端聚合) + 任务级评论(Hub comments 加 work_item_id + 任务级端点 + 控制台抽屉评论区) |
| [WB-114](WB-114-pm-task-templates-inline-edit.md) | ✅ | P2 | frontend | PM 细化之二（纯前端）任务模板 + 列表内联编辑(状态/优先级/负责人/里程碑点选即改) + 子任务进度条；依赖/自定义字段/附件需后端另设计 |
| [WB-113](WB-113-pm-board-view-enhancements.md) | ✅ | P2 | frontend | PM 细化之一 看板/视图增强 —— 泳道分组(按负责人/里程碑) + 列 WIP 上限(超限标红·localStorage) + 保存的筛选视图 + 列表批量操作(改状态/负责人/里程碑/删除)；纯前端 console，续 pm- 前缀 |
| [WB-112](WB-112-manager-positioning-data-spec.md) | 🟡 | P1 | fullstack | WorkBuddy Manager 管理端定位（epic）—— 改名 BuddyWebMgr→WorkBuddy Manager(done) + 数据分层规范 `docs/workbuddy-数据分层与同步规范.md`(done) + 统一用户/协作写代理/身份强映射/动态回读/镜像增量合并/PM 细化(待做) |
| [WB-111](WB-111-portal-pm-workspace-redesign.md) | ✅ | P1 | frontend | BuddyWebMgr 门户项目管理专业化重构 —— 项目详情改标签页工作台(概览/任务/协作/配置) + Linear 风看板/列表/甘特(统计条·进度条·列容器·富卡片·头像·逾期高亮·今天线)；纯前端消费既有 WB-104/105 API，Hub :8100 四 tab×三视图 CDP 实测+拖拽真落库，0 报错 |
| [WB-124](WB-124-model-management-custom-models.md) | ✅ | P2 | fullstack | 模型管理 —— 自定义模型全栈（多厂商 base/key、DB 按用户隔离、内置项可隐藏、切换真生效）：底部模型下拉「配置自定义模型」落地 + resolve 按 owner 路由到各厂商 base/key |
| [WB-125](WB-125-merge-skillhub-into-skills-tab.md) | ✅ | P2 | frontend | 目录运营中心「SkillHub」顶层 tab 与「技能」tab 冗余 —— 把顶层 SkillHub 降为「技能」的第三子视图（浏览橱窗｜目录管理｜SkillHub 同步），与「连接器」范式对齐，顶层 5→4 tab（console.html 纯前端） |
| [WB-126](WB-126-skillhub-sync-http-leftover.md) | ✅ | P2 | fullstack | SkillHub 同步 HTTP 化后的收尾 —— 前端手动同步文案仍写死「跑 CLI」（误导，实际直连公开 HTTP、无需 key）；后台定期同步被 `cli_available()` 卡住，无 CLI 环境一次都不启动（hub/web/console.html:1617 + hub/main.py:38） |
| [WB-127](WB-127-skillhub-sync-list-no-detail.md) | ✅ | P3 | frontend | 目录运营中心「SkillHub 同步」列表无查看技能详情入口 —— 卡片描述截断且不可点，复用现成 `sgDetail()` 弹窗给列表项加点击详情（纯前端 console.html） |
| [WB-128](WB-128-builtin-provider-channels.md) | ✅ | P2 | fullstack | 模型管理重构 —— 内置改「厂商渠道」（DeepSeek/智谱/MiniMax/Kimi/通义/OpenAI，真实 base+模型，填 key 即用）+ 移除假 Auto/倍率 + resolve 按 @provider 路由(含非标 chat_path) + 自定义作兜底 |
| [WB-129](WB-129-provider-editable-base-live-models.md) | ✅ | P2 | fullstack | 厂商渠道 base_url/请求路径可显示可编辑（按 owner 覆盖预置，resolve 用有效值）+ 「拉取最新」在线列举厂商真实模型（打 `{base}/models`，治模型名过时）；实测真拉到用户 DeepSeek 的 v4-flash/pro |
| [WB-130](WB-130-console-skill-detail-files.md) | ✅ | P3 | fullstack | 技能「文件信息」收敛到 Manager —— Hub 加单技能预览代理(HTTP 富元数据+CLI SKILL.md) + App 改走 Manager 取数(不再直连 SkillHub，本地兜底) + Manager 控制台弹窗懒加载渲染 SKILL.md/参考文件/版本来源 |
| [WB-131](WB-131-manager-nav-ia-redesign.md) | ✅ | P2 | frontend | WorkBuddy Manager 导航/IA 专业化重构 —— 扁平混杂菜单改分区侧栏(工作区/目录/系统)+顶栏(组织切换·通知铃铛·账号)+新增概览页+收编 SkillHub/高级JSON、去运营黑话；纯前端 console.html，沿用现有 token（关联 epic WB-112 管理端定位） |
| [WB-132](WB-132-model-capabilities-cost-meta.md) | ✅ | P2 | fullstack | 模型能力/成本元数据（模态/工具/推理 + 每百万token 输入·输出单价 + 上下文，启发式默认可编辑，为 Auto 铺路）+ 接入地址简化为仅 Base URL + 模型管理提到全局菜单入口（账号菜单，uiStore flag） |
| [WB-133](WB-133-drop-hide-restore-unify-delete.md) | ✅ | P3 | frontend | 去掉厂商模型「隐藏/恢复」二层机制，预置/自加统一为一个「删除」（删的不再显示，要用再拉取/手填加回；复用既有端点，前端过滤 hidden） |
| [WB-134](WB-134-curated-model-defaults-tiered-pricing.md) | ✅ | P2 | fullstack | 内置厂商按官方文档建准确「能力+定价」默认表（DeepSeek/智谱，preset 优先于名字启发式）+ 定价 schema 加缓存命中价/币种 + 更新过时 seed（DeepSeek→v4-flash/pro、智谱现役 GLM）；model_meta ALTER 迁移，reset 回 preset |
| [WB-135](WB-135-glm-official-pricing.md) | ✅ | P2 | backend | 补齐智谱 GLM 官方定价（文本+视觉，人民币/基础档+note 标分档/缓存命中价）+ seed 对齐现役旗舰(glm-5.2/4.7/4.5-air/4.6v) + 视觉补 image/video 能力；只收 chat 模型（生成/语音/向量/重排非 chat、按次计费，如实不纳入） |
| [WB-136](WB-136-ui-default-model-not-env.md) | ✅ | P2 | fullstack | 「默认模型」改为在「配置模型」里选择、按 owner 存 DB，彻底不读 .env：backstop 名字/运行时空选择解析都改走 DB 默认，无默认则诚实报错；新增 `PUT /api/models/default` + 配 key 时自动设默认；前端加「设为默认」+ 去掉 App.tsx 首屏回填 |
| [WB-137](WB-137-home-ctray-stub-buttons.md) | ✅ | P2 | frontend | 首页「选择工作空间/默认权限」两个 tray 按钮是 toast 桩：接 projectStore(startProject) 做真空间选择 + 复用 PermPopover 设默认权限 |
| [WB-138](WB-138-model-mgmt-to-left-menu.md) | ✅ | P2 | frontend | 模型管理入口从输入框模型下拉的「配置模型」移到左侧「更多」菜单（+移除账号菜单重复入口、runtime.py 报错文案改「模型管理」）；ModelPicker 只做选模型，空态文案改指向「更多·模型管理」 |
| [WB-139](WB-139-local-voice-input-asr.md) | ✅ | P2 | fullstack | 语音输入落地 —— 本地 ASR 小模型（faster-whisper base），按住说话松开转写：后端 /api/asr（懒加载单例·PyAV 直解 webm·依赖未装诚实 503）+ 前端 Composer 麦克风真录音（pointer 按住·红点脉冲·转写态·权限兜底）+ api.transcribeAudio；音频不出本机 |
| [WB-140](WB-140-kdocs-sidebar-panel.md) | ✅ | P2 | fullstack | 侧栏「更多 → 金山文档」从 toast 桩变真面板：后端 GET /api/connectors/kdocs/files（最近/搜索云文档，归一化 items、诚实降级）+ 前端 KdocsView（连接态引导·搜索·点开跳转 kdocs.cn，复用既有 class）；复用 WB-052 已打通的 kdocs 连接器/OAuth |
| [WB-141](WB-141-glm-knowledge-base-rag-epic.md) | ✅ | P1 | fullstack | GLM 知识库 RAG 接入（总纲/epic）—— 本地 backend 执行(建库/传档/文档管理/文本+全模态检索/上下文增强，key 只存本地) + 检索接进 agent 工具循环 + Manager 目录橱窗管理下发；子任务 WB-142~145 全落地实测 |
| [WB-142](WB-142-glm-kb-backend-engine.md) | ✅ | P1 | backend | GLM 知识库 Phase A —— 本地 backend 真·知识库引擎 glm_kb.py(httpx) + routers/knowledge.py(建库/传档/文档管理/检索/全模态/用量)，key 走 db.get_provider_key(owner,zhipu)；真机建库→传档→向量化→检索全通 |
| [WB-143](WB-143-glm-kb-agent-retrieve-tool.md) | ✅ | P1 | backend | GLM 知识库 Phase B —— knowledge_retrieve 工具接进 agent 工具循环(照抄 set_work_context contextvar) + ChatBody.knowledge_ids loadout 透传；SSE 真出 knowledge_retrieve 事件+引用来源作答 |
| [WB-144](WB-144-glm-kb-app-frontend.md) | ✅ | P1 | frontend | GLM 知识库 Phase C —— App 前端 KnowledgeView(建库/传档/进度/用量/模板) + knowledgeStore + Composer loadout 选择器 + Sidebar 入口；CDP 实截渲染真 GLM 用量+模板 |
| [WB-145](WB-145-glm-kb-manager-console.md) | ✅ | P2 | frontend | GLM 知识库 Phase D —— Manager console 知识库橱窗+目录管理(kb- 前缀，仿 WB-101) + catalog_items 新 category KB_TPLS 下发(零 schema 改动)；隔离 Hub CDP 实截 CRUD+橱窗 |
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
| [WB-156](WB-156-hub-invite-reuse-and-viewer-writes.md) | ✅ | P1 | backend | Hub 访问控制 —— 邀请码可无限重用/永不失效 + Viewer 越权（timeline 上报 / org 建项目） |
| [WB-157](WB-157-hub-pm-referential-integrity.md) | ✅ | P2 | backend | Hub PM 引用完整性 —— parent_id/milestone_id 跨项目未校验 + 级联删除/清空无 project 过滤 |
| [WB-158](WB-158-hub-origin-offline-write-data-loss.md) | ✅ | P2 | backend | hub-origin 项目离线新建 work_item/milestone 被下次镜像删除（数据丢失） |
| [WB-159](WB-159-frontend-store-robustness.md) | ✅ | P2 | frontend | 前端 store 健壮性 —— 看板乐观更新不回滚 / answer 失败挂起 agent / send finally 无流守卫 / connect 不 reload |
| [WB-160](WB-160-backend-hardening-tail.md) | 🟡 | P2 | backend | 后端加固尾集 —— 通知空 ids 误清全部 / MCP 超时孤儿进程 / 邮件先标已读丢信 / 流出错丢回复 / SSRF / slug 校验（邮件项 deferred） |
| [WB-161](WB-161-authoritative-docs-correction.md) | ✅ | P2 | misc | 权威现状文档纠偏 —— CLAUDE.md/README/实现方案 对 Hub/auth/LLM key/CSS/Tauri 的错误陈述 |
| [WB-162](WB-162-memory-mechanism-optimization.md) | ✅ | P2 | fullstack | 记忆机制优化 —— 注入预算化(优先手动+最近·超预算截断) + 结构化抽取(add/update 合并·更替过时矛盾) + 抽取输入预算 + 手动编辑一条(PUT+内联编辑 UI) |
| [WB-163](WB-163-manager-user-management.md) | ✅ | P1 | backend | Manager 用户管理 —— 平台账号 admin CRUD(列表/建/改人格套餐管理员/重置密码/删，含删自己·最后管理员·有项目守卫) + console「用户」页(um- 前缀) |
| [WB-164](WB-164-app-login-via-manager.md) | ✅ | P1 | backend | App 登录经 Manager 验证 + 两端打通 —— Manager 权威(ok 用 Hub token 镜像) + 离线兜底(login 回退本地/register 诚实 503) + hub_login_ex 判别式；未接 Hub 零变化 |
| [WB-165](WB-165-cognitive-memory-epic.md) | ✅ | P2 | fullstack | 认知记忆机制移植(参考 AgentOS·epic) —— 强度/衰减/使用强化 + 本地语义检索 + 白盒管理（WB-166~168 三档累加） |
| [WB-166](WB-166-memory-strength-decay-lifecycle.md) | ✅ | P2 | backend | 认知记忆 档一 —— 强度(importance×recency衰减×usage)排序注入+命中强化 + 软状态生命周期(active/superseded/archived 不硬删) + decay_gc（无嵌入） |
| [WB-167](WB-167-memory-local-semantic-retrieval.md) | ✅ | P2 | backend | 认知记忆 档二 —— 本地嵌入(fastembed bge-small-zh·可选依赖懒加载) + 语义去重/自动更替 + 按当前对话相关性 top-K 注入 |
| [WB-168](WB-168-memory-whitebox-management-ui.md) | ✅ | P2 | fullstack | 认知记忆 档三 —— 白盒管理(API: stats/search/importance/archive/rollback/trace/decaying + 设置·记忆面板升级) |
| [WB-169](WB-169-console-kb-tpl-dim-slice-dropdowns.md) | ✅ | P2 | frontend | Manager 知识库模板编辑器 —— 新增「向量维度」联动下拉(跟随模型·真实生效·不碰铁律#1) + 切片方式改下拉(GLM 真实枚举) + 切片字数仅自定义切片时显示 |
| [WB-170](WB-170-memory-embedding-backend-configurable.md) | ✅ | P2 | fullstack | 记忆嵌入后端可配置 —— 本地(fastembed bge-small-zh) ⇄ 在线(GLM embedding-3) 用户可选 + 跨模型 tag 惰性重嵌入迁移（知识库档位选择 WB-144/169 已就绪，本条只补记忆侧） |
| [WB-171](WB-171-hub-knowledge-base-document-backend.md) | ✅ | P2 | backend | Hub 真·知识库 + 文档后端(项目级) —— 建库/传档(字节存 Hub)/文档管理 + 有文档后锁向量维度(400 拦截)；Manager 不算向量(向量化交执行面，且只调 GLM 嵌入接口、不用 GLM 知识库功能) |
| [WB-172](WB-172-manager-project-knowledge-base-tab.md) | ✅ | P2 | frontend | Manager 项目「知识库」tab —— 真·建库(向量维度联动下拉/切片方式下拉)+文档上传/列/删+有文档后维度 select 锁定+诚实未向量化状态(kbm- 前缀)；配 WB-171 |
| [WB-176](WB-176-trim-experts-showcase-data.md) | ✅ | P3 | fullstack | 精简专家/专家团橱窗数据 —— 三层数据源(前端静态兜底/后端种子/运行库)同步裁剪至 专家7·团3·场景3·分类6，避开「删空即重种」与「兜底顶上来」两个复活陷阱 |
| [WB-177](WB-177-connectors-showcase-weknora.md) | ✅ | P3 | fullstack | 连接器橱窗改版 —— 三层同步去掉 ima知识库/乐享知识库/腾讯文档/TAPD/企查查(12→8)，新增 WeKnora知识库 卡 + CONN_META 详情(工具清单逐字镜像后端真 knowledge_retrieve/knowledge_add) |
| [WB-178](WB-178-skills-subsystem-epic.md) | ⬜ | P1 | fullstack | 技能子系统重构（总纲/epic）—— 以 slug 为主键焊死「橱窗/loadout/磁盘」三层；根因=技能无稳定身份，橱窗与真引擎靠展示名撞运气连通；子任务 WB-179~186 |
| [WB-179](WB-179-skill-identity-and-fallback-prompt.md) | ⬜ | P1 | fullstack | 技能身份断裂 —— loadout 存展示名 + `skill_def` 兜底话术「运用「X」技能的专长…」伪装能力（SK_GRID 17 个里 11 个后端零能力，铁律#1） |
| [WB-180](WB-180-skill-picker-ignores-installed.md) | ✅ | P1 | frontend | ＋菜单技能选择器只读静态 SK_GRID —— 真实已安装的技能在会话里选不到（装机与使用两条路断开）；改为「内置(新增 /skills/builtin，SK_GRID 里藏着 6 个真内置技能差点被砍) + 已装未停用」，静态假卡不再出现；CDP 自驱实测 23 项(12 张真卡/明暗双主题对比度/窄宽/loadout chip 真出) |
| [WB-181](WB-181-skills-page-fake-interactions.md) | ⬜ | P1 | frontend | 技能页假交互清理 —— 推荐段＋号/安装套件/排序/＋添加技能 全是 toast 桩 + SKILLHUB_GRID 写死假 downloads/stars（铁律#1） |
| [WB-182](WB-182-skill-kits-fabricated.md) | ⬜ | P2 | fullstack | 「套件」100% 虚构 —— 前端 4 条静态卡（技能数手写）、后端零代码、Hub 无源、DB 无表、安装按钮是 toast；真做(Hub kit 表+批量安装)或删 |
| [WB-183](WB-183-catalog-skills-to-db.md) | ⬜ | P2 | fullstack | 技能目录/定义未入库 —— WB-059 漏项：专家人格/连接器进了 DB，技能仍硬编码在 skills.py；设计过的 catalog_skills 表从未建 + 63 条孤儿静态数据 + 分类映射双份硬编码 |
| [WB-184](WB-184-skill-browse-sources-convergence.md) | ⬜ | P2 | frontend | 技能浏览四套数据源 + 两套分类体系并存（精选/推荐/SkillHub/套件；SK_CATS vs SKILLHUB_CATS）+ 兜底链竞态 + SK_RECO 死代码 —— 收敛为一个面板一套分类 |
| [WB-185](WB-185-skills-api-attack-surface.md) | ✅ | P2 | backend | /api/skills 攻击面 —— App 侧 install/preview 的 slug 未校验（WB-160 第6项只修了 hub 孪生站点，App 侧漏网）已修+两侧口径统一+顺带硬化前导`-`（实测 CLI argparse 真被 `--dir` 噎住）；零鉴权项 ⏸ deferred（current_user 从不拒绝，需共享后端鉴权策略横切决策） |
| [WB-186](WB-186-skills-backend-consistency-tail.md) | 🟡 | P3 | backend | 技能后端一致性尾集 —— rankings 补齐 Manager 代理(顺带：Hub 走 HTTP 无需 CLI，没装 CLI 的本机终于能拿真实榜单而非静态假数据) + 预览缓存 TTL 对齐 Hub + 合冗余分支，均已修；plan 过滤/schema 去重两项经实测为今日无实害的结构性预防(web_fetch 是 GET 不违反 plan 契约)，⏸ 归 WB-183 一并做 |
| [WB-187](WB-187-resolve-slug-installs-wrong-skill.md) | ✅ | P2 | backend | 按名安装取搜索首条 —— 名字不存在时静默装上无关技能并贴上用户输入的名字（截图里「腾讯微云」的＋号实测会装成 self-improving-agent，真微云技能在搜索第4条被跳过）；resolve_slug 改仅精确命中，实测 38 张静态卡 37 命中/1 诚实404 |
| [WB-188](WB-188-weknora-config-form.md) | ✅ | P2 | fullstack | WeKnora 连接配置改 UI 表单 —— 从「只能改 .env + 重启」改为按 owner 入库(key 存 provider_keys 只写不回读/url 存 KV)、DB 优先 .env 兜底、连接器弹窗内真表单 + 测试连接 |
| [WB-189](WB-189-project-connectors-picker-cleanup.md) | ✅ | P3 | fullstack | 新建项目的连接器选择器/模板仍留着已下架的连接器 —— NP_CONNS 删 乐享知识库/腾讯文档/TAPD(13→10) + NP_TPLS 清引用；且模板提示词点名「在 TAPD 中跟进…同步到腾讯文档」指挥 agent 用不存在的连接器(铁律#1)；配 WB-177 |
| [WB-190](WB-190-skills-tencent-docs-cleanup.md) | ✅ | P3 | frontend | 技能侧「腾讯文档」清理 —— SK_GRID(17→16,DB 供给三层同步)/SK_RECO(死代码)/SKILLHUB_GRID(不入库,仅静态层) 与连接器侧下架不一致；后端本无该技能定义(零能力卡)；配 WB-177/189；⚠️只清掉「我们自己的目录」那半 —— SkillHub 段是上游商店镜像、不受影响，另见 WB-191 |
| [WB-191](WB-191-skillhub-mirror-no-delisting.md) | ⬜ | P3 | fullstack | SkillHub 段是上游 skillhub.cn 商店的镜像(369 条)，本地目录下架对它无效 —— 想下架某条需 Manager 侧跨同步存活的过滤(replace_all_downlink 每次清空重建，删镜像行必被覆盖)；WB-190 实测发现 |
| [WB-192](WB-192-run-command-inherits-secrets.md) | ✅ | P1 | backend | run_command 子进程继承后端全部密钥 —— 模型一句  即可读走并上传给 LLM 厂商；WB-011 只把连接器那条路收成无密钥白名单，run_command 从未收口(WB-014 以「如实标注」结案)；实证子进程读到 LLM_API_KEY(35 字符) |
| [WB-193](WB-193-knowledge-add-url-and-mcp-verdict.md) | ⬜ | P3 | backend | knowledge_add 只能加工作区文件，不能从 URL/文本入库 —— 承接 WB-175 的「留后续」(url 受 WeKnora 侧 SSRF 白名单限制、manual 建出 draft/disabled)；并记录**否决接官方 WeKnora MCP server** 的评估：其 create_knowledge_from_url 打同一个 REST 端点受同样限制(拿不到额外好处)、反而没有本地文件上传、且 _secret_env 只读 os.environ 与 WB-188 的 per-owner DB key 冲突 |

## 来源

本批 issue 来自 2026-07-06 的一次三路并行代码审查（前端逻辑 / 后端逻辑 / UI·CSS）
+ 浏览器实测复查。🆕 标记为近期改动（＋菜单 loadout、⌘F 搜索、响应式抽屉）引入；
其余为原型迁移遗留或既有实现。

WB-058～063 来自 2026-07-07 的架构讨论：把「能力定义入库」与「多用户协作管理平台」
两项诉求整合为 **WorkBuddy Hub（local-first 执行 + 云端控制平面）** 重构。总设计见
[`docs/workbuddy-hub-架构设计.md`](../workbuddy-hub-架构设计.md)，WB-058 为总纲、WB-059～063 为分阶段子任务。

WB-078～084 来自 2026-07-08 用户检查 Hub 站点后的诉求：把 Hub 控制台升级为完整 Web 管理门户并更名
**BuddyWebMgr**（项目管理面 + 目录运营中心 + SkillHub）。总设计见
[`docs/buddywebmgr-管理门户设计.md`](../buddywebmgr-管理门户设计.md)，WB-078 为总纲、WB-079～084 为分阶段子任务。

WB-178～186 来自 2026-07-16 用户要求对**技能功能的设计从头审查**（前端 / 后端 / Hub 三路梳理 + 逐条源码核实）。
结论：技能是「橱窗」与「真引擎」两套互不相认的系统贴在一起，根因是**技能没有稳定身份**（展示名 / slug / 磁盘目录名三层无映射），
后端用一句兜底话术把"找不到"伪装成"有效果"。WB-178 为总纲、WB-179～186 为子任务，范围含 Hub/Manager 侧。
