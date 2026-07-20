---
id: WB-178
title: 技能子系统重构 —— 以 slug 为主键焊死「橱窗/loadout/磁盘」三层（总纲/epic）
severity: P1
area: fullstack
status: open
origin: 既有实现
files:
  - src/views/ExpertsView.tsx
  - src/data/catalog.ts
  - src/components/project/NewProjectModal.tsx:215
  - backend/agent/skills.py:243
  - backend/agent/skills_store.py
  - hub/skillhub_sync.py
created: 2026-07-16
---

## 问题

2026-07-16 对技能功能做了一次从头审查（前端 + 后端 + Hub 三路），结论：
**技能是两套互不相认的系统贴在一起**。

- **真的那套**：`skills_store.py` 对 `~/.agentmate/skills/` 的磁盘扫描/安装/启停 + SkillHub CLI 拉包
  + 真实 SKILL.md 正文注入 + 3 个真跑的工具（`web_fetch`/`analyze_csv`/`html_to_markdown`，带真 SSRF 防护）。
- **橱窗那套**：`catalog.ts` 的静态商品卡（`SK_GRID` 17 条 / `SKILLHUB_GRID` 39 条 / `SKILLHUB_KITS` 4 条），
  多数后端零能力。

两者之间**没有 ID 接缝**——只靠「展示名恰好撞上磁盘目录名」连通，撞不上时后端
[skills.py:262](../../backend/agent/skills.py) 编一句「运用「XX」技能的专长完成相关任务」**假装有效果**。
`skills.py:8-9` 的 docstring 把这个设计直接写明：*"unknown names get a generic instruction so every
catalog skill still has an effect"* —— **模拟行为被写进了架构注释**，与铁律#1 正面冲突。

### 根因：技能没有稳定身份

同一个技能在三层有三种身份：

| 层 | 身份 | 例 |
|---|---|---|
| 橱窗卡 | 展示名（三元组 `[icon,name,desc]` 第 2 项） | `腾讯微云` |
| 会话/项目 loadout | 展示名字符串 | `projects.skills = ["腾讯微云"]` |
| 磁盘/安装 | slug 目录名 | `~/.agentmate/skills/tencent-weiyun__skillhub/` |

由此长出的断裂已拆为子任务 **WB-179 ~ WB-186**。

## 触发场景

装一个 SkillHub 技能 → 回首页点 ＋ 菜单 → **列表里找不到它**（只有 17 张静态卡）；
随手选一张静态卡（如「腾讯自选股」）→ 发消息 → agent 收到的只有一句兜底话术，
但 UI 显示「技能：腾讯自选股」已挂载。

## 影响

P1。这是技能功能的**结构性问题**，不是若干个 bug：装机流程与使用流程是断开的两条路，
且系统会主动伪装能力存在。继续在橱窗上打补丁只会加深断裂。

## 建议修法

以 slug 为主键把三层焊死，分子任务推进（范围含 Hub/Manager 侧）：

| 子任务 | 内容 |
|---|---|
| **WB-179** | 身份统一：loadout 存 slug + 删兜底话术 + 存量迁移（根因） |
| **WB-180** | ＋菜单改读 `skillStore.installed`，装机↔使用合成一条路 |
| **WB-181** | 假交互与虚假承诺清理（铁律#1） |
| **WB-182** | 「套件」真做（Hub kit 表 + 批量安装）或删 |
| **WB-183** | `catalog_skills` 入库 —— 补 WB-059 漏掉的技能（含 Hub） |
| **WB-184** | 浏览面板四套数据源/两套分类收敛 |
| **WB-185** | `/api/skills` 攻击面：App 侧 slug 未校验 + 端点零鉴权 |
| **WB-186** | 技能后端一致性尾集（plan 约束 / rankings 绕 Hub / 预览缓存无 TTL） |

**注意迁移面**：`projects.skills` 与 `assistants.skills` 里已存的是展示名，改 slug 需一次非破坏迁移。

## 验证

- 子任务全 fixed 后关闭本条。
- 端到端：装一个 SkillHub 技能 → ＋ 菜单能选到 → 发消息 → SSE trace 里出现该技能的**真实工具调用或真实 SKILL.md 注入**，而非兜底话术。
- 反向：卸载后该技能从 ＋ 菜单消失；loadout 里残留的 slug 解析不到时**诚实报错/不注入**，不再编话术。
