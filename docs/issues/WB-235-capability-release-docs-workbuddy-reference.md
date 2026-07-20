---
id: WB-235
title: 能力目录发布升级设计与 WorkBuddy 产品参考缺少统一文档沉淀
severity: P1
area: misc
status: fixed
origin: 既有实现
files:
  - docs/agentmate-实现方案.md:10
  - docs/agentmate-server-架构设计.md:116
  - docs/agentmate-console-管理门户设计.md:69
  - docs/desktop-build.md:62
  - docs/WorkBuddy/tencent-workbuddy-reference.html:1
  - backend/server_sync.py:113
  - backend/agent/skills.py:426
  - src/stores/catalogStore.ts:67
  - src-tauri/tauri.conf.json:44
created: 2026-07-21
---

## 问题

AgentMate 已经分别实现 Server Console 的 `APP_SKILLS` 目录 CRUD、Server→App 全量目录下行、
AgentMate 目录技能的本机安装/版本提示/原子替换，以及 Tauri updater 脚手架，但现有方案与架构文档
仍以里程碑完成情况和模块列表为主，没有把这些能力组织成一套可运营、可升级、可回滚的
**能力发布体系**，也没有清楚区分以下四种版本边界：

1. Server 侧 Skill 目录元数据、指令和附加文本文件；
2. 已安装到 App 本机的 Skill 快照；
3. Skill 绑定的工具、权限和 App 能力契约；
4. 必须随签名桌面安装包发布的工具实现、运行时与 UI。

源码核实还发现，现状中存在必须在设计文档里如实标注、后续按独立实现任务解决的边界：

- Server 普通目录下行不携带停用的 `APP_SKILLS`；App 全量替换 `scope=server` 后会继续暴露同 slug
  的本地 builtin 兜底，因此 Console 的“停用/归档”还不能作为中心权威撤回能力。
- 已安装目录 Skill 的指令来自本地 `SKILL.md` 快照，但工具列表由最新 `catalog_skills` 实时解析；
  Server 修改工具绑定后可能出现“旧指令 + 新工具”的混合版本，权限扩大也没有独立确认。
- `shared/skill-tools.json` 已声明 `min_app_version`，但 App 下行和运行时没有执行兼容性门禁；
  Server 只能配置已知工具名，不能证明某台旧 App 真正支持该工具版本。
- App 只在前端目录模块初始化或登录后触发一次 `POST /server/pull`，缺少恢复唤醒、周期检查、
  手动刷新和目录失效推送，长时间运行的客户端不能及时获得运营更新。
- Tauri updater 已有下载、安装、重启代码，但 endpoint 仍是占位地址，也没有实际调用入口；
  “Server 已更新”和“桌面 App 已升级”目前不是一条已上线的发布链路。

与此同时，腾讯 WorkBuddy 已公开形成“任务工作台 + Skill + 专家/专家团 + 连接器 + 自动化 +
远程助理 + 企业控制面”的完整产品分层。仓库只有一个历史高保真原型 HTML，缺少按来源、访问日期、
产品概念、交互路径、能力边界和 AgentMate 可借鉴点整理的参考资料目录。后续设计容易继续依赖
零散网页、口头记忆或过期截图，无法追溯依据。

本 issue 的交付范围是**登记真实现状、更新方案/架构/Console/桌面发布文档并建立 WorkBuddy
参考资料目录**；不把运行时代码缺口伪装成已修复。停用墓碑、Skill 原子权限快照、同步失效通知、
正式桌面更新服务和新增办公工具等实现，应在本设计确定后分别登记实现 issue。

## 触发场景

1. 平台管理员在 Console 修改或停用一个内置 Skill，随后询问“App 何时、以什么方式升级”；
   现有文档无法给出目录刷新、本机安装快照、工具兼容和桌面版本之间的完整答案。
2. Console 为 Skill 增加工具绑定，已安装旧版本 Skill 的 App 在未点击升级时就可能取得新工具，
   但详情页仍显示旧版本指令，文档没有说明这一混合状态及权限风险。
3. 运营希望紧急撤回内置 Skill；下行省略停用项后 App 回退 builtin，中心停用语义没有在架构中定义。
4. Server 部署新能力后，用户期待桌面 App 自动升级；实际 updater endpoint 仍为占位符，且 UI
   没有触发检查更新，方案文档却只写“接端点即生效”，缺少生产发布、签名、灰度和回滚流程。
5. 产品继续对标 WorkBuddy 的专家团、连接器、自动化、产物区和企业治理时，需要反复上网查找，
   仓库内没有统一的官方来源索引、事实摘要和设计分析。

## 影响

