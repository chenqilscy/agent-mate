---
id: WB-186
title: 技能后端一致性尾集 —— plan 模式不约束技能工具 / rankings 绕过 Manager 违反 WB-130 / 预览缓存无 TTL / schema 不去重
severity: P3
area: backend
status: fixed
origin: 既有实现
files:
  - backend/agent/runtime.py:418
  - backend/agent/runtime.py:427
  - backend/agent/skills_store.py:360
  - backend/agent/skills_store.py:220
  - backend/agent/skills_store.py:369
  - backend/routers/skills.py:45
created: 2026-07-16
---

## 问题

一组独立的中低危一致性项（同 WB-160 的尾集范式）：

1. **`runtime.py:418` plan 模式约束不住技能工具（P2）**：
   ```python
   tools_list = base_tools(plan) + skill_tools + wi_tools + kb_tools
   ```
   `base_tools(plan)` 只对**基础工具**做 plan 过滤（`tools.py:544-545` 的 `_PLAN_TOOLS`），
   `skill_tools` **直接拼接、不受 plan 约束** → 只读规划模式下 `web_fetch` / `html_to_markdown`
   **照样发出网请求**。plan 模式的"只读"承诺对技能工具不成立。

2. **`skills_store.py:360-398` + `routers/skills.py:45-49` rankings 绕过 Manager（P3）**：
   `/api/skills/rankings` 走**本地 CLI 直连 skillhub.cn**，与同文件 `search`/`preview` 遵循的
   **WB-130「App 不直连 SkillHub，统一经 Manager」原则自相矛盾**。Hub 侧无对应 rankings 代理端点。

3. **`skills_store.py:220-221, 250-252` 预览缓存无 TTL（P3）**：
   `_preview_cache` 只在 `len > 64` 时整体 `clear()`，**无过期**。技能发新版后本进程永远返回旧预览。
   Hub 侧同名缓存有 `_PREVIEW_TTL = 300`（`hub/skillhub_client.py:260`）—— **两侧不一致**。

4. **`runtime.py:427-428` schema 不去重（P3）**：
   `active_tools`（L419）用 dict 按名去重，但 `schemas = [t.schema() for t in tools_list]`
   **不去重** → 技能工具与 base 工具重名时会向 LLM 发两份同名 schema。
   当前 3 个技能工具名无冲突，但无防护；WB-183 让技能定义可运营后，重名风险上升。

5. **`skills_store.py:369-372` 冗余（P3）**：`items = cached[1] if cached else []`
   在 `elif`/`else` 两分支重复写了两遍，可合并。

## 触发场景

1. plan（只读规划）模式下挂载「Web Access」技能 → 提问 → agent 调 `web_fetch` → **真发了出网请求**。
3. 预览某技能 → SkillHub 上该技能发新版 → 再次预览 → 仍是旧 SKILL.md，除非重启后端。

## 影响

P3（第 1 项本身接近 P2）。各自独立、中低危，合并为一组一致性修。
第 1 项是**行为承诺缺口**（plan 模式说只读却能出网），修复优先级最高。

## 建议修法

1. 技能工具也过 plan 过滤：给 `Tool` 加 `readonly: bool`（或复用 `_PLAN_TOOLS` 白名单机制），
   plan 模式下只保留只读技能工具；`analyze_csv`（纯本地读）可放行，
   `web_fetch`/`html_to_markdown`（出网）在 plan 下过滤掉。
2. Hub 加 rankings 代理端点（照抄 `catalog/skills/search` 范式），App 改为「Hub 优先 → 本地 CLI 兜底」，
   与 `search`/`preview` 口径统一（补完 WB-130）。
3. `_preview_cache` 加 `TTL = 300`，与 Hub 侧对齐。
4. `schemas` 改从 `active_tools.values()` 生成（已去重），或显式按 name 去重。
5. 合并那两行重复。

## 验证

- `py_compile` 过。
- plan 模式挂 Web Access 提问 → SSE trace 里**无 `web_fetch` 调用**；agent 模式下仍可调。
- 断开 Hub → rankings 仍能出内容（CLI 兜底）；接上 Hub → 走 Hub 代理（日志/抓包确认）。
- 预览缓存：mock 一次预览 → 等 TTL 过 → 再次预览确认重新取数。
- 造一个与 base 工具重名的技能工具 → 确认发给 LLM 的 schemas 只有一份。

## 处理记录（2026-07-16）

5 项中**修 3 项（2/3/5）**，**第 1、4 项 ⏸ deferred**（理由见下）。

### ⏸ 第 1 项的前提被推翻 —— 原描述有误，在此更正

