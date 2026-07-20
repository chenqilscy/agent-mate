---
id: WB-215
title: SkillHub 错误由 Server 集中管理，未安装技能可读取文件内容
severity: P1
area: fullstack
status: fixed
origin: 产品边界复查
files:
  - backend/routers/skills.py
  - backend/agent/skills_store.py
  - backend/server_client.py
  - backend/server_sync.py
  - src/stores/catalogStore.ts
  - src/views/ExpertsView.tsx
  - src/components/skill/SkillDetail.tsx
  - server/main.py
  - server/routers/catalog.py
created: 2026-07-20
---

## 问题

第三方 SkillHub 商店目前被当作 AgentMate Server 的集中目录：Server 周期同步榜单、代理搜索/排行/安装前预览，App 再从 Server 下行镜像并优先消费。这把机器级、本地安装的能力市场错误地变成了组织控制平面数据，也导致 App 是否能浏览 SkillHub 与 Server 登录、同步状态耦合。

同时，未安装技能详情会调用 `/api/skills/preview`，临时下载技能包并读取 `SKILL.md`、源码和 references。用户尚未安装技能时就能读取其文件内容，破坏了“商店描述 → 安装 → 本地文件”的生命周期边界。

## 触发场景

1. 连接 Server 后打开“技能 / SkillHub”，列表优先来自 Server 镜像或 Server 代理。
2. 点击任意未安装技能，App 会临时下载包并展示完整 `SKILL.md` 与引用文件列表。

## 影响

P1：Server 与 App 职责倒置，第三方目录产生重复存储、定时同步、代理、精选运营和历史数据清理成本；未安装即读取包内容也让安装语义失真，后续权限、审计与内容安全边界难以收敛。

## 建议修法

- AgentMate Server 仅保留 AgentMate 自有推荐技能定义，不再同步、代理或精选第三方 SkillHub 数据。
- App 后端直接查询 SkillHub 搜索与排行，并在本机完成安装；Server 登录状态不影响第三方市场浏览。
- 未安装详情仅使用列表返回的名称、描述、版本、分类、下载量等商店元数据，不下载技能包、不展示源码与 references。
- 安装成功后再读取本地技能目录，开放 `SKILL.md` 预览/源码、references、打开文件夹、启停与卸载。
- 清理旧 Server SkillHub 路由、周期任务、配置与 App 代理代码，阻止旧镜像继续下行。

## 验证

- 未连接 Server 时 SkillHub 搜索、排行与安装仍可用，响应来源明确为本地 App。
- 未安装详情不请求 `/api/skills/preview`，页面无源码切换、references 或 SKILL.md 内容。
- 安装后同一详情切换为本地完整详情，文件内容、打开目录、启停与卸载均可用。
- Server OpenAPI 不再暴露 SkillHub 同步/搜索/排行/预览接口，也不启动周期同步任务。
- 明暗主题与窄屏无溢出；前后端类型检查、构建和相关回归通过。

## 处理记录（2026-07-20）

- Server 删除第三方 SkillHub 定时同步、HTTP/CLI 客户端、查询/排行/预览代理、市场 Key 设置路由及 Console 同步/精选界面；启动迁移会清理旧镜像、分类、精选和凭据。
- Server 继续管理 `APP_SKILLS`（AgentMate 自有推荐定义），Console 技能页只保留推荐目录预览与管理。
- App 的 `/api/skills/search`、`/api/skills/rankings` 固定由本地 backend 直接访问 SkillHub，响应标记 `source=app`；Server 登录与下行同步不再影响第三方市场。
- App 下行过滤历史 `skill`、`skill-category`、`SKILLHUB_FEATURED` 分类，前端目录状态从 `skillMirror` 收敛为本地 `skillMarketplace`，移除 Server 精选区。
- 删除安装前 `/api/skills/preview` 和临时下载/缓存实现。未安装详情直接使用列表卡片元数据，隐藏 SKILL.md、源码切换和 references；安装成功后才读取本地完整详情。
- 同步更新 Server/Console 架构文档，并新增 WB-215 回归门禁。

### 验证结果

- `python -m unittest backend.tests.regression.test_skill_market_boundary backend.tests.regression.test_skill_catalog_contract backend.tests.regression.test_skill_import`：11/11 通过。
- `npx tsc --noEmit`、`npx vite build`、变更 Python 文件 `py_compile`、Console 内联脚本语法检查均通过；构建仅保留既有大 chunk 提示。
- 硬重启 Server `:8100` 与 App backend `:8101`；App frontend `:8102` 正常监听。
- 真 API：Server OpenAPI 无 `/catalog/skills/*`；旧 `/api/skills/preview` 返回 404；本地搜索返回 `source=app`，结果无 `markdown`/`references` 字段。
- 真安装：临时安装 `kdocs-skill` 后，本地详情返回 `installed=true`、SKILL.md 10207 字符、12 个 references 和真实目录；随后卸载，已安装清单恢复为 0。
- CDP 真浏览器：未安装详情仅显示商店描述、分类、下载/收藏和安装提示，`.skd-viewtoggle=0`；1440×900 明暗主题均无横向溢出。
