---
id: WB-069
title: Hub 定时镜像 SkillHub 目录（按分类）+ Hub 统一查询代理
severity: P2
area: backend
status: fixed
origin: 🆕 近期改动
files:
  - hub/skillhub_client.py
  - hub/skillhub_sync.py
  - hub/routers/catalog.py
  - hub/main.py
  - hub/db.py
  - backend/agent/skills_store.py
created: 2026-07-08
---

## 问题

SkillHub 目录当前的接入是**本地 backend 实时直连**（[[WB-064]]：`skills_store.rankings()` 跑 skillhub CLI
`skill rankings --type ...`，前端逐次拉），Hub 侧只有一张通用 `catalog_items` 表 + 人工运营 Admin（[[WB-066]]），
**没有把 SkillHub 目录自动镜像进 Hub**。诉求：让 **Hub 定时把 SkillHub 目录抓下来、按 12 个场景分类归组、
保持与 SkillHub 对外橱窗一致**，客户端从 Hub 拉镜像（离线兜底 + 团队口径一致）；同时**实时查询统一走 Hub 代理**。

## 触发场景

打开「技能」页浏览商店：现在每个客户端各自去打 skillhub.cn，离线就没有目录，团队看到的内容也不统一。
期望：Hub 有一份定时刷新的 SkillHub 镜像目录（按分类），客户端拉 Hub 即可；搜索也经 Hub。

## 实测确认的 SkillHub 真实对外接口（非臆测）

- `GET /api/v1/categories` → 12 个一级分类 `{key,name,nameEn,sortOrder,active}`（**不含每类计数**）：
  office-efficiency / content-creation / dev-programming / data-analysis / design-media / ai-agent /
  knowledge-management / business-ops / education / professional / it-ops-security / life-service。
- `GET /api/v1/showcase/{hot|featured|newest|recommended|trending|paid}` → `{section,skills,total}`，
  每条富卡带 `category/downloads/installs/stars/score/iconUrl/subCategories/verified/description_zh…`。
- `GET /api/v1/search?q=<kw>&limit=<≤100>` → `{results:[...]}`（同富字段；**limit 硬顶 100、无翻页**）。
- ~~静态全量索引 `skills.json`~~ 已废弃（返回 `{total:0}`），**不可用**。
- 网站 `/skills?category=&sortBy=&source=` 背后的浏览接口 `POST /api/v1/skills` **需鉴权（401）**，公开拿不到。

**关键约束**：公开 API **拿不到干净的严格全量**；能得到的最大集 = 6 榜单 ∪ 关键词 search。故本条口径定为
「**镜像 SkillHub 对外榜单 + 按 12 分类归组**」，数量由抓到多少决定，不是接口给死的精确计数。

## 决策（本条按此落地）

1. **Hub 抓取方式 = 复用 skillhub CLI**：Hub 服务端用自己的 Python 跑 `~/.skillhub/skills_store_cli.py`
   （不新起 HTTP 客户端）。沿用本地 [`backend/agent/skills_store.py`](../../backend/agent/skills_store.py) 里
   `_run_cli`/`_cli_env` 的硬化封装（白名单转发 env + `PYTHONUTF8=1`，**绝不透传 `LLM_API_KEY` 等**，铁律#4）。
   > 约束：CLI 只有 `skill rankings --type {6类}` 与 `search <kw>`，**无 categories 命令、search 不支持按分类过滤**。
   > 因此：分组靠榜单卡自带的 `category` 字段；12 分类的中文名/排序用一张静态映射表（源自上面实测的
   > `/api/v1/categories` 真数据快照，非编造）。
2. **全量口径 = 榜单 ∪ 分类 search 去重**：定时同步以 `rankings --type all`（6 榜单并集）为主，按 slug 去重、
   按 `category` 归到 12 类。「分类 search 补量」为**后续增强**（CLI search 仅关键词近似，非精确枚举），本期先不做。
3. **实时查询 = Hub 统一代理**：客户端「从 SkillHub 查询技能」改打 Hub 端点（Hub 内部跑 CLI `search` + 短缓存）；
   本地 backend 现有 `search()/rankings()` **降级为 Hub 不可达时的离线兜底**。

## 建议修法

- **`hub/skillhub_client.py`（新）**：从 `backend/agent/skills_store.py` 移植 `_run_cli`/`_cli_env`/`cli_available`/
  `_normalize_card`；提供 `rankings(rtype)` 与 `search(q, limit)`（跑 CLI、归一化商品卡）。CLI 路径/技能目录经
  `hub/config.py` 配置（默认 `~/.skillhub/skills_store_cli.py`）。
- **`hub/skillhub_sync.py`（新）**：`sync_once()` → 跑 `rankings --type all` → 归一 → 按 `category` 分组 + slug 去重
  → 用 12 类静态映射（key→中文名/排序）补齐骨架 → upsert 进 `catalog_items`
  （`category='skill'`、`kind='skillhub'`、`scope='builtin'`，`data` 存卡 + `skillhub_category`）。
  幂等：按 slug upsert，消失的标记禁用而非硬删（保留镜像稳定）。
- **`hub/db.py`**：需要「按 slug upsert / 批量替换某来源」的能力——加 `upsert_skillhub_items()` 之类
  （或复用 `create/update/delete_catalog_item` + 一层封装）。给 `catalog_items` 补 `source_key`（slug）便于幂等。
