---
id: WB-214
title: 推荐技能与 SkillHub 卡片交互不一致，内置技能缺少详情入口
severity: P2
area: fullstack
status: fixed
origin: 既有实现
files:
  - src/views/ExpertsView.tsx:62
  - src/views/ExpertsView.tsx:370
  - src/views/ExpertsView.tsx:473
  - src/components/skill/SkillDetail.tsx:36
  - backend/routers/skills.py:44
  - backend/routers/skills.py:80
created: 2026-07-20
---

## 问题

技能页的“推荐”和“SkillHub”使用两套卡片与两套入口：

- 推荐卡 `.scard` 本身不可点击，右上角 `RecoBtn` 对内置/已安装技能直接挂载到当前会话并跳回首页，对其他技能才尝试安装。
- SkillHub 卡 `.hcard.clickable` 点击卡片进入详情，右上角按钮只处理安装，安装后展示启停、编辑、卸载状态。

当前推荐目录的 6 条全部来自内置 `catalog_skills`，因此用户在推荐页点击“＋”都会直接离开目录；点击卡片其余区域没有反应。相同视觉层级的 SkillHub 卡却可以先查看详情，操作预期不一致。

不能只给推荐卡补 `onOpenDetail({slug})`：现有 `SkillDetail` 对未安装项调用 `/api/skills/preview`，该端点只预览 SkillHub 上游技能；内置技能不在磁盘，也未必存在于 SkillHub，会得到“未找到该技能”。

## 触发场景

进入“技能”：

1. 在“推荐”页点击 `Web Access（浏览器自动化）` 卡片正文，无反应；点击右上角“＋”，立即挂载并跳回首页。
2. 在“SkillHub”页点击任意卡片正文，进入详情页；点击“＋”才执行安装。

## 影响

P2：用户无法在使用内置推荐技能前查看其真实说明、工具与来源；两个并列 Tab 的相同卡片形态却采用不同导航模型，容易把“＋”误解为统一的安装动作。

## 建议修法

- 推荐卡与 SkillHub 卡统一为“点击卡片进入详情，卡片动作不触发详情”的交互模型。
- 给内置目录技能提供真实详情数据（读取 `catalog_skills`，不伪造 `SKILL.md`），详情明确展示“内置/Server 下发”来源、描述、指令与可用工具。
- 保留生命周期差异：内置/已就绪技能的主动作是“去试试/挂载”，SkillHub 未安装技能的主动作是“安装”；不要把内置技能伪装成需要安装。
- 卡片上直接动作应有明确 `aria-label`/tooltip，并与详情页主动作复用同一判断，避免再次漂移。

## 验证

- 推荐与 SkillHub 卡片正文均可进入详情；右上角动作均 `stopPropagation`。
- 6 条内置推荐技能详情均可读取真实 DB 定义，不访问 SkillHub、不报“未找到”。
- 内置技能执行“去试试”后进入 composer 并带真实 slug；SkillHub 未安装技能仍走真实安装。
- 明暗主题、窄屏与键盘焦点状态均正常；`npx tsc --noEmit` 与相关后端回归通过。

## 处理记录（2026-07-20）

- 推荐卡改为与 SkillHub 卡一致的“点击正文进入详情”；卡内动作继续阻止冒泡。
- 推荐目录技能无需安装，右上角从容易误解为安装的“＋”改为“使用”图标与文案，动作仍以稳定 slug 挂载并进入 composer。
- 后端新增 `/api/skills/catalog/{key}`，直接读取 `catalog_skills` 的真实定义；没有把目录定义伪造成磁盘 `SKILL.md`。
- 详情页展示来源、分类、真实可用工具与指令。目录技能只显示“去试试”，隐藏仅适用于磁盘技能的启停、打开目录与卸载操作。
- 目录详情与 SkillHub 预览显式分路：即使同 slug（实测 `web-access`），推荐仍读目录定义，SkillHub 仍读上游/本机安装内容，不互相覆盖。

### 验证结果

- `py_compile agent/skills.py routers/skills.py` 通过。
- `python -m unittest tests.regression.test_skill_catalog_contract`：4/4 通过，新增目录详情契约覆盖。
- `npx tsc --noEmit`、`npx vite build` 通过；构建仅保留既有的大 chunk 提示。
- 真 API：`/api/skills/catalog/web-access` 返回 `source=catalog/catalog=true`；同 slug 的 `/api/skills/preview` 仍返回本机 SkillHub 内容，来源隔离成立。
- CDP 真浏览器：推荐 6 张卡全部可点击；首卡详情显示“内置”、真实指令与“去试试”，无磁盘管理控件；浅色/深色均文字清晰且无横向溢出。
