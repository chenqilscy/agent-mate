---
id: WB-217
title: 技能定义与推荐位配置耦合，推荐内容无法独立运营
severity: P1
area: fullstack
status: fixed
origin: 产品架构复查
files:
  - server/catalog_seed.py
  - server/db.py
  - server/routers/catalog.py
  - server/web/console.html
  - backend/server_sync.py
  - backend/storage/db.py
  - src/data/catalog.ts
  - src/stores/catalogStore.ts
  - src/views/ExpertsView.tsx
created: 2026-07-20
---

## 问题

“推荐”Tab 直接展示全部 `APP_SKILLS` 技能定义，Server Console 也把技能定义列表同时当作推荐列表。技能定义与推荐位是一对多且生命周期不同的两类数据：前者描述可安装的 AgentMate 技能，后者决定某个位置在某段时间展示哪些 AgentMate 或第三方 SkillHub 技能。当前耦合导致运营无法独立配置推荐顺序、上下架和生效时间，也无法在不复制第三方技能包的前提下推荐 SkillHub 技能。

## 触发场景

1. 在 Server Console 新建或启用任意 `APP_SKILLS` 技能定义，该技能自动出现在 App“推荐”Tab。
2. 想只推荐部分技能、调整推荐顺序或设置生效时间时，没有独立配置入口。
3. 想推荐 SkillHub 技能时，只能错误地把第三方商店元数据再次集中到 Server。

## 影响

P1：Server 的运营控制平面职责不完整，技能定义变更会意外改变推荐内容；App 推荐只能等同“全部自有技能”，无法做人工精选和排期，也容易重新引入 WB-215 已清理的第三方商店镜像与 Key 集中管理技术债务。

## 建议修法

- 在 Server 目录中增加独立 `SKILL_RECOMMENDATIONS` 推荐位配置，保存技能来源、slug、推荐位置、编辑文案、排序、启停和生效时间。
- AgentMate 自有推荐引用 `APP_SKILLS.slug`；SkillHub 推荐只保存 slug 与展示元数据指针，不同步技能包、商店榜单或 SkillHub Key。
- Server Console 增加推荐位 CRUD 与状态管理，技能定义管理继续只负责可安装技能定义。
- App 通过现有 Server 下行链路缓存推荐位；在线使用 Server 配置，离线无配置时回退本地 AgentMate 技能定义。
- 推荐卡统一复用真实本地安装生命周期，Server 不参与下载、安装、文件读取或执行。

## 验证

- Console 可创建、编辑、排序、启停和删除 AgentMate / SkillHub 推荐位，并校验引用与排期。
- App“推荐”Tab 按 Server 推荐位渲染，不再默认等同全部 `APP_SKILLS`；未生效、已过期和停用项不展示。
- 无 Server、Server 不可达或尚无推荐配置时，App 保留本地离线兜底且不白屏。
- SkillHub 推荐仍由 App 本机安装，Server 无 SkillHub Key、技能包和文件内容。
- Server/API 回归、前后端检查、明暗主题与窄屏验证通过。

## 处理记录（2026-07-20）

- 在 Server 既有 `catalog_items` 中新增独立 `SKILL_RECOMMENDATIONS` 类型，支持 `agentmate` / `skillhub` 来源、稳定 slug、推荐位置、编辑文案、排序、启停与起止时间；同推荐位去重并保护被引用的 AgentMate 技能定义不被改 slug 或删除。
- Server 首次启动写入 6 条产品随附的 AgentMate 技能定义，并一次性迁移成 6 条显式推荐位；迁移带版本标记，运营主动删空后不会重建。
- Console 技能页拆出“推荐位管理”，支持创建、编辑、启停、删除和排期；目录预览只显示当前生效项。SkillHub 表单明确只保存 slug 和展示文案，不接触 Key、榜单、技能包或文件内容。
- App 沿用全量目录下行缓存，新增 `SK_RECOMMENDATIONS` 归一化输出；未配置时回退本机技能定义，已配置但全停用时保持空态，排期外、停用、引用失效项不会展示。
- 推荐页改为消费独立推荐位；AgentMate 与 SkillHub 推荐均复用本地真实安装、已安装管理与安装后文件查看流程。
- 同步更新 Server / Console 架构文档，并补充 Server 验证、迁移、停用空态及 App 下行/排期回归。

### 验证结果

- `python -m unittest backend.tests.regression.test_skill_catalog_contract backend.tests.regression.test_skill_market_boundary backend.tests.regression.test_skill_import`：13/13 通过；`server/tests/test_skill_recommendations.py`：4/4 通过。
- `npx tsc --noEmit`、`npx vite build`、变更 Python 文件 `py_compile`、Console 内联脚本语法检查与 `git diff --check` 通过；构建仅保留既有的大 chunk 提示。
- 硬重启 Server `:8100`、App backend `:8101` 和 App frontend `:8102`；Server 真库包含 `APP_SKILLS=6`、`SKILL_RECOMMENDATIONS=6`，App pull 下行 13 条目录项与 6 条技能定义。
- 真 API 临时创建 SkillHub 推荐位后 App 可见，停用后立即隐藏，删除并再次 pull 后恢复原数据；临时推荐位已清理。
- 真浏览器：Console 显示 6 条生效推荐位与完整管理表单；App 推荐页显示 6 张统一安装卡，1280px 明暗主题均无横向溢出。验证后恢复深色主题，临时 Console 管理员账号已清理。
