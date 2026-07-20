---
id: WB-064
title: SkillHub 浏览列表改为实时（rankings/search），替掉硬编码的静态目录与假下载/星数
severity: P2
area: backend
status: fixed
origin: 🆕 近期改动
files:
  - src/data/catalog.ts
  - backend/routers/skills.py
  - backend/agent/skills_store.py
  - src/views/ExpertsView.tsx
created: 2026-07-07
---

## 问题

「技能」页 SkillHub 的浏览内容（精选技能 `SKILLHUB_FEATURED`、网格 `SKILLHUB_GRID`、
下载量/星数、分类）是从截图**硬编码**进 `catalog.ts` 的静态数据，下载/星数是编的——
不是实时从 SkillHub 站点获取。违反铁律#1（不模拟）。当前只有 search/install/preview 是实时的。

## 触发场景

打开技能页看到的卡片列表、下载 174k/星 109 这类数字，全是本地写死的，和 skillhub.cn 实际不同步。

## 影响

P2：导购数据不真实（假计数）；功能可用但内容陈旧/虚构。

## ⚠ 与 [[WB-060]] 的重叠（需协调，别撞车）

并发会话的 [[WB-060]]「橱窗目录入库」也在解同一症状（干掉 catalog.ts 静态商品卡），
但路线不同：WB-060 把商品卡迁到 **AgentMate 自己的 Hub DB + API**（其策展数据入库）；
本条 WB-064 是**直连 skillhub.cn 实时 rankings/search**（第三方站点真数据）。二者可能二选一，
或分层（Hub DB 做策展/离线兜底，skillhub.cn 做实时来源）。动手前先与 WB-060 对齐，避免同改
`catalog.ts` / `ExpertsView.tsx` 冲突。

## 建议修法

- SkillHub 有实时接口：`skillhub skill rankings --type {all,hot,featured,newest,recommended,trending,paid}`
  返回真实列表（name/description/description_zh/slug/version/category/subCategories/downloads/
  installs/stars/score/iconUrl/tags/verified…）；`search <q>` 按关键词/分类查。
- 后端加：`GET /api/skills/catalog?type=featured|hot|...&category=` —— 跑 CLI rankings（PYTHONUTF8=1
  避免 GBK 崩，见坑），归一化字段返回；小 TTL 缓存 + 站点不可达时回退。
- 前端：`SkillHubView`/`FeaturedSkills` 从后端拉实时目录渲染（真实下载/星数/分类/图标），
  去掉 `SKILLHUB_GRID`/`FEATURED` 静态假数据；分类从 rankings 的 category 派生。安装仍按 slug（更准）。
- 保留优雅降级：接口失败时给出「暂时无法连接 SkillHub」而非退回假数据。

## 验证

- 卡片来自实时 rankings/search（下载/星数与 skillhub.cn 一致、随 --type 变化）；分类过滤走真实 category；
  安装/预览用真实 slug；断网时明确提示而非展示假数据。明暗双主题都看。

## 处理记录（2026-07-07）· 分层方案的「skillhub.cn 实时」那一层
用户选定「分层」：Hub DB（[[WB-060]]）做策展/离线兜底 + skillhub.cn 做实时来源。
本条只交付**实时来源这一层**（加法、只碰自有文件，避免与并发在改的 WB-060 撞车）：
- 后端 `agent/skills_store.py`：`rankings(type,category,limit)` 跑 `skillhub skill rankings
  --type {featured/hot/recommended/newest/trending/all/paid}`，归一化成商品卡
  （slug/name/description/version/category/downloads/installs/stars/iconUrl/tags/verified…）+
  标记本地已安装 + 300s TTL 缓存 + 站点不可达回退缓存；`routers/skills.py` 加 `GET /api/skills/rankings`。
- 验证：模块 + HTTP live（:8000 已重启）`/api/skills/rankings?type=featured` 200，返回 skillhub.cn
  真实数据（如 tencent-docs 132082 下载/184 星，对上我此前静态的 131k/183）。

### 待办（交接给 WB-060 整合，别在本仓库这两个文件外自行乱改前端）
- 前端 `SkillHubView`/`FeaturedSkills` 改从目录层取数（WB-060 的 `/api/catalog` 消费本 `/api/skills/rankings`
  作实时源、DB 作兜底），去掉 `catalog.ts` 的 `SKILLHUB_GRID`/`FEATURED` 静态假数据。
- 分类映射：UI 中文分类 ↔ rankings 的英文 category（office-efficiency/ai-agent…）需一张映射表。
- 这两步落在 WB-060 正在改的 `catalog.ts`/`ExpertsView.tsx`，由那个会话做以免冲突。

## 处理记录（2026-07-21）

- WB-060/WB-069/WB-070/WB-071/WB-184 已完成分层整合：App 技能浏览读真实 rankings/Server 镜像，
  Server 不可达时走本机真实 rankings，静态 SkillHub 商品卡与虚构统计已移除。
- 本轮重新核对 App 目录链路，并运行技能/连接器真功能门禁：Web Access、Excel 工具均真实调用，
  共 15/15 通过；生产构建通过。原交接待办已全部落地，本条收口。