- **`hub/main.py`**：FastAPI lifespan 里起一个 asyncio 后台循环（间隔默认 12h，可配 `SKILLHUB_SYNC_INTERVAL`），
  启动先跑一次；**不引第三方调度依赖**。
- **`hub/routers/catalog.py`**：
  - `POST /api/catalog/skills/sync`（**平台管理员**）—— 手动触发一次同步，返回统计。
  - `GET /api/catalog/skills/search?q=&limit=` —— Hub 代理实时查询（跑 CLI `search` + 短 TTL 缓存 + 失败降级）。
  - 镜像目录复用现有 `GET /api/catalog` / `GET /api/catalog/{category}`（客户端已会 pull）。
- **降级链**：Hub 不可达/无 CLI → 客户端回退本地 `skills_store`（[[WB-064]]），保持离线全功能（铁律：local-first 回退）。

## 与既有 issue 的关系

- [[WB-064]]（本地实时 rankings/search）：浏览主源上移到「Hub 定时镜像」后，WB-064 相应**降级为离线兜底**并可收尾。
- [[WB-060]]（橱窗入库）/[[WB-066]]（目录运营 Admin）：本条复用它们的 `catalog_items` 表 + 下发/override 机制，
  只是把「技能」这一类从人工运营改为 SkillHub 自动镜像。落地时勿与其重复建表。
- 本条**只碰 `hub/` + 移植性地读 `backend/agent/skills_store.py`**，前端接线（浏览/搜索改打 Hub）与
  [[WB-067]]（App 前端接 Hub）协调，避免撞 `catalog.ts`/`ExpertsView.tsx`。

## 验证

- `POST /api/catalog/skills/sync`（管理员）返回真实统计（条数、分类分布），`GET /api/catalog/skill` 或
  `GET /api/catalog`（scope=builtin）能看到镜像卡，`category`/下载/星数与 skillhub.cn 一致、按 12 分类归组。
- `GET /api/catalog/skills/search?q=tencent` 返回 skillhub.cn 真实结果（非静态假数据）。
- Hub 后台循环启动即同步一次；断网/无 CLI 时端点明确降级而非崩溃或造假数据。
- Hub 侧 `py_compile` 通过；手动跑一次同步 + 一次代理查询确认（Hub :8100）。部署注意：Hub 主机需装 skillhub CLI + 真 Python。

## 处理记录（2026-07-08）

- **改动（Hub 侧，加法为主）**：
  - `hub/skillhub_client.py`（新）：移植 backend 的硬化 CLI 封装（白名单 env + `PYTHONUTF8`，铁律#4）；
    `rankings_all()` 跑 `skill rankings --type all` 展平 6 榜单去重（`paid` 特判 `featured_paid_skills` 键）；
    `search(q,limit)` 跑 CLI search + 120s TTL 缓存。
  - `hub/skillhub_sync.py`（新）：`SCENE_CATEGORIES`（12 类静态映射，快照自 `/api/v1/categories`）；
    `sync_once()` 归组 + 幂等替换；`run_periodic()` 后台循环。
  - `hub/db.py`：`replace_skillhub_mirror(rows)` —— 原子 delete+reinsert（只动 `scope=builtin` 且
    `kind∈{skillhub,skillhub-taxonomy}`，不碰人工运营项/org 覆盖）。
  - `hub/routers/catalog.py`：`POST /api/catalog/skills/sync`（管理员手动触发）、
    `GET /api/catalog/skills/search`（Hub 查询代理）。
  - `hub/main.py`：lifespan 起后台同步循环；`hub/config.py`：`SKILLHUB_CLI`/`SKILLHUB_WORK_DIR`/`SKILLHUB_SYNC_INTERVAL`（默认 12h）。
- **验证（全走真实 SkillHub，非模拟）**：
  - `py_compile` 全过；FastAPI TestClient 接线通过（两新路由注册、health OK、未鉴权 401）。
  - 隔离临时库跑真 `sync_once()`：镜像 **369 个技能**、覆盖全 **12 分类**（ai-agent 77 / data-analysis 59 /
    … / education 5）、taxonomy 行含 12 类中文名+计数；卡片带真实 downloads/stars/iconUrl + `skillhub_category` 归组字段。
  - **幂等**：连跑两次条数稳定（删 370 插 370，仍 369 技能 + 1 骨架），不翻倍。
  - 查询代理 `search('tencent')` 返回真实 tencent / 腾讯文档 / 腾讯会议。
- **落地时的取舍（对原计划的偏离，已确认合理）**：
  - 幂等策略用 **delete+reinsert**（单事务、抓取失败则不触库），比「按 slug upsert + 标记禁用」更简单且对
    无人工状态的 builtin 镜像行完全等价。
  - **查询代理富字段（2026-07-08 追加，用户确认要）**：代理 `search` 改为**优先直连 `/api/v1/search`**
    （带回 downloads/stars/iconUrl/category 富字段），直连失败回退 CLI `search`（字段精简）再回退缓存。
    验证 `search('tencent')` → tencent-docs 133347 下载 / 184 星 / office-efficiency / 有图标。
    这对「查询代理」偏离了「纯复用 CLI」但换来富查询体验；**镜像同步仍用 CLI `rankings`**（决策#1 不变）。
  - **前端接线**（浏览/搜索改打本地 backend、本地 backend 下行 pull Hub 镜像 + 代理搜索、Hub 不可达回退本地）
    另开 issue 交付（前端→本地 backend→Hub 的接入点在本地 backend），不在本条。
- commit：（见 git 历史，标题带 WB-069）。
