---
id: WB-187
title: 按名安装取搜索首条 —— 名字不存在时静默装上无关技能，且被改名伪装成用户要的那个
severity: P2
area: backend
status: fixed
origin: 既有实现
files:
  - backend/agent/skills_store.py:311
  - backend/agent/skills_store.py:322
  - backend/agent/skills_store.py:435
  - backend/routers/skills.py:83
created: 2026-07-16
---

## 问题

`resolve_slug(query)`（[skills_store.py:311-322](../../backend/agent/skills_store.py)）在搜索无精确命中时
**无条件返回第一条搜索结果**：

```python
for it in results:
    if str(it.get("slug","")).strip() == q or str(it.get("name","")).strip() == q:
        return str(it["slug"]).strip()
return str(results[0].get("slug", "")).strip() or None   # ← 取第一条
```

`POST /api/skills/install {"name": "<任意字符串>"}`（无 slug 时，`routers/skills.py:83`）走这条路：
**只要 SkillHub 的模糊搜索回了任何东西，就装第一条**，不管它和用户要的是不是一回事。

更糟的是 `install(slug, display_name)`（`skills_store.py:435`）会用**用户传的 display_name**
覆盖 `_skillhub_meta.json` 的 `name`：

```python
"name": (display_name or fm.get("name") or slug).strip(),
```

→ 装错的技能**在「我安装的」列表里顶着用户输入的名字**，用户无从发现装错了。
这与 WB-179 的「身份」主题同源：**展示名与真实 slug 脱钩，且展示名可被调用方任意覆盖**。

## 触发场景

**实测复现**（2026-07-16，WB-185 验证时意外触发）：

```
POST /api/skills/install {"slug": "", "name": "不存在的技能xyz"}
→ HTTP 200 {"ok": true, ...}
→ ~/.agentmate/skills/self-improving-agent/ 被真实创建
→ _skillhub_meta.json = {"slug":"self-improving-agent","name":"不存在的技能xyz","version":"3.0.24"}
→ GET /api/skills 清单里显示：key=self-improving-agent, name=不存在的技能xyz
```

一个**根本不存在**的技能名，装上了一个**完全无关**的技能，并被贴上用户输入的名字。
（该目录已在验证后清理，未留在用户机器上。）

## 影响

P2。用户视角是「装了个技能，名字对得上」，实际磁盘上是另一个技能，
且它的 SKILL.md 会**真的注入进 agent 的 system prompt**（`instructions_for` 按目录名/meta 匹配）——
即用户以为在用 A 的能力，实际跑的是 B 的指令。

当前 UI 主路径大多带 slug（`SkillDetail.doInstall` 传 `data?.slug ?? target.slug`），
所以线上触发面有限；但 API 支持纯 name 安装，且 WB-180 打通 picker 后按名安装的路径会变多。

## 建议修法

1. **`resolve_slug` 去掉「取第一条」兜底**：无精确命中（slug 或 name 完全相等）→ 返回 `None`，
   让 `routers/skills.py:85` 如实报 404「SkillHub 未找到「X」」。
   模糊匹配要给用户，就走 `/api/skills/search` 让**用户自己选**，不要后端替他猜。
2. ~~**`install` 不再用 display_name 覆盖真实 name**：`_skillhub_meta.json` 的 `name`
   以 front-matter / 发布方元数据为准~~ —— **此条经实测推翻，不做**（理由见「处理记录」）：
   front-matter 的 `name` 是**包的内部机器名**，SkillHub 卡片名才是给人看的权威名。
   改以 front-matter 为准会让 UI 从「网络工程师」退化成 `my-network-skill`。
   且修好第 1 条后，误标问题**自动消失**——精确匹配后 `q` 按构造即等于真名。
3. 与 **WB-179** 一并做更彻底：loadout/安装全链路以 slug 为主键，展示名只用于渲染。

## 验证