P1：能力目录是 Console 运营和 App 真实执行之间的核心契约。发布边界不清会导致运营误以为
“保存即全量生效”或“停用即可撤回”，也可能让工具权限在用户未确认升级时发生变化。桌面更新
链路未落地则阻断新增工具和运行时修复的可靠分发。缺少可追溯的竞品参考资料还会使后续方案
反复漂移，出现只有卡片没有真实能力、专家团只是多人格组合、文档型 Skill 不生成真实产物等问题。

## 建议修法

### A. 更新 AgentMate 方案与架构

- 在总实现方案中补充“任务交付优先”的产品原则，以及 Tool / Skill / Expert / Expert Team /
  Connector / Automation / Inspiration 的职责边界；明确当前能力和 WorkBuddy 对标差距。
- 在 Server 架构中增加能力控制面与本地执行面：目录 revision、显式 tombstone、最后可用快照、
  App capability report、最低版本门禁、兼容窗口、权限变化确认、发布/撤回/回滚语义。
- 明确目录内容更新、Skill 快照升级、工具契约升级和 App 二进制升级是四条关联但不同的链路。
- 把“纯文本且不扩大权限可自动更新；新增写入/网络/外部服务能力必须确认”写成产品规则。

### B. 更新 Console 与桌面发布设计

- Console 从 CRUD 升级为“草稿 → Test Run → 审核 → 发布 → 灰度 → 全量 → 撤回/回滚”，
  展示版本说明、最低 App 版本、工具/权限 diff、发布人、审计记录和客户端兼容分布。
- Skill 的 slug、指令、工具、文件、权限与内容哈希组成不可拆分版本；不得由 Server 无签名地下发
  任意 Python/PowerShell 可执行代码。
- 桌面发布文档区分当前脚手架与生产状态，补齐签名产物、release manifest、stable/beta 通道、
  灰度、强制最低版本、失败回滚和 Server API 向后兼容要求。

### C. 建立 `docs/WorkBuddy/` 参考资料目录

- 将现有腾讯 WorkBuddy 高保真参考原型归档到该目录并修复仓库引用。
- 建立 README 索引，记录每条官方资料的标题、URL、来源类型、访问日期、覆盖主题和本地摘要文件。
- 保存产品设计分析：任务工作台、结果区、Skill/专家/专家团/连接器分层、自动化、远程助理、
  企业控制面、权限与审计、商业化/额度，以及对 AgentMate 的可复用结论。
- 只保存必要的事实摘要、短引用和链接，不整页复制受版权保护的官方内容；动态信息注明访问日期。

### D. 形成后续实施清单

- P0：中心停用墓碑、Skill 原子版本/权限快照、App 兼容门禁、正式 Tauri 更新服务。
- P0：真实办公交付工具（DOCX/XLSX/PPTX/PDF）、浏览器自动化、文件补丁/搜索/整理工具。
- P1：邮箱/日历/企业文档等连接器、OCR/图片/音频、深度研究与自动化结果投递。
- P2：团长调度、子任务 DAG、并行执行、审稿汇总、预算和可观察记录组成的真实多 Agent 专家团。

## 验证

- issue 与 `docs/issues/README.md` 状态一致，问题、证据、范围、非目标和后续实现边界完整。
- `docs/agentmate-实现方案.md`、`docs/agentmate-server-架构设计.md`、
  `docs/agentmate-console-管理门户设计.md`、`docs/desktop-build.md` 对同一发布模型表述一致，
  不再把 updater 脚手架或目录 CRUD 写成已完成的生产升级能力。
- `docs/WorkBuddy/README.md` 可从主题导航到本地参考原型、官方资料索引和产品设计分析；所有本地链接有效。
- 官方资料条目包含原始 URL、来源、访问日期和摘要；动态能力与商业信息明确可能随时间变化。
- 文档明确列出当前 4 个 Skill 工具、6 个内置 Skill 及真实性边界，不把纯指令 Skill 描述为已能
  生成 DOCX 或查询实时行情。
- 文档链接检查、`git diff --check` 通过；本次不修改运行时代码，不宣称上述实现缺口已经修复。

## 处理记录（2026-07-21）

- 改动：建立 `docs/WorkBuddy/`，归档高保真原型，新增官方资料索引与产品设计/AgentMate 对标分析；
  更新总实现方案、Server 架构、数据同步规范、Console 设计和桌面发布文档，统一 Tool/Skill/
  Expert/Team/Connector 分层、四条升级链路、tombstone/last-known-good、能力兼容、发布生命周期和
  Tauri 生产更新边界；README 与 issue-tracker 参考路径同步更新，旧 HTML 路径保留兼容跳转。
- 验证：PowerShell 本地链接检查确认本次 10 份 Markdown 的相对链接全部存在；新旧原型路径均可定位，
  归档原型大小 189802 bytes；`git diff --check` 通过；定向检索确认文档明确标注“目标设计/尚未实现/
  生产更新尚未上线”，没有把运行时代码缺口写成已修复。
- commit：见本次 WB-235 提交。
