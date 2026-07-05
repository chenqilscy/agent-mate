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
| [WB-025](WB-025-attach-file-size-limit-too-small.md) | ⬜ | P2 | frontend | ＋菜单「添加文件」上限 200KB 过小（且被后端 8000 字符截断掩盖） |
| [WB-026](WB-026-plan-todo-detail-and-create-modals.md) | ✅ | P2 | frontend | 计划 · 待办详情弹窗 + 新建待办弹窗 + WorkItem 数据模型扩展 |
| [WB-027](WB-027-plan-toolbar-filter-batch-search.md) | ✅ | P2 | frontend | 计划 · 顶部工具条（归属/来源筛选 + 批量操作 + 搜索） |
| [WB-028](WB-028-plan-add-datasource-picker-placeholder.md) | ✅ | P2 | frontend | 计划 · 「添加数据源」选择器（占位，明确「敬请期待」，不伪造授权） |
| [WB-029](WB-029-plan-add-to-input-as-ref-chip.md) | ✅ | P2 | ui | 计划 · 「添加到输入框」应作为独立引用 chip 显示，而非混入正文 |
| [WB-030](WB-030-agent-work-item-status-tools.md) | ✅ | P2 | backend | 计划 · 计划项作为可执行任务，agent 能查看并回写其状态 |
| [WB-031](WB-031-live-work-item-sse-sync.md) | ✅ | P3 | frontend | 计划 · agent 改状态时实时回写看板（SSE 事件），而非仅返回刷新 |
| [WB-033](WB-033-automation-runnow-stuck-running.md) | ✅ | P2 | frontend | 「立即运行」自动化后状态永久卡在「运行中」（前端只刷新一次、无轮询） |
| [WB-034](WB-034-automation-view-live-poll.md) | ✅ | P3 | frontend | 自动化看板不反映「到点自动触发」的运行（视图级自适应轮询） |

## 来源

本批 issue 来自 2026-07-06 的一次三路并行代码审查（前端逻辑 / 后端逻辑 / UI·CSS）
+ 浏览器实测复查。🆕 标记为近期改动（＋菜单 loadout、⌘F 搜索、响应式抽屉）引入；
其余为原型迁移遗留或既有实现。
