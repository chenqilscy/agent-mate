---
id: WB-191
title: SkillHub 段展示的是上游商店镜像，本地目录下架对它无效（想下架某条需 Manager 侧持久化过滤）
severity: P3
area: fullstack
status: open
origin: 既有实现
files:
  - src/views/ExpertsView.tsx:424
  - backend/storage/db.py:1433
  - backend/hub_sync.py:112
  - hub/skillhub_client.py:131
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