- `py_compile` 过。
- `POST /api/skills/install {"name":"不存在的技能xyz"}` → **404**，`~/.agentmate/skills/` 无新目录。
- `POST /api/skills/install {"name":"skill-creator"}`（精确命中）→ 仍能正常安装。
- 装完后 `GET /api/skills` 里该技能的 name 是**其真实名**，不是调用方传的字符串。

## 处理记录（2026-07-16）

**只改一处**：`backend/agent/skills_store.py` `resolve_slug()` 去掉「否则取第一条」——
仅在 slug 或 name **完全相等**时返回，否则 `None`（→ 路由如实 404）。

### 建议修法第 2 条经实测推翻，未做

原计划「`_skillhub_meta.json` 的 name 改以 front-matter 为准」。实测 6 个真实已装技能后**放弃**：

| 目录 | front-matter `name` | `_skillhub_meta.json` `name` | 清单显示 |
|---|---|---|---|
| `hcieskills__skillhub` | `my-network-skill` | **网络工程师** | 网络工程师 |
| `unclecheng-reduce-ai-perception-v2` | `humanizer` | **文章去AI味工具** | 文章去AI味工具 |
| `gog` | `gog` | **Google全家桶** | Google全家桶 |

front-matter 的 `name` 是**包的内部机器名**，SkillHub 卡片名才是给人看的权威名
（`_info_from_dir:165` 的 `sh → fm` 优先级是**对的**）。改以 front-matter 为准会让 UI
从「网络工程师」退化成 `my-network-skill`，还会打断 `skill_def` 的按名匹配。

且**修好第 1 条后误标问题自动消失**：精确匹配后 `q` 按构造即等于真名/真 slug，
display_name 不再可能与实际装上的技能不符。残留的理论面（直接 API 调用
`install(slug="X", display_name="Y")` 仍可自定义标签）在 local-first 单机下无实际攻击者，
彻底解法归 WB-179（全链路 slug 主键）。

### 影响面评估（实测 38 张静态卡）

`InstallBtn` 的三个调用点里只有静态卡走「按名安装」：
- `MirrorSkillCard`（Hub 镜像，主路径）传 `card.slug || card.name` → **精确匹配 slug，不受影响**；
- `SkillDetail.doInstall` 传真 slug → 不受影响；
- `SkillHubCard`/`FeaturedCard`（静态兜底卡）传展示名 → 逐个实测 `resolve_slug`：
  **37/38 精确命中，仅 1 张变成诚实 404**。

那 1 张正是**「腾讯微云」**（用户截图里的第一张精选卡）。修复前点它的 ＋ 号会：

```
search('腾讯微云') → 1. self-improving-agent  ← 装这个
                     2. find-skills
                     3. summarize
                     4. super-weiyun-skill    ← 真正的微云技能在第 4 条
```

即**装上毫不相干的 `self-improving-agent` 并贴上「腾讯微云」的名字**，而真正的微云技能
（`super-weiyun-skill`）就在第 4 条却被跳过。修复后如实报 404「SkillHub 未找到「腾讯微云」」。
（该目录名不匹配属目录数据问题，归 WB-183/184 清理。）

### 验证

- `py_compile` 过。
- `resolve_slug('不存在的技能xyz')` → `None`（修复前 → `find-skills`）。
- 回归：`resolve_slug('humanizer')` → `humanizer`（按 slug）、`resolve_slug('Humanizer')` → `humanizer`（按 name）。
- 端到端（隔离 TestClient 打真路由）：`POST /api/skills/install {"name":"不存在的技能xyz"}`
  → **HTTP 404**「SkillHub 未找到「不存在的技能xyz」」，`~/.agentmate/skills/` **无新目录**
  （测试前后目录清单逐字相等）。
- 静态卡影响面：38 张逐个跑 `resolve_slug`，37 命中 / 1 诚实 404（如上）。

- commit：未提交（待用户确认）。
