---
id: WB-179
title: 技能身份断裂 —— loadout 存展示名 + skill_def 兜底话术伪装能力（铁律#1）
severity: P1
area: fullstack
status: in-progress
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

## 处理记录（2026-07-17）

**修了「伪装」那一半（P1 核心），slug 迁移那一半 ⏸ 归 WB-183**（证据见下）。

### ✅ 删掉兜底话术 —— 系统不再假装技能生效

- `agent/skills.py` `skill_def()` 返回类型改 `tuple[str, list[Tool]] | None`，
  **删除第 3 层** `f"运用「{name}」技能的专长完成相关任务。"`。解析不到 → `None`。
- `agent/runtime.py` 只注入**真解析到**的技能；解析不到的收进 `skills_skipped`，
  **如实上报**「技能未就绪 X（未安装或已停用）」。
  - 这不是我新发明的范式 —— **照抄同函数里连接器的 `mcp_skipped`**：选了但加载不了的连接器
    早就会显示「连接器未就绪 GitHub（缺 token）」，其注释写明 *"so it isn't a silent no-op"*。
    技能此前却反其道而行：不但静默，还编一句话假装有效果。现在两者口径一致。
  - `lines` 为空时**连「# 已启用技能」段都不加**，不留空壳。
  - 「已加载 · 技能 …」只列真加载的，不再把假技能混进去谎报。

### ✅ 过度承诺的描述（`catalog.ts:118`）

「CDP 直连本地 Chrome，智能调度联网工具，支持登录态、并行批量操作」
→「联网取材：按 URL 抓取网页正文再作答，并注明来源链接」——与 `web_fetch` 的真实能力一致
（实现就是一次 `httpx.get` + SSRF 守卫）。

### ⏸ slug 迁移 deferred 归 WB-183 —— 基于实测证据，不是懒

先证伪了「展示名当身份完全不可用」这个假设：`skills_store._index()` 的 key 覆盖
`目录名 / 去 __skillhub / meta.name / meta.slug / frontmatter.name`，实测 **6 个已装技能
100% 能经 `skill_def(展示名)` 解析出真实 SKILL.md**（WB-180 已验证）。即**今天展示名是能工作的**。

再量了真实撞车面（打上游 336 条目录）：

| 撞车类型 | 实测 |
|---|---|
| 展示名重复 | **4 组**：`Agent Browser`×3（agent-browser / -clawdbot / -2）、`Tavily Search`×2、`Intiface Direct Control`×2、`ppt`×2 |
| 展示名撞上他人 slug | **1 例**：名为 `ppt` 的技能其 slug 是 `666-v2`，撞上真 slug `ppt` |

即撞车率 ≈ **1.2%（4/336）**，且要**同时装两个同名技能**才真出问题（那时 `_index()` 里
后遍历到的胜出，注入哪个取决于文件系统顺序）。

结论：**危害真实但窄，且已从「静默伪装」变成「响亮失败」**（本次修完，解析不到会明说）。
剩下的是健壮性，而它的正确归宿是 **WB-183** —— 那条本就要建 slug 主键的 `catalog_skills`、
重构 `slug → tools` 绑定；届时浏览卡自带 slug，loadout 存 slug 才是自然的，
而不是现在为迁移而迁移（要横切 `projects.skills` / `assistants.skills` / `ChatBody` /
Manager 项目配置 picker / 目录五处）。已把迁移清单挂进 WB-183。

### 验证

- `py_compile` 过；`npx tsc --noEmit`（仓库根）过。
- **单元 20 项全过**：`skill_def` 对 5 个未安装名（腾讯自选股 / NeoData金融搜索 / QQ音乐助手 /
  不存在的技能xyz / fbs-bookwriter）**全部返回 None**；6 个内置技能仍解析（工具数正确）；
  6 个已装技能仍注入真 SKILL.md（938~6017 字符）；**停用后 → None、恢复后又能解析**（无副作用）。
- **端到端 12 项全过**（打真 `run_chat`，拦在 `stream_chat` 抓真实 system_prompt + 解析真 SSE 帧）：
  - 只挂假技能 → prompt 里**无兜底话术、连「# 已启用技能」段都没有**，
    SSE：`已加载 · 技能未就绪 腾讯自选股（未安装或已停用）`；
  - 真假混挂 → `已加载 · 技能 Excel 文件处理、网络工程师 · 技能未就绪 腾讯自选股（未安装或已停用）`，
    真内置注入含其工具名 `analyze_csv`、真已装注入 SKILL.md 正文（含「路由交换」）、假的未混入；
  - 全真技能 → `已加载 · 技能 Excel 文件处理`，**无「未就绪」噪音**。
  - 测试自身加了硬守卫（抓不到 system_prompt 即判定测试失效）—— 首版就因 `run_chat` 签名传错
    而空跑，负向断言在空字符串上全部假阳性地"通过"了。

### 状态

`in-progress` —— slug 迁移归 WB-183，其余已修。

- commit：未提交（待用户确认）。
