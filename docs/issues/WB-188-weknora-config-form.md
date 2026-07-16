---
id: WB-188
title: WeKnora 连接配置改为 UI 表单提交（按 owner 入库，不再只能改 .env）
severity: P2
area: fullstack
status: fixed
origin: 既有实现
files:
  - backend/agent/weknora.py:35-47
  - backend/routers/knowledge.py:32-39
  - backend/agent/tools.py:350-351
  - backend/agent/runtime.py:285
  - src/components/connector/ConnectorDetailModal.tsx
  - src/views/KnowledgeView.tsx:160
  - src/data/catalog.ts:163
created: 2026-07-16
---

## 问题

用户诉求：「WeKnora 的连接配置，不应该修改配置文件，而应该提供表单提交相关的配置项」。

现状 WeKnora 是**唯一**一个只能靠改 `backend/.env` 才能接入的能力：

- `backend/config.py:60-62` —— `WEKNORA_URL` / `WEKNORA_API_KEY` / `WEKNORA_EMBEDDING_MODEL_ID`
  全部 `os.getenv`，**进程级、非 owner 隔离**，改完还得重启后端。
- `backend/agent/weknora.py:35-47` —— `configured()` / `_headers()` / `_api()` 直读 `settings.*`。
- `backend/routers/knowledge.py:32-39` —— `_require()` 文案硬写「请在 backend/.env 配置」；
  且该 router **全程没有 `current_user()`**（对比 `routers/models.py` 每个端点都有）。
- `src/views/KnowledgeView.tsx:160` —— 空态让用户「请让管理员在后端配置」。
- 连接器详情弹窗（WB-177 新增的 WeKnora 卡）「启用方式」也只能干写一段 .env 说明。

这与项目自身的既有做法相悖：模型管理（WB-124/128/136）早已是「各厂商 base/key 按用户入库，
运行时按 owner 解析」（`db.get_provider_key`/`set_provider_key`），连接器 token（WB-077/093）
也存 DB 并在本机设置 UI 内可改。`docs/issues/WB-161` 已经记过：`CLAUDE.md` 铁律#4 的
「Key 只存 backend/.env」表述与实现（存 DB）不符，`.env` 只是兜底而非唯一。

## 触发场景

App → 连接器 → WeKnora知识库 → 详情弹窗：只有一段「在 backend/.env 配置 WEKNORA_URL /
WEKNORA_API_KEY」的说明文字，没有任何可填的表单；用户必须去文件系统改 `.env` 并重启后端。
「知识库」页未配置时同样只给一句「请让管理员在后端配置」。

## 影响

P2：功能可用但接入门槛错位 —— 桌面应用要求用户手改配置文件 + 重启进程；且配置是进程级的，
共享后端多用户下所有人共用一套 WeKnora 凭据（与 WB-153 的 owner 隔离方向相悖）。

## 建议修法

**存储（按 owner，复用既有表，不新建表）**
- API Key → `provider_keys(owner_id, provider_id='weknora')`：项目**指定的密钥存放处**，
  `set_provider_key` 已实现「空串=撤销」，`list_provider_keys` 只回 id 集合（天然只写不回读）。
  不放通用 KV `user_settings`，避免将来有人加「整表导出」时把密钥带出去
  （现 `routers/data.py:37` 的导出走 `get_personalization`，只读两个白名单键，暂无此风险）。
- 服务地址 / 嵌入模型 id（非密钥）→ `user_settings` KV：`weknora_url` / `weknora_embedding_model_id`。
- `db.py` 加 `get_weknora_conf(owner_id)` / `set_weknora_conf(owner_id, ...)` 一对封装把上面两处藏起来；
  「不改」与「清除」用 sentinel 区分（照 `models.py:361` 自定义模型 PATCH 的语义）。

**解析（DB 优先，.env 兜底）**
- `weknora.py` 各公开函数显式加 `owner_id` 参数，内部 `_conf(owner_id)` 解析：
  DB 有则用 DB，没有则回退 `settings.WEKNORA_*` —— **存量 .env 用户零破坏**。
