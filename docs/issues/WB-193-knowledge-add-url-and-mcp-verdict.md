---
id: WB-193
title: knowledge_add 只能加工作区文件，不能从 URL/文本入库 —— 承接 WB-175「留后续」；并记录「不接官方 WeKnora MCP server」的评估结论
severity: P3
area: backend
status: open
origin: 既有实现（能力缺口）+ 选型评估
files:
  - backend/agent/tools.py:495
  - backend/agent/weknora.py:193
  - backend/agent/mcp_client.py:97
created: 2026-07-17
---

## 问题

会话内把资料沉淀进知识库只有一条路：`knowledge_add`（[tools.py:495](../../backend/agent/tools.py#L495)）读**工作区文件**
→ `weknora.upload_file`（[weknora.py:193](../../backend/agent/weknora.py#L193)）。用户说「把这个网页加进知识库」做不到，
只能先自己把网页存成文件再加。

WeKnora 本身支持三种入库（`docs/api/knowledge.md`）：`/knowledge/file`、`/knowledge/url`、`/knowledge/manual`。
[[WB-175]] 当年**只接了 file 一条**，并在「未做（留后续）」里写明原因：`manual` 建出来是 `draft/disabled`
（需额外处理才可检索）、`url` 受 WeKnora SSRF 白名单限制（实测 `example.com` 即被拦）。
本条把那半截「留后续」显式挂账，避免它散落在一条已 fixed 的 issue 里无人追踪。

## 触发场景

会话里对助理说「把 https://… 这篇文档加入知识库」→ 助理只能答做不到，或退而求其次读完网页在对话里转述（不入库、不可检索）。

## 影响

P3：能力缺口，非缺陷，且有可用替代（先存文件再 `knowledge_add`）。不定 P2 是因为**障碍在上游、不在本仓**：
放开 URL 入库需要用户去改 WeKnora 部署侧的 `SSRF_WHITELIST`（形如
`SSRF_WHITELIST=internal.service,*.corp.example,172.16.0.0/12`），这与 [[WB-188]]「让用户填表单、不必改配置文件」
的方向有张力 —— 收益够不够抵这份麻烦，值得先想清楚再动手。

另需注意：WeKnora 的 URL 导入有 **CVE-2026-30247**（SSRF via redirect，后端不校验重定向目标；
`host.docker.internal` 未被拦），修复版 ≥0.2.12。真要放开白名单前应先确认部署版本。

## 决策依据：为什么不通过接官方 MCP server 来拿这个能力

WeKnora 官方有 `mcp-server/`（`pip install weknora-mcp-server`，stdio，`WEKNORA_BASE_URL` + `WEKNORA_API_KEY`），
其中 `create_knowledge_from_url` 正好覆盖本条缺口。**评估结论：不接**，理由按分量排序：

1. **拿不到额外好处**。MCP 的 `create_knowledge_from_url` 打的是同一个 WeKnora REST `/knowledge/url` 端点，
   **受同样的 SSRF 白名单限制** —— 换个调用方并不能绕过上游障碍，本条的真正难点原封不动。
2. **换过去反而丢能力**。按官方 README 列的工具面，MCP server **没有本地文件上传**（只有 `create_knowledge_from_url`），
   而 `upload_file` 恰是 `knowledge_add` 的核心。
3. **凭据模型冲突**。[mcp_client.py:97](../../backend/agent/mcp_client.py#L97) 的 `_secret_env` 与
   [:162](../../backend/agent/mcp_client.py#L162) 的 `requires` gate 都只读 `os.environ`；[[WB-188]] 后 WeKnora 配置
   按 owner 存 DB，MCP 连接器看不见。接 MCP 得先给 mcp_client 加 per-owner 凭据解析 —— 把 WB-188 往回推。
4. **工具面稀释**。MCP 暴露 22 个工具（tenant/session/model/chat 管理占大半，其中 `chat` 是 WeKnora 自己的 RAG 对话 ——
   本 agent 去调它是套娃），会挤掉现在精心裁出的 `knowledge_retrieve` + `knowledge_add` 两个高质量工具。
5. **进程与依赖**。每会话 spawn stdio 子进程（12s 握手超时）+ 要求用户装 `uv`/`pip` 包；且
   [mcp_client.py:196](../../backend/agent/mcp_client.py#L196) 的 frozen gate 让打包版默认禁用第三方 stdio 连接器。
   现在是后端进程内 httpx，零额外依赖。

同理排除 ClawHub 上的第三方 skill（`@lyingbug/weknora`，MIT-0，非腾讯官方）—— 它也只是包一层 WeKnora REST API，
而本后端自己就是那一层。

**结论**：要补就在现有 REST 客户端里补，不引入 MCP 这一层。

## 建议修法

**范围 `backend/`，零架构改动。** 动手前先定一件事：URL 入库要不要做（见「影响」的取舍）。若做：

1. **`backend/agent/weknora.py`**：加 `create_from_url(owner_id, kb_id, *, url)` → `POST /knowledge-bases/{id}/knowledge/url`，
   复用既有 `_request`/`_unwrap`（错误体解析已能吐出 WeKnora 的可读 message，SSRF 被拦会走这条路）。
2. **`backend/agent/tools.py`**：给 `knowledge_add` 加可选 `url` 参数（与 `path` 二选一，都缺 → 提示），
   目标库解析复用现成的 `_resolve_add_kb`，不另开工具（避免工具面膨胀，与上面第 4 条自洽）。
3. **被 SSRF 白名单拦时的文案**：必须可操作 —— 明确告诉用户是 WeKnora 侧的白名单拦的、要去哪配，
   而不是甩一句「加入失败」。这是本条能不能真用起来的关键。
4. `manual`（文本直接入库）**暂不做**：[[WB-175]] 实测建出来是 `draft/disabled`，需额外处理才可检索，收益不明。

## 验证

- `py_compile`；真机 WeKnora 驱动**真会话**（照 [[WB-175]] 处理记录的做法：`POST /api/chat`，让助理自己选工具）。
- happy：白名单内的 URL → 入库 → 轮询 `parse_status` 到 `completed` → `knowledge_retrieve` 能检索到该网页内容。
- 错误路径：白名单外的 URL（确认提示文案真的可操作）、`path`/`url` 都缺、`url` 格式非法、未接入 WeKnora。
- 回归：只传 `path` 的老路径（工作区文件）行为不变。
