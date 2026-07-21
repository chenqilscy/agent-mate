---
id: WB-193
title: knowledge_add 只能加工作区文件，不能从 URL/文本入库 —— 承接 WB-175「留后续」；并记录「不接官方 WeKnora MCP server」的评估结论
severity: P3
area: backend
status: deferred
origin: 既有实现（能力缺口）+ 选型评估
files:
  - backend/agent/tools.py:690
  - backend/agent/weknora.py:210
  - backend/agent/runtime.py:54
  - backend/tests/regression/test_weknora_knowledge_add_url.py:1
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

## 处理记录（2026-07-22）

- 改动：沿用现有 owner 级 REST 客户端，不引入 WeKnora MCP server。`knowledge_add` 现支持 `path` / `url`
  恰好二选一，目标库解析与旧 path 共用；运行时工具注册改为读取 `weknora.configured(user.id)`，不再只看进程级
  `.env`。URL 入库前每次读取 `/api/v1/system/info`，只接受可识别的稳定版 WeKnora `>=0.2.12`；版本
  未知、预发布、过旧或端点不可读一律 fail-closed，旧 path 不受影响。SSRF 拒绝会给出管理端白名单 /
  `SSRF_WHITELIST_EXTRA` 的可执行提示与最小放行警告。
- 未做：`manual` 文本入库仍不做。现有证据只能证明其创建后可能处于 `draft/disabled`，尚无可靠的自动转为
  `parse_status=completed` 并可检索契约；不把“创建出一条记录”冒充“知识已可用”。
- 自动化验证：改动 Python 文件 `py_compile` 通过；新增 WB-193 regression 10/10 通过，覆盖版本门禁、owner
  凭据、path/url 二选一、非法 URL、未配置、可操作 SSRF 错误和旧 path 回归。按仓库命令在本独立 worktree
  执行完整 backend regression：101 项中 93 通过、8 项基线错误；其中 4 项与下述 `list_messages` 阻塞同根，
  其余为本分支尚未包含的 Server gate / 测试 DB 与安全上下文隔离修复，不涉及本次文件。协调确认目标集成分支已含
  WB-277/WB-279/WB-280，完整 Backend 118/118；本 backend-only issue 不以 worktree 缺少 `node_modules` 为阻塞。
- 真实 WeKnora：运行容器镜像 `v0.6.3` 健康，`system/info` 自报 `0.6.2` / commit `974ca35`。
  `https://open.bigmodel.cn/` URL 临时库实测 `pending → processing → finalizing → completed`，检索命中 1 条；
  旧 `path` 文件实测 `completed` 且检索命中 1 条；`host.docker.internal` 被真实 SSRF 策略拒绝且 AgentMate
  返回可操作提示。所有临时知识库与本地临时目录均已删除。
- 状态与前置条件：**deferred，不虚假关闭**。本分支基于的 master 中，`backend/storage/db.py:list_messages()` 在查询后
  缺少 `return`，而构造 `Message` 的返回块错位到了另一函数之后，导致未打补丁的任何 `runtime.run_chat`
  都在 LLM 前报 `TypeError: 'NoneType' object is not iterable`。在一次性验收进程里临时恢复该明显错位逻辑后，
  真实 LLM/SSE 会话产生 `knowledge_add` step（81 个事件、0 error），URL 文档 `completed` 且检索命中 1 条；
  但这不等于本分支原样通过。目标集成分支已由 `a121dff`（WB-277）恢复该返回逻辑且 Backend 118/118；
  可执行前置条件是把本提交集成到该目标树后，用**无 workaround**真会话复验，确认后将本条改为 `fixed`。
- commit：本提交（未 merge、未 push）。
