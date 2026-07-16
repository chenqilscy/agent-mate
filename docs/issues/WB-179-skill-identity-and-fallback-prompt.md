---
id: WB-179
title: 技能身份断裂 —— loadout 存展示名 + skill_def 兜底话术伪装能力（铁律#1）
severity: P1
area: fullstack
status: open
origin: 既有实现
files:
  - backend/agent/skills.py:8
  - backend/agent/skills.py:243
  - backend/agent/skills.py:253
  - backend/agent/skills.py:262
  - backend/agent/runtime.py:280
  - backend/storage/db.py:136
  - backend/storage/db.py:507
created: 2026-07-16
---

## 问题

技能在 loadout 里以**展示名字符串**存储与传递，而真实能力按 **slug/磁盘目录名**组织，
两者无映射。`skill_def(name)`（[skills.py:253-262](../../backend/agent/skills.py)）三层回退：

1. 命中 `SKILLS` 硬编码字典（6 条，`skills.py:243-250`）→ 返回 `(instr, tools)`
2. 否则 `skills_store.instructions_for(name)` → **拿展示名去磁盘碰运气**，撞上了才注入真 SKILL.md
3. 否则 → `f"运用「{name}」技能的专长完成相关任务。"`

**第 3 层是伪装**：它让每张商品卡"看起来有效果"。`SK_GRID` 17 个技能里有 **11 个**
（NeoData金融搜索、腾讯自选股、A股全栈数据、QQ音乐助手、skill-creator、IMAP/SMTP邮件、
fbs-bookwriter、腾讯文档、QQ邮箱、腾讯新闻、创业可以学）只要磁盘上没装同名 skill，
就**只得到这一句话** —— 目录里是商品卡，后端里零能力，UI 却显示「已挂载」。

`skills.py:8-9` docstring 直白承认此设计：
*"Names match the frontend skill picker (SK_GRID); unknown names get a generic instruction so
every catalog skill still has an effect."*

相关的**过度承诺**：`catalog.ts:119` 把「Web Access（浏览器自动化）」描述为
「CDP 直连本地 Chrome，智能调度联网工具，支持登录态、并行批量操作」，
实现（`skills.py:81-91`）是**一次 `httpx.get`**。

## 触发场景

1. 不装任何技能，＋ 菜单选「腾讯自选股」，问「帮我查下腾讯今天股价」。
2. agent 的 system prompt 里出现「- 腾讯自选股：运用「腾讯自选股」技能的专长完成相关任务。」
3. 无任何工具、无任何数据源 → LLM 凭空作答或称做不到；但 UI 全程显示技能已挂载。

## 影响

P1，违反铁律#1（不硬编码、不模拟）最核心的一条：**系统主动伪装能力存在**。
用户无法区分"技能真的在工作"与"技能只是一句话"。这也是 WB-178 整个断裂的根因。

## 建议修法

1. **loadout 存 slug**：`ChatBody.skills` / `projects.skills` / `assistants.skills` 改存 slug；
   展示名只用于渲染（由目录/已装清单反查）。
2. **`skill_def` 改按 slug 解析**，去掉第 3 层兜底话术：解析不到 → **不注入 + 诚实告知**
   （SSE 里给出「技能 X 未安装/无法解析，已跳过」），宁可少一个技能也不能假装有。
3. **6 条内置技能给稳定 slug**（`web-access` / `markitdown` / `excel-csv` / …），
   与商店技能同构；定义迁库见 WB-183。
4. **存量迁移**：`projects.skills` / `assistants.skills` 里的展示名 → slug（非破坏 ALTER + 一次性迁移，
   参考 WB-104 的迁移范式）；迁不动的（对应不到任何真实技能的纯商品卡名）**直接丢弃并记日志**，
   不要留着继续走兜底。
5. **改 `catalog.ts:119` 的 Web Access 描述**，与 `web_fetch` 的真实能力一致（或在 WB-183 迁库时一并改）。

## 验证

- `py_compile` + `npx tsc --noEmit` 过。
- 选一个**未安装**的技能进 loadout → 发消息 → system prompt 里**不出现**该技能，SSE 给出诚实跳过提示；
  grep 全仓库确认「运用「」话术已删除。
- 选一个**已安装**的技能 → system prompt 里出现其真实 SKILL.md 正文。
- 迁移：造一条 `projects.skills=["Web Access（浏览器自动化）"]` 的存量记录，迁移后变为对应 slug 且仍能正常挂载。
