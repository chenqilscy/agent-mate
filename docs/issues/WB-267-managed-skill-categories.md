---
id: WB-267
title: Skill 分类是自由文本，缺少独立分类目录与引用治理
severity: P1
area: fullstack
status: fixed
origin: 用户反馈
files:
  - console/src/SkillEditor.tsx:308
  - console/src/SkillsPage.tsx:80
  - server/routers/catalog.py:503
  - backend/storage/db.py:2579
created: 2026-07-21
---

## 问题

Skill 的 `category` 只是发布数据中的自由文本。Console 从现有 Skill 临时去重生成筛选项，App 又从推荐卡反向生成分类；Server 没有分类实体、稳定 slug、排序、启停或引用约束。

## 触发场景

平台管理员新增 Skill 时可任意输入“办公效率”“办公 效率”等近似值，系统会把它们视为不同分类；分类改名必须逐条修改 Skill，推荐位还能填写与 Skill 定义不同的分类。

## 影响

P1：分类是技能目录的核心运营维度。自由文本会持续制造重复分类、名称漂移和不可控顺序，也无法安全删除或统一调整 App/Console 的分类展示。

## 建议修法

- 在 Server 目录中建立 `SKILL_CATEGORIES` 权威分类实体，包含稳定 slug、名称、图标、说明、排序和启用状态。
- 从现有 Skill 分类幂等迁移分类实体；Skill 发布保存 `category_slug`，显示名由分类实体解析并兼容旧 `category` 数据。
- Console 增加分类管理页，并把 Skill/推荐位的自由文本改为受控选择器；推荐位优先继承 AgentMate Skill 分类。
- 删除被引用分类时拒绝操作；停用分类不再允许新绑定，但保留历史数据可读性。
- App 分类下行按分类实体顺序展示，无 Server/旧数据时继续从推荐技能安全回退。

## 验证

- 分类 CRUD、稳定 slug、排序、启停和引用删除保护均由 Server 测试覆盖。
- 旧 Skill 数据能自动获得/解析分类，新发布 Skill 使用 `category_slug`，改名后 App/Console 展示同步更新。
- Skill 与推荐位表单只允许从分类目录选择；分类管理支持新增、编辑、排序、启停与删除。
- App/Console TypeScript、生产构建通过；Console 明暗主题与窄屏交互实测通过。

## 处理记录

### 2026-07-21

- Server 新增 `SKILL_CATEGORIES` 权威目录和幂等迁移，统一稳定 slug、名称、图标、说明、排序与启停状态；兼容旧自由文本分类并为未知分类生成稳定 legacy slug。
- Skill 与推荐位发布改为受控分类引用；AgentMate 推荐位继承 Skill 分类，分类改名实时解析，停用分类拒绝新绑定，被 Skill、发布版本或推荐位引用的分类拒绝删除。
- Console 增加“分类管理”页和共享图标选择器，Skill/推荐位表单改为分类选择器；780px 窄屏表格采用横向滚动，避免分类说明逐字换行。
- App 下行按 Server 分类排序生成 `SK_CATS`，无分类目录时保留旧推荐数据回退；本机 `GET /api/catalog` 实测返回 `全部、开发编程、内容创作、办公效率、数据分析、商业运营`。
- 验证：`pnpm build` 通过；Server 分类/工具/UI 契约 10 项通过；App 分类排序与目录契约 17 项通过；Console 在 `http://127.0.0.1:8100` 完成新增、图标选择、受控选择、继承、引用保护及明暗/780px 交互验收。
- 全套 Server discover 仍有 2 条与本项无关的既有契约漂移，已由 WB-268 单独跟踪；WB-267 定向回归全部通过。
