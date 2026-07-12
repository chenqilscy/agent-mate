---
id: WB-125
title: 目录运营中心「SkillHub」顶层 tab 与「技能」tab 冗余，SkillHub 并入技能作第三子视图
severity: P2
area: frontend
status: fixed
origin: 既有实现
files:
  - hub/web/console.html:1054
  - hub/web/console.html:1403
  - hub/web/console.html:1600
created: 2026-07-12
---

## 问题

App 管理端 `hub/web/console.html` 的「目录运营中心」目前有 5 个顶层 tab：
`专家·专家团 / 连接器 / 技能 / SkillHub / 高级 JSON`（`catTab` 定义在 console.html:1054）。

其中「技能」tab（`skillsCat`，console.html:1403）自身有「浏览橱窗 | 目录管理」子切换，
且浏览橱窗内还有一段名为 **SkillHub** 的子标签（`sgSkillhub`，`推荐 / SkillHub / 套件` 三段）。
而顶层又有一个独立的 **SkillHub** tab（`skillhubCat`，console.html:1600）。

两者**读同一份数据**（`/catalog/skill` 镜像 + `/catalog/skill-category`），但定位不同：

- 技能→浏览橱窗→SkillHub 段：**只读预览**，与 App 整页技能同款富卡片，给运营看下发效果，消费 `SKILLHUB_FEATURED`。
- 顶层 SkillHub tab：**运营操作台**，手动同步 CLI、按真实榜单字段（来源/下载/收藏/安装/上新）筛选排序、加入/取消精选（生产 `SKILLHUB_FEATURED`）。

问题在于 **"SkillHub" 这个名字在顶层 tab 和技能橱窗子标签两处各出现一次**，信息架构冗余、
让人以为是同一入口点两遍；且「技能相关」的操作散落在两个顶层 tab。

## 触发场景

进入 App 管理端 → 目录运营中心 → 顶部同时看到「技能」和「SkillHub」两个 tab；
点「技能」→ 浏览橱窗，里面还有个「SkillHub」段。用户困惑：SkillHub 到底在哪个 tab？两处什么关系？

## 影响

P2：不是功能缺陷，是信息架构/一致性问题。「连接器」tab 已是「浏览橱窗 | 目录管理」两子视图的干净范式，
技能相关却分裂在两个顶层 tab，破坏一致性，增加认知负担。

## 建议修法

方向 A（用户已选）：把顶层 SkillHub tab **降级为「技能」tab 的第三个子视图**，与「连接器」对齐。

- `skillsCat`（console.html:1403）的子切换从「浏览橱窗 | 目录管理」扩为
  **「浏览橱窗 | 目录管理 | SkillHub 同步」**，`SKILLSUB` 增加 `"skillhub"` 分支，
  第三个分支调用现有 `skillhubCat`（几乎原样复用，只是挂到 `sk-sub` 容器下）。
- 删掉 console.html:1054 顶层 `catTab("skillhub","SkillHub")`，顶层从 5 tab 减到 4。
- 顶层 tab 分发逻辑里 `skillhub` 分支一并移除（找 `catTab` 的 onclick / CAT 分发处）。
- 橱窗段里那个 `SkillHub` 子标签（`sgBrowse` 的 `data-seg="skillhub"`）**保留**，
  它是「预览 App 的推荐/精选榜/套件」三段之一，语义不同；不改名以免扩大改动范围（可另议）。
- 复用既有 class/token，不新增硬编码样式；子切换按钮沿用 `skillsCat` 已有的 `.tabs`/`data-ss` 范式。

## 验证

- `console.html` 是纯 vanilla + 模板串、无构建，语法用浏览器/CDP 载入验证（前端 tsc 不覆盖此文件）。
- 隔离 Hub（:810x + scratchpad DB）跑起，管理员登录（alice/alice123）→ 目录运营中心：
  - 顶层只剩 4 tab，无独立「SkillHub」。
  - 「技能」tab 出现三子切换「浏览橱窗 | 目录管理 | SkillHub 同步」，三者切换正常。
  - SkillHub 同步子视图：手动同步、搜索、来源/排序/场景筛选、加入/取消精选全部照旧可用；
    加入精选后回到「浏览橱窗」精选技能区能看到该项（数据链路未断）。
  - 明暗双主题各看一眼，无白底白字/深底深字。

## 处理记录（2026-07-12）
- 改动（`hub/web/console.html`，纯前端 vanilla）：
  - `catalogView`：顶层 tabs 去掉 `catTab("skillhub","SkillHub")`；分发 map 去掉 `skillhub:skillhubCat`。顶层 5→4 tab。
  - `skillsCat`：子切换从「浏览橱窗｜目录管理」扩为「浏览橱窗｜目录管理｜SkillHub 同步」，`SKILLSUB` 增 `skillhub` 分支，
    分发改为对象映射 `{gallery:skillsGallery, manage:skillsManage, skillhub:skillhubCat}`，第三分支复用原 `skillhubCat`（零改），
    渲染进子容器 `#sk-sub`，其自递归重绘只动 `#sk-sub`、保留上方子切换。
  - 橱窗内 `SG_SEG==='skillhub'` 段（推荐/SkillHub/套件之一）按方案保留不动，语义为「预览 App 技能页」而非运营入口。
- 验证：
  - `node --check` 抽 `<script>` 块解析 OK。
  - 隔离 Hub（scratch DB 拷贝 + `HUB_PORT=8110`，不扰共享 :8100）+ chrome-headless-shell 走 CDP：alice 登录 →
    目录运营中心。断言全 PASS：顶层 tabs=`["专家 · 专家团","连接器","技能","高级 JSON"]`（无 SkillHub、共 4）；
    技能子切换=`["浏览橱窗","目录管理","SkillHub 同步"]`；点「SkillHub 同步」渲染出操作台 `#sh-sync`（手动同步 SkillHub），
    子切换保留且「SkillHub 同步」高亮 active。截图确认暗色渲染正常、339 技能列表+加入精选按钮完整。
- commit：（待提交）
