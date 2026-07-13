---
id: WB-140
title: 侧栏「金山文档」面板真接入 —— 最近/搜索云文档，点开跳转，连接态引导
severity: P2
area: fullstack
status: fixed
origin: 既有实现
files:
  - src/components/layout/Sidebar.tsx:303
  - src/views/KdocsView.tsx
  - src/App.tsx:42
  - src/lib/types.ts:16
  - src/lib/api.ts:161
  - backend/routers/kdocs.py:83
created: 2026-07-14
---

## 问题

侧栏「更多 → 金山文档」当前只是个桩：点击只弹 `toast('打开 · 金山文档')`
（[Sidebar.tsx:303](../../src/components/layout/Sidebar.tsx#L303)），没有任何真实面板。

金山文档的**后端能力早已打通**：WB-052/WB-054 已落地 `kdocs` 内置 MCP 连接器
（[mcp_servers/kdocs.py](../../backend/mcp_servers/kdocs.py)，9 个真实工具 + 通用透传）、
WPS OAuth 连接流（[routers/kdocs.py](../../backend/routers/kdocs.py)）、前端连接器目录/详情弹窗。
但那套是「让 agent 在对话里操作金山文档」，缺一个**直接浏览自己云文档**的入口——
即这个侧栏面板。

## 触发场景

侧栏「更多」菜单 → 点「金山文档」→ 只弹一条 toast，看不到任何自己的云文档。

## 影响

一个显式暴露的入口是死的（伪功能，违背铁律#1「不模拟」精神）。用户期望点进去能看到、
搜索、打开自己的金山文档。P2：非核心链路，但后端能力已就绪，补面板即可真打通。

## 建议修法

**后端**（`backend/routers/kdocs.py`，复用既有 `_cli`/`_safe_env` 与 subprocess 同步模式）：
- 新增 `GET /api/connectors/kdocs/files?keyword=&page_size=`：
  - 无 keyword → `kdocs-cli drive list-latest-items`（最近访问文档）
  - 有 keyword → `kdocs-cli drive search-files`
  - 解析 stdout JSON 信封（`code==0`；升级提示走 stderr，stdout 是干净 JSON），
    把 `items[].file` 归一化成 `{name,file_id,drive_id,link_url,ext,mtime,size,owner}`。
  - 未安装/未授权 → 分别回 `{installed:false}`/`{authenticated:false}`（诚实降级，前端引导连接），
    不 500。

**前端**：
- `lib/types.ts`：`ViewId` 加 `'kdocs'`。
- `lib/api.ts`：`kdocsFiles(keyword?)`（复用既有 `kdocsStatus/kdocsConnect`）。
- `views/KdocsView.tsx`（新，复用 `.page-scroll`/`.mf-*`/`.search-box`/`.hub-act` 等既有 class，
  不引入新样式 token）：
  - 挂载先拉 `kdocsStatus`：未安装 → 提示装 kdocs-cli；未授权 → 「连接金山文档」按钮走
    既有 OAuth（`kdocsConnect` + `window.open(authUrl)` + 轮询）；已授权 → 拉最近文档。
  - 顶部搜索框（回车触发）→ `kdocsFiles(keyword)`；空关键词回到最近文档。
  - 文件列表：按后缀给图标、名称、归属者/修改时间；点一项 `window.open(link_url,'_blank',
    'noopener,noreferrer')` 跳转在线文档。空态/加载态/错误态都有。
- `App.tsx`：`case 'kdocs'` 渲染 `KdocsView`。
- `Sidebar.tsx`：`toast('打开 · 金山文档')` → `setView('kdocs')`（收起「更多」菜单）。

凭据不出本机（后端只经密钥链 Token 调 CLI，link_url 是公开分享短链）。

## 验证

- 后端：`py_compile backend/routers/kdocs.py`；`GET /api/connectors/kdocs/files` 返回最近文档，
  带 keyword 返回搜索结果；未授权时诚实降级。
- 前端：`npx tsc --noEmit` 过；浏览器实测点「更多 → 金山文档」→ 面板列出真实最近文档 →
  搜索 → 点开跳转 kdocs.cn；**明暗双主题**都看。

## 处理记录（2026-07-14）

- 改动：
  - 后端 `routers/kdocs.py`：新增 `GET /api/connectors/kdocs/files?keyword=&page_size=`。
    复用既有 `_cli`/`_safe_env`/`_authed`；新增同步 `_run_json`（跑 `kdocs-cli <svc> <action> --output json
    --args {...}`，只解析 stdout JSON 信封——升级提示走 stderr、stdout 干净；exit code 恒 0 故只信
    `code==0`）+ `_items`（挖出嵌套 `data…items[]`）+ `_norm`（把 `.file` 归一化成
    name/file_id/drive_id/link_url/ext/mtime/size/owner，只留 type==file）。无 keyword → `list-latest-items`
    （最近访问），有 → `search-files`。未安装/未授权分别回 `{installed:false}`/`{authenticated:false}`（诚实降级，
    前端引导连接），CLI 报错回 502。
  - 前端：`lib/types.ts` 加 `ViewId 'kdocs'` + `KdocsFile` 接口；`lib/api.ts` 加 `kdocsFiles(keyword)`；
    新 `views/KdocsView.tsx`（连接态机 loading/not_installed/need_auth/connecting/ready；未授权走既有
    `kdocsConnect` OAuth+`window.open`+轮询；已连接拉最近文档、回车搜索、返回最近、刷新；文件行按后缀给
    emoji 图标+类型名、名/归属/时间/大小，点开 `window.open(link_url)` 跳转）；`App.tsx` 加 `case 'kdocs'`；
    `Sidebar.tsx` 更多菜单「金山文档」`toast` → `setView('kdocs')`。
    `styles/app.css` 加 `.kd-*` 列表样式（用既有 token）、`tokens.css` 把 `.kd-item` 并入 body.dark 深色面板列表。
- 验证：
  - `py_compile routers/kdocs.py`、`npx tsc --noEmit` 全过。
  - **真接口**（后端已在跑，reload 生效）：`GET /files`（空 kw）返回 30 条真实最近文档
    （`Claude_Code_视频…docx`、`xgit新服务器.otl` 等，含真实 `kdocs.cn/l/…` 链接、归属者「奇」）；
    `?keyword=周报` 返回 29 条真实周报文档。
  - **Playwright 实测**（:5173，用户「奇」）：侧栏「更多 → 金山文档」→ 面板 `data-view=kdocs` 渲染、
    标题「📄 金山文档」、列出 30 条真实最近文档（图标/类型/归属/时间/大小）；输入「周报」点「搜索」→
    列表切「『周报』的搜索结果 · 29 项」、出现「返回最近」按钮；**明暗双主题**均正常
    （`.kd-item` 暗色 `#22272D` 面板、白字/灰 meta，无白底白字/深底深字）。测试后已删临时截图与 `.playwright-mcp`。
  - 端到端未授权路径靠既有 WB-052 OAuth 流（本机当前已授权，走已连接分支）。
- commit：（待提交）
