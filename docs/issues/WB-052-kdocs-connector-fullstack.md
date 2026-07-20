---
id: WB-052
title: 金山文档连接器全栈落地（后端 kdocs-cli 桥接 MCP + 前端连接器详情弹窗/接入 loadout）
severity: P2
area: backend
status: fixed
origin: 既有实现
files:
  - src/data/catalog.ts:226
  - src/views/ExpertsView.tsx:267
  - backend/agent/mcp_client.py:67
  - backend/mcp_servers/telegram.py:1
created: 2026-07-07
---

## 问题

「金山文档」当前只是前端静态目录里的一张展示卡（[catalog.ts:226](../../src/data/catalog.ts#L226)），
[ConnectorsPane](../../src/views/ExpertsView.tsx#L267) 渲染的卡片只有一个仅弹 toast 的 `AddBtn`——
没有详情弹窗、没有能力清单、没有真正接入会话 loadout，更没有后端能力：
后端连接器注册表 [`CONNECTORS`](../../backend/agent/mcp_client.py#L67) 里根本没有「金山文档」，
选中它也只会被 `open_connectors` 当作「未内置该连接器」跳过（[mcp_client.py:174](../../backend/agent/mcp_client.py#L174)）。

按铁律 #1（不硬编码、不模拟），要把它做「真」：agent 得能**真操作**金山文档（WPS 云文档）——
搜索 / 读取 / 新建写入 / 分享 / 网页剪藏 / AI 生成 PPT 等；凭据按铁律 #4 只存后端 `backend/.env`，
按 WB-011 只注入该连接器自己的进程、绝不泄漏 `LLM_API_KEY`。

参考产品的连接器详情形态（截图）：图标/名称/完整能力介绍、去试试·解绑、Show Details 展开真实工具清单。
AgentMate 的连接器目前完全没有这层详情交互（专家有、连接器没有）。

## 触发场景

连接器页 → 金山文档卡片：点「＋」只弹「已添加」toast，不进 loadout；无详情弹窗、看不到它能干什么；
即便手动把「金山文档」加进 loadout，后端也因未注册而跳过——**这个连接器目前对 agent 完全无效**。

## 影响

P2：一个 headline 连接器整块缺失（前端呈现 + 后端能力都缺）。金山办公已提供官方 `kdocs-cli`
（WPS 云文档 API 的命令行封装，本机已安装 v2.5.11），后端可照 `telegram.py`
（内置 FastMCP、call-time 读凭据、`requires` 门控）的成熟模式做一个 in-process 桥接，风险可控。

## 建议修法

### 后端（真能力）
- `backend/mcp_servers/kdocs.py`（新）：内置 FastMCP server，工具异步 `subprocess.run`（放进
  `asyncio.to_thread`，避开 Windows Selector loop 不支持子进程的坑、也不阻塞事件循环 WB-002）
  壳到 `kdocs-cli`。curated 工具（`search_files`/`read_file`/`create_doc`/`list_files`/`share_file`/
  `scrape_url`/`generate_ppt`）+ 通用透传 `run(service,action,params_json)` + 自描述 `list_actions`
  覆盖 10 服务 170+ 动作。凭据 call-time 读 `KDOCS_TOKEN`，有则 `--token` 传入；子进程 env 走白名单
  （不带 `LLM_API_KEY`，WB-011）。exit code 恒为 0，须解析 stdout JSON 的 `code`（0=成功）。
- `backend/agent/mcp_client.py`：`_builtin_fastmcp` 增 `kdocs` 分支；`CONNECTORS` 注册
  `"金山文档": {"builtin_server":"kdocs","builtin":True,"requires":["KDOCS_TOKEN"]}`——无 token 时
  按既有机制清晰跳过、并被 [runtime.py:345](../../backend/agent/runtime.py#L345) 报「连接器未就绪」。
- `backend/config.py` + `.env.example`：登记 `KDOCS_TOKEN`（可发现性 + 使用说明）。

### 前端（呈现 + 接入）
- `src/data/catalog.ts`：金山文档描述对齐参考稿；新增 `CONN_META`（`status`(rdy/tok)/`setup`/完整介绍/
  真实工具清单——镜像后端桥接，非伪造）。
- `src/components/connector/ConnectorDetailModal.tsx`（新，套 `.np-*` 弹窗类）：图标/名称/状态标签
  （复用已存在的 `.conn-tag.rdy/.tok`）/完整介绍/能力清单（Show Details）/「去试试」「添加·移除」。
- `src/views/ExpertsView.tsx`：ConnectorsPane 卡片点开详情弹窗、显示状态标签；「添加」真接入
  `loadoutStore.toggle('conn', name)`（不再只是 toast），「去试试」把连接器挂进 loadout 并到首页 composer。

## 验证

- `npx tsc --noEmit` 通过；`py_compile` 改动 .py 全过。
- 桥接子进程+解析：直接跑 `kdocs.py` 的 `run`/`list_actions`，确认真起 `kdocs-cli`、正确解析 JSON 信封；
  鉴权失败路径（token 过期 → `code:400006`）返回可读错误而非崩溃。
- 后端注册：`is_connector("金山文档")` 为真；未配 `KDOCS_TOKEN` 时 `open_connectors(["金山文档"])`
  把它列进 `skipped` 且 reason 提示配置 KDOCS_TOKEN；配了 token 则真列出工具。
- 手动/端到端：配一个有效 `KDOCS_TOKEN` 后，让 agent「搜索金山文档里的周报」→ 真返回文件列表
  （本机 keychain token 已过期，端到端成功路径需用户提供有效 token；无 token 时优雅降级）。
- Playwright：连接器页点金山文档 → 详情弹窗（状态标签、能力清单、去试试/添加）；**明暗双主题**都看。

## 处理记录（2026-07-07）

- 改动：
  - 后端：
    - `mcp_servers/kdocs.py`（新）：内置 FastMCP server「kdocs」，工具经 `asyncio.to_thread(subprocess.run, …)`
      壳到本机 `kdocs-cli.exe`（避开 Windows Selector loop 不支持子进程、也不阻塞事件循环 WB-002）。
      9 个工具：curated `search_files`/`read_file`/`create_doc`/`list_files`/`share_file`/`scrape_url`/
      `generate_ppt`（参数逐一对照 `kdocs-cli <svc> <action> --help` 落地）+ 通用透传 `run(service,action,
      params_json)`（覆盖 10 服务 170+ 动作）+ 自描述 `list_actions`。call-time 读 `KDOCS_TOKEN`，有则
      `--token` 传入；子进程 env 走白名单（不带 `LLM_API_KEY` 等，WB-011）；解析 stdout JSON 的 `code`
      （exit code 恒 0，不可信），400006 给出更换 token 的提示。
    - `agent/mcp_client.py`：`_builtin_fastmcp` 增 `kdocs` 分支；`CONNECTORS` 注册
      `"金山文档": {builtin_server:"kdocs", builtin:True, requires:["KDOCS_TOKEN"]}`。
    - `config.py` + `.env.example`：登记 `KDOCS_TOKEN`（可发现性 + 获取/使用说明）。
  - 前端：
    - `data/catalog.ts`：金山文档描述对齐参考稿；新增 `CONN_META`（status/statusLabel/setup/fullDesc/
      tools/prompts），tools 逐字镜像后端 9 个工具（非伪造）。
    - `components/connector/ConnectorDetailModal.tsx`（新，套 `.np-*` 弹窗类）：图标/名称/状态标签
      （复用 `.conn-tag.tok`）/能力介绍/启用方式/能力清单（Show Details 折叠）/试试这样问我；
      「添加到本会话」真 `loadoutStore.toggle('conn', …)`，「去试试」挂连接器进 loadout + 到 composer。
    - `views/ExpertsView.tsx`：ConnectorsPane 卡片可点开详情弹窗（role=button + 键盘可达）、显示状态标签；
      新增受控 `ConnAddBtn`（反映真实 loadout、stopPropagation 不误触发弹窗）。
- 验证：`npx tsc --noEmit`、`npx vite build`、`py_compile`（kdocs.py/mcp_client.py/config.py）全过。
  - 桥接实测：`list_actions('drive')` 真起 `kdocs-cli drive --help` 并回传（无需鉴权）；`run drive search-files`
    在本机 keychain token 已过期下返回可读错误「金山文档接口错误 code=400006：Token 已失效…」，无崩溃。
  - 注册实测：`is_connector('金山文档')` 为真；`open_connectors(['金山文档'])` 无 `KDOCS_TOKEN` → skipped
    `{reason:'需在 backend/.env 配置 KDOCS_TOKEN'}`（被 runtime 报「连接器未就绪」）；设 token → 经真实 MCP
    in-process 通道列出全部 9 个工具（qualified `mcp__c0__search_files` 等），connector=金山文档。
  - Playwright（:5173，登录用户「奇」）：连接器页金山文档卡片显示「需配置 Token」标签与丰富描述 → 点开详情弹窗
    （状态标签 / 能力介绍 / 启用方式 / 能力清单展开 9 项工具 / 试用问法 / 添加·去试试）；「添加到本会话」→ 头部出现
    「本会话已接入」、按钮转「移除」（真读 loadout）；**明暗双主题**均正常（`.conn-tag.tok` 暗色 override 生效，
    无白底白字/深底深字）。测试后已复位 loadout、删除临时截图。
  - 端到端成功路径（agent 真列/建金山文档）需用户在 backend/.env 配置有效 `KDOCS_TOKEN`（本机 keychain token 已过期）；
    无 token 时按既有机制优雅跳过、不影响其他能力。
- commit：（待提交）

## 处理记录（2026-07-07）· 追加：WPS OAuth「连接」流

用户反馈「金山文档连接器点击后应跳转到 WPS 页面授权」——把授权从「手填 KDOCS_TOKEN」升级为真实 OAuth 连接流。

- 机制（实测）：`kdocs-cli auth login` 把 WPS 授权 URL 打到 **stderr（立即 flush）**、最终 Token 打到 stdout，
  且会自动开浏览器；用户授权后 Token 存**系统密钥链**。Token 优先级：`--token` > 环境变量 > 密钥链。
- 后端：
  - `routers/kdocs.py`（新）：`GET /api/connectors/kdocs/status`（installed/authenticated，跑 `auth status --output json`）、
    `POST /connect`（线程里 spawn `auth login`，stdout→DEVNULL 丢弃 Token「绝不进后端内存/前端」、stderr 抓授权 URL；
    已登录 WPS 者秒级自动完成，故 6s 内再探一次直接回 connected，否则回 `{pending, authUrl}`）、`POST /disconnect`（logout）。
    同步 `def` 端点走 FastAPI 线程池，阻塞子进程不卡事件循环（WB-002）；子进程 env 白名单（WB-011）。
  - `main.py` 挂载 `kdocs.router`。
  - `agent/mcp_client.py`：新增通用 `requires_bin` 门控；金山文档 spec 从 `requires:["KDOCS_TOKEN"]` 改为
    `requires_bin:["kdocs-cli"]`——授权改走 OAuth→密钥链，桥接无 `KDOCS_TOKEN` 时回退密钥链 Token。
  - `mcp_servers/kdocs.py`：400006 提示改为「请在连接器页点『金山文档 · 连接』重新授权」。
- 前端：
  - `lib/api.ts`：`kdocsStatus/kdocsConnect/kdocsDisconnect`。
  - `ConnectorDetailModal.tsx`：oauth 连接器打开即拉真实状态；未连接→主按钮「连接」（点后 `window.open(authUrl)`
    跳 WPS 授权页 + 每 2s 轮询状态，最长 5 分钟，含「手动打开授权页」兜底链接）；已连接→「● 已连接」+ 断开/添加/去试试
    并放出试用问法；未安装 kdocs-cli 有明确提示。轮询 timer 卸载即清。
  - `ExpertsView.tsx`：连接器卡片拉一次真实连接态，金山文档显示「● 已连接 / 需连接」；弹窗关闭回刷。
  - `catalog.ts`：CONN_META 金山文档加 `oauth:true`、启用说明改为 OAuth 口径。
- 验证（真流程，非模拟）：
  - `GET /status` → `{"installed":true,"authenticated":true}`；`POST /connect`（已授权）→ `{"status":"connected"}`。
  - **真调用**：桥接 `search_files('周报')` 经密钥链 Token 返回 `code:0` + 真实文件（file_id / `kdocs.cn/l/…` 链接 /
    created_by「奇」）——连接器真能操作金山文档。
  - **Playwright 全流程**：卡片「● 已连接」→ 弹窗连接态（断开/添加/去试试）→ 点「断开」→「需连接」+「连接」按钮 →
    点「连接」→ **新开标签跳转 `account.wps.cn/login?cb=…` WPS 授权页**（正是用户要的「跳转 WPS 授权」）→ 后端 auth login
    自动完成 → 前端轮询回「● 已连接」。明暗双主题均正常。测试后连接器已恢复已连接、临时截图与多余标签已清。
