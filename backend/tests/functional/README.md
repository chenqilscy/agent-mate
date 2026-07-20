# 细致功能自动化测试（functional / E2E）

对**真实运行的后端**做端到端功能测试。核心原则：断言**真实副作用**（磁盘文件、
SQLite 行、SSE 工具事件）这一 ground truth，而**不是** LLM 的措辞——所以即便走真实
LLM，断言依然确定、不 flaky。一个指令性 prompt 诱发某个动作，流式读到决定性事件
（`diff` / `step` / `work_item`）后**立即停止该 run**（副作用已落地），再核对磁盘/DB。

## 覆盖

| 套件 | 功能 | 要点 |
|---|---|---|
| `test_A_chat.py` | 新建任务 / agent 运行时 | write/read/run_command/list_dir 真实副作用、update_plan、plan 只读、ask 零工具、停止复位、refs 不持久、多轮记忆、持久化回放 |
| `test_B_projects.py` | 项目 | 沙箱隔离、项目指令真注入、计划项回写（DB+SSE）、成员写闸/访问隔离；含 WB-050 回归断言（B8） |
| `test_C_skills_connectors.py` | 技能·连接器 | 时钟/便签/检索连接器真返回数据、web_fetch/analyze_csv 技能工具、GitHub 未就绪、plan 禁连接器（专家不在范围） |
| `test_D_automation.py` | 自动化 | 校验+CRUD、run-now 真跑到完成并持久化、在飞去重、**调度器到点真触发**、绑定归属、停用不触发 |
| `test_E_project_kb_system_settings.py` | 项目知识库 · 系统设置 | 项目 `knowledge_ids` 创建/修改/权限/SQLite 真值；系统设置默认/持久化/owner 隔离/非法值（不调用 LLM） |

## 前置

- 后端跑在 `:8101`，且 `backend/.env` 配了真实 LLM（`LLM_API_KEY` 等）。
- 用项目 venv 跑：`backend/.venv/Scripts/python.exe`。
- 每个套件用一个一次性账号（`atest_*`/`btest_*`/`ctest_*`/`dtest_*`）跑完即**全量清理**其数据。

## 运行

```bash
# 全部
backend/.venv/Scripts/python.exe backend/tests/functional/run_all.py
# 单个
backend/.venv/Scripts/python.exe backend/tests/functional/test_B_projects.py
```

退出码：`0` 通过 · `1` 有失败 · `2` 未配置 LLM（行为类跳过）。

## 环境变量（可选覆盖）

- `AGENTMATE_TEST_BASE`（默认 `http://127.0.0.1:8101/api`）
- `AGENTMATE_DB`（默认 `backend/agentmate.db`）——须与后端所用 DB 一致才能核对副作用
- `AGENTMATE_WORKSPACE`（默认 `backend/workspace`）

## 注意

- 是**集成测试**，需真后端 + 真 LLM，非纯单元测试；会产生真实 LLM 调用。
- `agentmate_testkit.stream()` 内置 2s 节流，避免连跑触发 LLM 端点限流。
- 需与后端所用的**同一个** SQLite 库对齐（副作用断言直接读该库）。
