---
id: WB-059
title: 目录「真定义」入库 —— 内置专家人格 + 连接器启动注册表 从硬编码迁到 DB
severity: P2
area: backend
status: fixed
origin: 既有实现
files:
  - backend/agent/experts.py:9
  - backend/agent/mcp_client.py:70
  - backend/agent/runtime.py:236
  - backend/storage/db.py:134
  - backend/storage/models.py:77
created: 2026-07-07
---

## 问题

两处「真生效」的能力定义是硬编码的：

- 内置专家人格 13 条：[experts.py:9-23](../../backend/agent/experts.py#L9-L23)（`EXPERTS: dict[str,str]`，`persona_for()` 查字典注入系统提示）。
- 连接器启动注册表 6 个：[mcp_client.py:70-93](../../backend/agent/mcp_client.py#L70-L93)（`CONNECTORS: dict`，`builtin_server`/`command`/`secret_env`/`requires` 决定怎么 spawn MCP）。

它们真影响运行（人格注入 [runtime.py:236-239](../../backend/agent/runtime.py#L236-L239)、连接器接入 MCP），但无法在运行时/管理端维护——改一条要动代码发版。自造专家已入库（`experts` 表，WB-049），内置人格与连接器却没有。

## 触发场景

运营方/管理员想新增或调整一个内置专家人格、或接入一个新连接器，只能改 `experts.py`/`mcp_client.py` 重新发版；无统一目录表可读写。

## 影响

P2（择机）：不阻断现有功能，但它是 Hub 目录（[WB-058](WB-058-hub-control-plane-epic.md)）的地基。本阶段先把「真定义」落到**本地 backend 库**，运行时改读库，纯本地即可交付、独立验证。

## 建议修法

按 [架构设计 §5](../agentmate-hub-架构设计.md) 的目录模型：

### 后端
- `storage/db.py`：新增 `catalog_experts` 与 `catalog_connectors` 表（沿用幂等建表 `CREATE TABLE IF NOT EXISTS` + 必要时 `_migrate`）。
  - `catalog_experts`：并入现有 `experts` 表理念——`scope`（builtin/org/user）、`functional`(persona 是否真注入)、`owner_id`、`persona`、展示字段。现有自造专家视为 `scope='user'`。
  - `catalog_connectors`：`status`（rdy/tok/catalog）、`launch`(json：builtin_server/command/args/secret_env/requires)、展示字段。
  - **种子（seed）**：首次启动把现有 13 内置人格 / 6 连接器作为 `scope='builtin'` 写入（幂等，仅当缺失时）。
- `agent/experts.py`：`persona_for(name)` 改为**先查库**（当前 owner 的 user 专家 + builtin），命中优先，查不到再退化通用人格。保留纯函数签名以最小改 runtime。
- `agent/mcp_client.py`：`CONNECTORS`/`is_connector`/spec 解析改为**读库**（builtin 种子 + org/user 追加）；`secret_env`/`requires` 语义不变（凭据仍只在 `backend/.env`，铁律 4/11）。
- `storage/models.py`：新增对应 dataclass。

### 不做
- 不动橱窗目录（那是 [WB-060](WB-060-catalog-showcase-to-db.md)）；不引入 Hub/同步（那是 P1+）。

## 验证

- `backend/.venv/Scripts/python.exe -m py_compile` 改动的 .py 全过。
- 硬重启 :8000（Windows reload 不生效）：
  - 库里能查到 13 内置人格 + 6 连接器种子；`GET /api/experts`（自造）仍正常。
  - 召唤一个内置专家（如「创业伙伴」）发消息，回答带该人格 → 确认**读库后人格仍真注入**（对比迁移前）。
  - 挂一个内置连接器（如「本地便签」）跑一次工具调用成功 → 确认**读库后连接器仍真接入 MCP**。
  - 在库里改一条内置人格/新增一条连接器定义（不改代码），重启后生效。
- owner 隔离：user 专家仅本 owner 可见（对齐 WB-013）；builtin 全局可见。
- 回归：`backend/tests/functional` 相关用例（test_C_skills_connectors 等）通过。

## 处理记录（2026-07-07）

- 改动：
  - `storage/catalog_seed.py`（新，纯数据、无 import 防 db↔agent 循环依赖）：`BUILTIN_EXPERTS`（13 人格，逐字迁自旧 `EXPERTS`）+ `BUILTIN_CONNECTORS`（6 连接器启动 spec，逐字迁自旧 `CONNECTORS`）。
  - `storage/models.py`：新增 `CatalogExpert` / `CatalogConnector` dataclass。
  - `storage/db.py`：新增 `catalog_experts` / `catalog_connectors` 表（`CREATE TABLE IF NOT EXISTS` + name 索引，均为新表、老库仅新增不动既有）；`init_db` 末尾加 `_seed_catalog()`（幂等：按 `scope='builtin'` + name 查重，缺失才插，已存在/被改过的不覆盖）；DAO：`builtin_persona` / `list_catalog_experts` / `connector_specs` / `list_catalog_connectors`（+ 两个 `_row_to_*`）。
  - `agent/experts.py`：删掉硬编码 `EXPERTS` 字典；`persona_for(name)` 改读 `db.builtin_persona(name)`，签名不变、命中优先、查不到回退通用人格。
  - `agent/mcp_client.py`：删掉硬编码 `CONNECTORS` 字典与 `_local` 辅助；新增 `connector_specs()`（读 `db.connector_specs()`，局部 import 防循环）；`is_connector` 改读库；`open_connectors` 循环前 `specs = connector_specs()`、`spec = specs.get(name)`。
  - **未动**：自造专家（`experts` 表 / WB-049）与 `runtime.py`——已是 DB、行为不变；用户专家表统一并入目录表留给后续（WB-060/063）。
- 验证：
  - `py_compile` 改动 5 个 .py 全过。
  - 隔离库 smoke：13/6 种子；`builtin_persona`/`persona_for` 读库 + 未知回退；`connector_specs` 6 条 spec 全对（builtin_server/command/secret_env/requires/requires_bin）；`init_db` 幂等；`时间助手`/`工作区检索` 经 DB spec **真接入 MCP**（列到 now/today/days_until/search_files/list_workspace，无 skip）；GitHub 无 token 干净跳过；改库即生效（改 persona / disable 连接器）。
  - 真库副本迁移：既有 4 用户 / 8 项目原样保留，catalog 表新建种入 13/6，重跑幂等无重复。
  - **硬重启 :8000**（Windows reload=False，杀 PID 重启）后 `/api/health` 200、seed 在真库启动无碍。
  - 实时召唤对话：`experts=["创业伙伴"]` → loadout「已加载 · 专家 创业伙伴」→ **真实 LLM 回答带林正刚现金流人格**（"别给客户当银行——应收超60天的单子，宁可不做。"）→ 读库后人格真注入、真影响回答。
  - 实时连接器对话：`connectors=["时间助手"]` → loadout 加载 + agent **真调 MCP `now`** → "2026年7月7日 早上07:04"。
  - 回归 `test_C_skills_connectors`：**15/15 通过**（连接器真加载·真工具、GitHub·Telegram 未就绪门控、plan 模式禁用），自带清理。
- commit：未提交（共享工作树，待用户确认）。改动集中在 `backend/storage/{catalog_seed.py,models.py,db.py}` + `backend/agent/{experts.py,mcp_client.py}`。