原文写「plan 模式的『只读』承诺对技能工具不成立」，**这个判断是错的**。查了 plan 模式的
实际契约，三处注释口径一致：

- `runtime.py:52` —— "Plan mode (spec 5.3): plan, don't execute."
- `runtime.py:290` —— "Plan mode is read-only, so it only gets the viewing tool."
- `tools.py:551` —— "Plan mode = read-only tools + ask_user (**no write_file / run_command**)."

`web_fetch` / `html_to_markdown` 是 **HTTP GET = 读**，不执行、不改任何状态，既不是
`write_file` 也不是 `run_command` —— **它们在 plan 模式下可用是符合契约的**。反过来把它们
过滤掉才是错的：规划时查不了资料，规划质量更差。

实测确认今天**零实害**：
```
skill 工具 = {web_fetch, html_to_markdown, analyze_csv}  ← 全是只读
base 工具  = {list_dir, read_file, run_command, update_plan, write_file}
交集 = 空                                                  ← 第 4 项今天也不会重复发 schema
```

**真实的缺口是结构性的**：`skill_tools` 完全绕过 plan 过滤，**没有任何机制表达某个技能
工具是否 plan-safe**。今天恰好 3 个都只读所以没暴雷；一旦有会写/会执行的技能工具落地，
就会静默地在 plan 模式下跑起来，破坏「plan, don't execute」。

**故 deferred，归入 WB-183**：那条 issue 本就要把技能定义迁进 `catalog_skills`、重构
`slug → tools` 绑定，届时给 `Tool` 加 `readonly` 标记（默认 False = 保守）才真正有用武之地。
现在单独做是个**行为上的 no-op**，却要动 `runtime.py`/`tools.py` —— 而这两个文件正被并发
会话（WB-177/188 WeKnora）占用，为一个 no-op 去争用文件不划算。第 4 项（schema 去重）同理：
今天无重名，随 WB-183 一并做。

### ✅ 第 2 项：rankings 补齐 Manager 代理（含 Hub 侧）

`/api/skills/rankings` 原先**绕过 Manager 直连 skillhub.cn**（本地 CLI），与同文件
`search`/`preview` 遵循的 WB-130 口径自相矛盾，且 Hub 侧压根没有对应端点。

- `hub/skillhub_client.py` 加 `rankings(rtype, limit)` —— 按榜单类型直连
  `showcase/{rtype}`（复用既有 `_normalize_card`/`_stored_key`），失败回退 `_cli_rankings()`，
  300s TTL 缓存；`all` 走既有 `rankings_all()`。
- `hub/routers/catalog.py` 加 `GET /catalog/skills/rankings`（放在 `{slug}/preview` 之前，避免路由歧义）。
- `backend/hub_client.py` 加 `skill_rankings()`，与 `search_skillhub`/`skill_preview` 同范式。
- `backend/routers/skills.py` 改「Hub 优先 → 本地 CLI 兜底」，返回 `source` 字段。
- `backend/agent/skills_store.py` 把「标记已安装 + 分类过滤 + 截断」抽成 `decorate_cards()`
  —— **「已安装」是本机磁盘的知识，Manager 给不出来**，所以经 Hub 取回的榜单也要过这一步。

**顺带的实际收益**：Hub 走 HTTP showcase **无需 CLI**（WB-094），而 App 侧 `rankings()` 被
`cli_available()` 卡着。所以本机没装 skillhub CLI 的用户此前 rankings **一条都拿不到**，
只能吃前端的静态假数据；现在能拿到真实榜单（正面响应铁律#1）。

### ✅ 第 3 项：预览缓存加 TTL

`_preview_cache` 从 `{slug: detail}` 改为 `{slug: (ts, detail)}` + `_PREVIEW_TTL = 300.0`，
与 `hub/skillhub_client.py:_PREVIEW_TTL` 对齐（此前 App 侧无过期，技能发新版后本进程
永远返回旧预览）。`> 64` 的整体封顶保留。

### ✅ 第 5 项：合并冗余分支

`rankings()` 里 `items = cached[1] if cached else []` 原在 `elif`/`else` 两分支重复写，
提到前面一次赋值（兼作缓存命中 / CLI 缺失 / 取数失败三种情况的兜底）。

### 验证

- `py_compile` 过（`skills_store.py` / `routers/skills.py` / `hub_client.py` /
  `hub/skillhub_client.py` / `hub/routers/catalog.py`）。
- **Hub 侧真连 skillhub.cn**：`rankings('hot'/'featured'/'newest'/'paid')` 各取到真实卡；
  `rankings('all')` → 338 条（6 榜并集）；非法 type 回落 featured；二次调用 0.0ms（TTL 缓存命中）。