- `tools.py` 的 owner 从 `_kb_ctx` 取；**注意 `runtime.py:285` 现在只有挂了库才 set owner**
  （`set_knowledge_context(user.id if (active_knowledge and not ask) else None, ...)`），
  而 `knowledge_add` 不要求挂载（WB-175）→ 必须改成 owner 始终 set、库列表可空，
  否则 add 路径拿不到 owner。`_knowledge_retrieve_run` 的「未挂载」提示按 knowledge_ids 空判断。
- `runtime.py:324` 的系统提示分支也要从 `settings.WEKNORA_API_KEY` 改为 `weknora.configured(owner)`。

**API（`routers/knowledge.py` 加 `current_user()`）**
- `GET /api/knowledge/config` → `{configured, url, has_key, embedding_model_id, source: 'db'|'env'|null}`
  —— **绝不回 api_key**（用户已拍板：只写不回读，同厂商 Key 的 `list_provider_keys` 脱敏做法）。
- `PUT /api/knowledge/config` → `{url?, api_key?, embedding_model_id?}`；
  `api_key` 省略=不改 / 空串=撤销 / 非空=覆盖。
- `POST /api/knowledge/config/test` → 真打一次 WeKnora（`list_kb`）验证连通与鉴权，
  返回 `{ok, error?, kb_count?}` —— **成功失败都是 200**，错误进 `error` 字段让前端原样 toast
  （照 `models.py:253-280` `fetch_provider_models` 的约定，而非抛 HTTP 错）。
- 其余端点 `_require(owner)` 未配置仍 400，但文案改为引导去 UI 表单。

**前端**
- `ConnectorDetailModal.tsx`：`ConnMeta` 加可选 `configKind?: 'weknora'`；有它就把「启用方式」
  那段静态文案换成真表单（服务地址 / API Key / 嵌入模型 id + 保存 + 测试连接），
  **复用既有 class**（`mc-keyrow`/`mc-cfg`/`mc-cfglbl`/`mc-frow`/`np-input`/`btn-dark`/`btn-ghost`），
  不新造样式（铁律#2）。已配置时 Key 输入框空起手 + placeholder「已配置，输入新 Key 覆盖」+「撤销」按钮。
- 卡片与弹窗徽标：接实时状态（`需连接` ⇄ `● 已连接`），照金山文档 oauth 的 `refreshAuth` 形态，
  但走 `GET /api/knowledge/config`。
- `KnowledgeView.tsx` 空态：从「请让管理员在后端配置」改为直接引导到该表单。
- `catalog.ts` 的 `CONN_META.WeKnora知识库.setup` 文案改成 UI 引导 —— **三层同步**
  （catalog.ts / catalog_showcase.json / 运行库，见 WB-177 的坑）。

## 验证

- `npx tsc --noEmit`；`py_compile` 改动的后端文件。
- 真机端到端：表单填 URL+Key 保存 → 测试连接通过 → 知识库页能列库；
  `GET /api/knowledge/config` 响应里**不含 api_key**（grep 断言）。
- 回退：DB 清空后仍能用 `.env` 的值（存量用户零破坏）；两者都无 → 400 + 引导文案。
- owner 隔离：A 配的 Key 不影响 B（B 仍未配置）。
- 撤销：Key 置空 → `configured=false`，检索/加入工具给出未接入提示。
- UI：明暗双主题看表单；`knowledge_add` 在未挂载任何库时仍能拿到 owner（回归 WB-175）。

## 处理记录（2026-07-16）

用户拍板：Key **只写不回读**（同模型管理的厂商 Key，而非 Telegram token 的明文可见）。

- 存储（未新建表）：`db.get_weknora_conf`/`set_weknora_conf`（`storage/db.py`）——
  key → `provider_keys(owner,'weknora')`（`WEKNORA_PROVIDER` 常量），url/嵌入模型 → `user_settings` KV；
  `_KEEP` sentinel 区分「不传=不改」与「''=清除」。
