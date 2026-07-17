---
id: WB-183
title: 技能目录/定义未入库 —— WB-059 漏项：专家人格与连接器进了 DB，技能仍硬编码在 skills.py
severity: P2
area: fullstack
status: open
origin: 🏚 迁移遗留
files:
  - backend/agent/skills.py:243
  - backend/storage/db.py:252
  - backend/storage/db.py:34
  - backend/storage/catalog_showcase.json
  - docs/workbuddy-hub-架构设计.md:114
  - hub/skillhub_sync.py:22
created: 2026-07-16
---

## 问题

WB-059「目录真定义入库」把内置**专家人格** → `catalog_experts`、**连接器注册表** → `catalog_connectors`
迁进了 DB（`db.py:252-290`），**唯独技能被漏掉**：

- 6 条内置技能的定义（instructions + 工具包绑定）仍**硬编码**在
  [skills.py:243-250](../../backend/agent/skills.py) 的 Python dict 里。
- [架构设计文档:114-117](../workbuddy-hub-架构设计.md) 设计过的表**从未建**：
  ```
  catalog_skills  -- 技能橱窗目录（SK_GRID/SKILLHUB_*）
    id, slug, name, label, color, description, category,
    downloads, stars, badge, source, featured bool, kit_id, ...
  ```
- 结果：**改一个专家的人格改数据（Manager 里点几下），改一个技能的提示词要改代码重启**。

连带的**孤儿数据**：`db.py:34` 的 `_SHOWCASE_SKIP = {SKILLHUB_GRID, SKILLHUB_FEATURED,
SKILLHUB_KITS, SKILLHUB_CATS}` 让 `catalog_showcase.json` 里 **38+8+4+13 = 63 条**永不入 App DB。
注释说「交给 WB-064」，而 WB-064 落地成了 `rankings` 端点（走的另一条路），这 63 条遂成孤儿。

**双份硬编码**：SkillHub 的 12 个一级分类映射在 `hub/skillhub_sync.py:22-36`（2026-07-08 手工快照）
和 `src/stores/catalogStore.ts:17-22`（同样的快照）**各抄了一份**，分类改名会两边一起静默错分。

## 触发场景

想把内置技能「Excel 文件处理」的提示词改一个字 → 必须改 `backend/agent/skills.py` → 重启后端 →
且该改动无法由 Manager 运营下发给任何用户。对比：改专家人格在 Manager 点两下即可。

## 影响

P2。不阻塞使用，但它是 WB-179 身份统一的**前置**（slug ↔ 定义的映射得有个权威存放处），
也是「能力定义入库」这条主线（WB-058 epic）唯一未完成的缺口。

## 建议修法

1. **App 侧建 `catalog_skills`**（照抄 `catalog_experts` 范式，`db.py:252` 附近）：
   主键 **slug**，含 name/description/category/source/builtin/featured 等；
   6 条内置技能 seed 入库（工具包仍在代码里，**按 slug 绑定** —— 同连接器的 launch spec 范式）。
2. **`skill_def` 改读库**（配合 WB-179 按 slug 解析），代码里只留 `slug → tools` 的绑定表。
3. **Hub 侧**：`catalog_items` 已有 `category='skill'`（SkillHub 镜像）；补技能目录的运营 CRUD
   （复用 WB-084/100/102 的橱窗 + 目录管理范式），经 `catalog_downlink` 下发。
4. **清理孤儿**：`_SHOWCASE_SKIP` 的 63 条静态数据随 WB-184 的数据源收敛一并删除，
   `_SHOWCASE_SKIP` 机制本身可移除。
5. **分类映射去重**：`catalogStore.ts:17-22` 的快照删掉，改从 Hub 下发的 `skill-category` 取；
   `hub/skillhub_sync.py:22-36` 保留为 Hub 侧唯一来源（并加注释说明它是快照、需人工维护）。

6. **一并做 WB-179 deferred 过来的 slug 迁移**（它等的也是本条 —— 有了 slug 主键的
   `catalog_skills`，浏览卡自带 slug，loadout 存 slug 才自然）：
   - `ChatBody.skills` / `projects.skills` / `assistants.skills` 改存 slug，展示名只用于渲染；
   - 存量迁移（展示名 → slug，非破坏 ALTER + 一次性迁移，参考 WB-104 范式）；对应不到任何
     真实技能的纯商品卡名**直接丢弃并记日志**；
   - Manager 项目配置 picker（WB-080）随之改传 slug；
   - `install()` 的 `display_name` 覆盖 `_skillhub_meta.json` 的 `name`（WB-187 未做的那半）
     届时一并收口：身份走 slug，展示名只是展示名。
   - **实测撞车证据**（WB-179 打上游 336 条目录量的，不是理论担忧）：展示名重复 **4 组**
     （`Agent Browser`×3 / `Tavily Search`×2 / `Intiface Direct Control`×2 / `ppt`×2），
     另有 1 例展示名撞上他人 slug（名为 `ppt` 者其 slug 是 `666-v2`，撞真 slug `ppt`）。
     撞车率 ≈1.2%，需同时装两个同名技能才触发 —— 届时 `_index()` 里后遍历到的胜出，
     注入哪个取决于文件系统顺序。

7. **一并做 WB-186 deferred 过来的两项**（它们等的就是本条的重构）：
   - 给 `Tool` 加 `readonly` 标记（默认 `False` = 保守），`runtime.py:418` 的 `skill_tools`
     也过 plan 过滤 —— 现状是 `skill_tools` 完全绕过 `base_tools(plan)`，**没有机制表达某个
     技能工具是否 plan-safe**。今天 3 个技能工具恰好全只读（`web_fetch`/`html_to_markdown`
     是 GET、`analyze_csv` 是本地读）所以无实害，但技能定义一旦可运营就会暴雷。
   - `runtime.py:427` 的 `schemas` 改从已去重的 `active_tools.values()` 生成（今天技能工具与
     base 工具无重名，可运营后重名风险上升）。

**注意复活陷阱**（WB-176 教训）：前端静态兜底 / 后端种子 / 运行库三层要同步改。

## 验证

- `py_compile` + `npx tsc --noEmit` 过。
- DB 里 `SELECT slug,name FROM catalog_skills` 出 6 条内置；改库里某条的 description →
  重启后 App 技能页/system prompt 反映新值，**未改任何 .py**。
- Manager 改一条技能目录 → App `POST /api/hub/pull` → 前端拉到新值。
- grep 确认 `SCENE_NAME` 快照在前端已删、`_SHOWCASE_SKIP` 的 63 条孤儿已清。
