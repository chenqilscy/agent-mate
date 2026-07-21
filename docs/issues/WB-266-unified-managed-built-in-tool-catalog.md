---
id: WB-266
title: 内置工具目录分裂且仅有四项，缺少数据库权威源与 Console 管理
severity: P1
area: fullstack
status: fixed
origin: 用户反馈
files:
  - shared/skill-tools.json:1
  - backend/agent/tools.py:1190
  - backend/agent/skills.py:469
  - server/routers/catalog.py:25
  - console/src/SkillEditor.tsx:294
  - console/src/SkillsPage.tsx:70
created: 2026-07-21
---

## 问题

Console「新增技能草稿」中的可用工具来自 `shared/skill-tools.json`，该文件只有
`web_fetch`、`html_to_markdown`、`analyze_csv`、`create_local_skill` 四项；但 App 运行时已经实现
目录/文件、Office 文档、浏览器、命令、计划、知识库、工作项和 Skill 资源等更多内置工具。
工具实现、Skill 可绑定名单、Server 校验与 Console 展示由多份代码/JSON 分别维护，目录会持续漂移。

同时，内置工具没有管理界面。运营若要调整显示名、分类、风险级别、启停、是否允许 Skill 绑定、
最低 App 版本或排序，只能修改并发布仓库文件，不符合 Server 控制平面作为目录权威源的架构。

## 触发场景

- 在 Console 新建或编辑技能，工具区始终只能看到四个选项。
- App 已实现的 `read_file`、`create_docx`、`browser_navigate` 等工具无法通过 Skill 草稿绑定。
- 调整工具启用状态或兼容策略时必须改 JSON/代码、重新部署，且没有管理审计入口。
- App/Server 任一侧新增工具后漏改另一份注册表，发布校验、能力报告与真实运行时不一致。

## 影响

P1：Skill 作者无法组合已存在的真实能力；文件式目录不可运营、不可审计、无法动态停用高风险工具；
目录漂移还会导致草稿可保存但客户端不能执行，或客户端有能力但 Console 永远不可选。

## 建议修法

1. 建立 Server 数据库 `tool_catalog` 作为工具目录和运营策略的唯一权威源；静态定义只允许用于首次
   建库 bootstrap，所有查询、校验、更新和 Console 展示必须读数据库。
2. 完整登记 App 内置工具，并区分 `skill`（可人工绑定）、`contextual`（按项目上下文自动注入）、
   `automatic`（运行时自动注入）和 `internal`（系统专用）暴露范围。
3. Console 技能管理增加「内置工具」页签，支持搜索、筛选与编辑可运营字段；实现名不可伪造创建、
   不允许删除，避免数据库声明出 App 中不存在的执行代码。
4. Skill 编辑器仅展示数据库中 `enabled && bindable` 的工具；Server 保存/发布仍做权威校验，已存在
   的系统 Skill 可保留其 internal 工具，但普通 Skill 不能新增绑定。
5. App 能力报告来自真实实现注册表；Server 发布兼容判断取数据库工具契约与客户端能力交集。
6. 删除 `shared/skill-tools.json` 的运行时依赖和过时文档，补充迁移、API、权限和回归测试。

## 验证

- Server 首次初始化后数据库包含全部内置工具，`GET /api/catalog/tools` 返回完整目录；重启不覆盖
  Console 已修改的运营字段。
- Console「内置工具」可查看并更新显示名、分类、风险、启停、可绑定、最低版本和排序；更新有审计。
- 技能编辑器展示完整的可绑定工具而非四项，禁用/非绑定/内部工具不会出现在普通选择列表。
- Server 拒绝未知、禁用或不可绑定的新工具，保留既有系统 Skill 的内部工具不会被误伤。
- App 运行时能够解析所有声明为可绑定的工具，目录契约与能力报告一致。
- Server/Backend 回归、Console/App TypeScript 类型检查和 Console 生产构建通过。

## 处理记录

- 2026-07-21：Server 新增数据库 `tool_catalog` 与 `tool_catalog_audit`；版本升级以
  `INSERT OR IGNORE` 只补充真实实现，不覆盖 Console 已管理的运营字段。目录当前登记 25 项，按
  `skill/contextual/automatic/internal` 分层，默认 16 项允许普通 Skill 绑定。
- 新增 `/api/catalog/tools` 查询、`PATCH /api/catalog/tools/{name}` 管理和审计端点；显示名、说明、
  分类、风险、启停、绑定、最低 App 版本和排序可管理，实现名、权限、契约和注入方式不可在网页伪造。
  Skill 保存/发布、权限并集、revision 和兼容检查全部改读数据库；禁用/不可绑定/未知工具 fail closed，
  既有系统 Skill 仅可保留原有 internal 工具。
- App `_TOOL_REGISTRY` 扩展到真实 base、Skill、项目、知识库和资源实现；capability report 直接枚举
  构建中的真实实现及 runtime `ask_user`，不再读取文件式目录。删除 `shared/skill-tools.json`。
- Console 技能页新增「内置工具」管理页签、搜索/分层/风险/权限/状态表格、编辑抽屉和审计；新增技能
  工具选择器从同一数据库投影获得 16 项，不再只有四项。生产静态资源已重新构建。
- 更新实现方案、Server 架构和 Console 设计，清理全量同步、Console 迁移、桌面更新等过时表述，并为
  历史 issue 补充 JSON 契约已被 WB-266 取代的说明。
- 验证：Server 工具目录 + Skill 契约定向回归 11/11、Backend Skill 回归 15/15；App 与 Console
  TypeScript 检查、`pnpm build:console`、Python 编译通过。隔离 `:8110` 真页面验证 25 项目录、16 项
  Skill 选择、管理抽屉和零 console error；隔离数据库与进程已清理。
- 全量回归发现的三项既有/并行门禁失败已另登记 WB-268，不夹带到本修复。