- 解析：`weknora.conf(owner) -> Conf(url, api_key, embedding_model_id, key_source, url_source)`，
  **DB 优先 / .env 兜底**；全部公开函数加 `owner_id` 首参；`NOT_CONFIGURED` 统一引导文案（不再喊「去改 .env」）。
- 路由：`routers/knowledge.py` 补 `current_user()`（此前**全程无鉴权**），`_require()` 返回 owner；
  新增 `GET/PUT /api/knowledge/config` 与 `POST /api/knowledge/config/test`。
  `/config` 声明在 `/{kb_id}` **之前**（否则 `GET /config` 会被当成 kb_id="config"，实测踩到过）。
- **顺带修掉一个潜伏 bug**：`runtime.py` 原来只有「挂了库」才 set owner
  （`set_knowledge_context(user.id if active_knowledge ...)`），而 `knowledge_add` 不要求挂库（WB-175）
  → 改成 owner 无条件 set、库列表可空，`_knowledge_retrieve_run` 改判 `knowledge_ids` 空。
  否则本次 owner-aware 化会让「不挂库直接加文件」拿不到连接配置而失效。
- 前端：新组件 `components/connector/WeKnoraConfigForm.tsx`（复用 `mc-form`/`mc-cfg`/`mc-keyrow`/`np-input`
  等既有 class，零新样式）；接进连接器详情弹窗（`ConnMeta.configKind='weknora'` 时「启用方式」下渲染真表单）
  与知识库页未接入态；卡片/弹窗徽标接真实连接态（`需连接` ⇄ `● 已连接`）。
  `catalog.ts` 的 setup 文案改为表单引导 —— 三层同步（含运行库对账，见 WB-177）。
- `config.py` 注释更正：那三个 env 现在是兜底而非唯一来源。

验证：
- `npx tsc --noEmit` 通过；改动的 5 个后端文件 `py_compile` 通过。
- 后端踩到「serving stale code」：`GET /config` 被旧路由当 kb_id 吃掉（502），**硬重启 :8000** 后正常（CLAUDE.md 已记此坑）。
- 真机端到端（curl 打真 :8000）：
  - GET → 存量 `.env` 生效且标 `key_source:"env"`（**存量用户零破坏**实证）。
  - PUT url+key → `key_source/url_source` 转 `db`；回读 **grep 断言响应无 `api_key`、无密钥值 → 命中 0**。
  - 测试连接：坏配置 → `{ok:false, error:"…"}` 且 **HTTP 200**（不是 5xx）；
    撤销 DB 覆盖后回退 .env → 真 WeKnora `{ok:true, kb_count:1}`。测完已还原用户原状态（DB 无残留行）。
- owner 隔离（库副本）：A 配 `sk-A-only` → B 仍回退 .env，互不可见；
  「只改 emb 不动 url」「撤销 key 不动 url」语义正确。
- 上下文回归（库副本）：未挂库时 `_kb_owner()` 仍给 owner（knowledge_add 可用），retrieve 仍如实报「未挂载」；ask 模式置空。
- UI（MCP 浏览器被并发会话占用 → 独立 headless chromium + CDP 实测真页面）：
  连接器卡片与弹窗徽标均为「● 已连接」；表单三项渲染，url/嵌入模型回填真值、
  **Key 框 type=password 且 value 恒空**（只写不回读实证），按钮未改动时禁用，
  提示如实显示「Key 当前来自 backend/.env」；明暗双主题表单底色/文字色均正常（无白底白字）。
  知识库页「未接入」分支：本机 .env 有真 key 故该分支活不出来 —— 用 CDP 只把 `/knowledge/config`
  这一个响应打桩成 `configured:false`，验真组件渲染：只出「接入知识库」+ 表单，
  不出新建按钮/模板/列表，「测试连接」在无 key 时禁用。
- **实测中发现并修掉自己引入的回归**：原用 `cfg?.configured` 门禁，若 `/config` 请求失败/未回，
  `cfg` 恒 null → 整个知识库页空白。改为 `const configured = cfg ? cfg.configured : true`（未知时乐观渲染），
  只有**确知**未接入才换成表单。
- commit：未提交（用户未要求）。