- **App 侧隔离 TestClient 打真路由**（未重启共享 :8000）16 项断言全过：
  - 第 5 项回归：本地 CLI 路径仍出真实卡、`installed` 标记在、`limit`/`category` 过滤生效、非法 type 回落；
  - 第 3 项：TTL 内命中缓存、过期后不再返回陈旧值；
  - 第 2 项：未接 Hub → `source=local`；接 Hub 有果 → `source=hub` **且仍被本机加工出 installed**
    （已装的 `github` 标 True、未装的标 False）；接 Hub 无果 → 回退 `source=local`；
    Hub 路径的 `category` 过滤能命中也能滤空。

## 处理记录（2026-07-17）· 第 1、4 项收尾

deferred 的两项做完了（WB-183 Phase A 的 `_TOOL_REGISTRY` 一落地，加标记的位置就有了）。
**而且第 1 项挖出了一个比技能侧严重得多的真 live bug** —— 见下。

### ✅ 第 1 项：plan 过滤统一到 `Tool.plan_safe`

- `agent/tools.py` 的 `Tool` 加 `plan_safe: bool = False`（**默认 False = 保守**：新工具不标注
  就进不了 plan 模式）；新增 `plan_filter(tools, plan)` 供**非 base** 工具集复用。
- `base_tools(plan)` 改按 `plan_safe` 过滤；`_PLAN_TOOLS` 名单**保留为一致性断言**
  （建表期 `assert (name in _PLAN_TOOLS) == plan_safe`），防止日后改一处忘另一处。
- 标注：`list_dir`/`read_file` 只读 → True；`update_plan` → True（它写的是待办清单本身，
  正是计划模式要产出的东西）；`write_file`/`run_command` → False（既有承诺）。
  技能侧 `web_fetch`/`html_to_markdown`（HTTP GET）/`analyze_csv`（沙箱内读）→ True。

### 🔴 顺带堵掉的真 live bug：**计划模式能写知识库**

建这个机制时发现 `kb_tools` 和 `skill_tools` **一样绕过 plan 过滤**，而它里面的
**`knowledge_add` 是写**（把文件灌进知识库 + 触发 WeKnora 解析/切片/向量化）——
即**计划模式下 agent 真能调它改知识库**，直接违反「plan, don't execute」。

技能侧那个是理论问题（3 个工具恰好全只读，本 issue 前面已实证「今天零实害」）；
**知识库侧是真的**。修复前后的 schema 对照（端到端抓 `run_chat` 真发给 LLM 的 tools）：

```
exec 模式: [list_dir, read_file, write_file, run_command, update_plan, knowledge_add, ask_user]
plan 模式（修复前）: … knowledge_add 也在 ←
plan 模式（修复后）: [list_dir, read_file, update_plan, ask_user]  ✓
```

修法就是这个机制本身：`knowledge_retrieve`（检索=读）标 `plan_safe=True`，
`knowledge_add` 保持默认 `False`，`runtime.py` 对 `skill_tools`/`kb_tools` 都过 `plan_filter`。
**没另开 issue**：它与本项同根同修（同一处绕过、同一个机制堵），拆开就得先发一个明知留着
洞的机制。

### ✅ 第 4 项：schema 去重

`schemas` 改从 **`active_tools.values()`**（已按名去重）生成，而非 `tools_list`。
`run_tool` 本来就只认 `active_tools` 里的那个，所以重名时发两份 schema 纯属误导 LLM。

### 验证（18 项全过）

- `py_compile` 过（含 `tools.py` 的建表期一致性断言）。
- **未改变既有行为**：`base_tools(True)` 仍是 `[list_dir, read_file, update_plan]`、
  `base_tools(False)` 仍是全部 5 个。
- **端到端**（打真 `run_chat`，抓真实发给 LLM 的 tool schemas）：
  - exec 模式给全套（含 `write_file`/`run_command`/`web_fetch`/`knowledge_add`）；
  - plan 模式**无** `write_file`/`run_command`（既有承诺没破），**仍给** `web_fetch`
    （GET=读，规划要查资料 —— 滤掉反而让规划变差）；
  - **plan 模式不再给 `knowledge_add`**（修复前它在）。
- **去重**：造一个与 base 工具 `read_file` 重名的技能工具（塞进 `_TOOL_REGISTRY` + 改库里
  `word-doc` 的 tools）→ 发给 LLM 的 schemas 里 `read_file` 只有 **1 份**。

### 状态

`fixed` —— 5 项全部了结（2/3/5 于先前一轮，1/4 于本轮）。

- commit：未提交（待用户确认）。
