---
id: WB-191
title: SkillHub 第三方市场缺少 Manager 集中下架策略
severity: P3
area: fullstack
status: fixed
origin: 既有实现
files:
  - console/src/SkillsPage.tsx
  - server/routers/catalog.py
  - backend/agent/skills_store.py
  - backend/routers/skills.py
created: 2026-07-17
---

## 问题

WB-190 按用户诉求把「腾讯文档」从技能侧目录清掉了，但**只有「推荐」段（`SK_GRID`，我们自己的
目录、DB 供给）真消失**；「SkillHub」段仍显示 `腾讯文档 TENCENT DOCS`。

根因：SkillHub 段的数据不是本地目录，而是**上游 skillhub.cn 商店的镜像**：
- `src/views/ExpertsView.tsx:424-427` 注释写明：有 Hub 镜像（`catalogStore.skillMirror`，已连 Hub
  并 pull）→ 用镜像的真实 369 技能；否则才回退静态 `SKILLHUB_*`。
- 本机 `HUB_URL=http://127.0.0.1:8100` 且 `catalog_downlink` 有 `skill` 369 行 → 走镜像分支，
  故 WB-190 改的静态 `SKILLHUB_GRID`（`_SHOWCASE_SKIP` 跳过、DB 0 行）**只在未接 Hub/离线时才生效**。
- 链路：skillhub.cn → `hub/skillhub_client.py:131` 镜像进 Hub → `backend/hub_sync.py:112` pull →
  `db.replace_all_downlink`（**清空重建**）→ 前端。

因此「在本地把某条镜像行删掉」不是可行解：`replace_all_downlink` 每次 pull 全量重建，
删了下次同步就复活；在 Hub 侧删同理会被下一次从上游的镜像刷新盖回。

## 触发场景

App → 技能 → SkillHub 段：仍能看到「腾讯文档 TENCENT DOCS」（369 条镜像之一），
而同页「推荐」段已无腾讯文档 —— 同一产品在同一页面下架得不一致。

## 影响

P3：不影响运行时；是「用户想在自己的 App 里不看到某个上游商店条目」的运营能力缺口。
注意这与 WB-177/189/190 性质不同：那些是**我们自己的目录数据**，可以直接删；
这里是**第三方商店的镜像**，删的语义是「本站下架/过滤」，需要一个持久化机制。

## 建议修法

需要一个**跨同步存活**的下架机制，两条路线（择一，需产品决策）：

1. **Manager 侧下架名单（推荐）**：Hub 的目录运营中心加「已下架 slug」黑名单（DB 表），
   镜像刷新时按名单过滤后再对外提供。好处：与 WB-066「Hub 目录下发覆盖本地」的既有方向一致，
   一处运营、所有客户端生效；且 Manager 本就是目录运营的位置（WB-100~102 的橱窗运营中心）。
2. **本地过滤**：本地 `showcase_all`/`skillMirror` 读一份本机 blocklist 再过滤。
   适合「只有我这台机不想看到」，但与 local-first 之外的多端不一致。

无论哪条，都要注意 `replace_all_downlink` 是幂等清空重建 —— 过滤要发生在**读出/对外提供**那一步，
而不是往镜像表里做删除（否则必被下次同步覆盖）。

## 验证

- 下架某个 slug → App 技能页 SkillHub 段不再出现该卡；
- 触发一次 Hub→上游镜像刷新 + 本地 pull → 该卡**仍不出现**（跨同步存活，这是本 issue 的关键点）；
- 未接 Hub / 离线时静态兜底路径不受影响。

## 清点记录（2026-07-21）

本条不属于技能执行链路缺口：当前 SkillHub 段忠实展示第三方商店真镜像，安装与运行链路正常。
是否在 AgentMate 侧屏蔽某个仍由上游发布的商品属于目录治理策略，需要明确选择全局下架名单或本机过滤；
在产品策略确定前标记为 deferred，不把它混入本轮 App/Server 能力打通验收。

## 决策记录（2026-07-22）

- 采用集中治理，但适配 WB-215 后的真实架构：Manager 只下发持久化 slug 下架策略，App 仍在本机直连
  SkillHub 获取商品元数据；策略在本地搜索、排行与安装入口统一执行，Server 不代理第三方正文或安装包。
- Console 提供管理界面，不要求运营人员编辑文件或 JSON；下架策略随既有目录 revision/pull 跨同步生效。

## 处理记录（2026-07-22）

- 改动：Manager 技能页新增“SkillHub 下架”管理页，平台管理员按 slug 新增/恢复策略并填写原因；Server
  对 `SKILLHUB_BLOCKLIST` 做 slug、长度与重复项校验，并纳入既有目录 revision/pull。App 保持本机直连
  SkillHub，但在搜索、排行和直接安装三条入口统一执行 last-known-good 下架策略；已安装技能不被静默删除。
- 架构纠偏：WB-215 后已不存在“Server 镜像 369 条 SkillHub 商品”的旧链路。本实现只通过 Server 下发
  治理策略，不恢复第三方正文/安装包代理，也不要求运营人员编辑文件。
- 验证：Server 策略回归 2/2、Backend 过滤与直接安装回归 2/2、Python `py_compile`、TypeScript
  `tsc -b`、Console 生产构建均通过；重复 slug、非法 `../` slug 和直接安装均 fail closed。
- commit：随本提交。
