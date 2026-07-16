---
id: WB-175
title: 会话内 agent 无法「把文件加入知识库」—— 补 knowledge_add 工具（工作区文件 → 挂载的 WeKnora 库）
severity: P2
area: backend
status: fixed
origin: 用户反馈（功能不完整）
files:
  - backend/agent/tools.py
  - backend/agent/runtime.py
created: 2026-07-16
---

## 问题

[[WB-173]] 接通 WeKnora 后，会话内 agent **只有 `knowledge_retrieve`（检索）**，没有「把文件加入知识库」的工具。
用户在对话里让助理把工作区文件（如 `客服模块-功能业务文档.md`）传进知识库，助理答「当前工具集未提供上传/添加文件到知识库」，
只能退而求其次读文件回答——**功能不完整**。知识库页 UI 能传档，但对话里不能，割裂。

## 影响

P2：能力补全。WeKnora 支持三种入库（`docs/api/knowledge.md`）：
`POST /knowledge-bases/:id/knowledge/file`（multipart，字段 `file`）、`/url`（`{url,…}`）、`/manual`（`{title,content}`）。
其中 **file 已实测干净可用**（pending→completed→可检索）；`manual` 建的是 `draft/disabled`（需额外处理才可检索）、
`url` 受 WeKnora SSRF 白名单限制（`example.com` 即被拦）。故本条只补**最可靠的 file 路径**，text/url 留后续。

## 建议修法

**范围 `backend/`。** 复用 [[WB-173]] 的 `weknora.upload_file` + 沙箱读文件。

1. **`backend/agent/tools.py`**：加 `knowledge_add` 工具——参数 `path`（工作区相对路径）+ 可选 `knowledge_id`
   （多库挂载时指定目标；单库省略即用它）。`resolve_in_sandbox(path)` 读字节（≤50MB、扩展名过 `weknora.SUPPORTED_EXTS`），
   `weknora.upload_file` 传入挂载的库；返回「已加入，正在解析向量化」。未挂载/未配置/越界/超限/类型不符 → 可读提示。
   `pre` 发 `step` 事件（与 `knowledge_retrieve` 同款 trace）。
2. **`backend/agent/runtime.py`**：`kb_tools` 里把 `knowledge_add` 与 `knowledge_retrieve` 一起加（`active_knowledge and not ask`）；import 补 `knowledge_add`。
3. system_prompt 的「已挂载知识库」提示补一句：需要把工作区文件沉淀进库时用 `knowledge_add`。

## 验证

- `py_compile`；真机（WeKnora :37200）驱动 `knowledge_add` 工具：把工作区文件加入一个挂载的库 → 轮询 parse_status
  到 completed → `knowledge_retrieve` 能检索到该文件内容。未挂载/越界/超限/坏类型的错误路径各验一次。

## 处理记录

2026-07-16 · 补齐会话内「加入知识库」能力。

**改动**（backend-only；`weknora.py` 复用 [[WB-173]] 的 `upload_file`/`SUPPORTED_EXTS`，未改）：
- `agent/tools.py`：新增 `knowledge_add` 工具（+`import mimetypes`、`KB_MAX_UPLOAD=50MB`）。参数 `path`
  +可选 `knowledge_id`；沙箱 `resolve_in_sandbox` 读文件 → 扩展名/大小/存在性校验 → `weknora.upload_file` 传入挂载库。
  目标库解析：显式 knowledge_id（须已挂载）／单库自动／多库要求指定。`pre` 发 step 事件。
- `agent/runtime.py`：`kb_tools = [knowledge_retrieve, knowledge_add]`；import 补 `knowledge_add`；
  system_prompt「已挂载知识库」提示补一句「加入/上传到知识库用 knowledge_add」。

**验证**（真机 WeKnora :37200，直接驱动工具）：
- happy：把工作区 `客服文档.md` 加入挂载库 → 轮询 parse_status pending→completed → `knowledge_retrieve`
  以「客服工单多久响应」命中该文件（相关度 0.740）。
- 错误路径逐一：无 path / 文件不存在 / 不支持类型(.exe) / 路径越界(../../ 被沙箱拦) / 未挂载 —— 均返回可读提示。
- `py_compile` 通过；改后**硬重启 backend(:8000)** 使工具在真会话生效。

**未做（留后续）**：`/knowledge/manual`（文本入库建的是 draft/disabled，需额外处理才可检索）与 `/knowledge/url`
（受 WeKnora SSRF 白名单限制）暂不接为工具——本条只补最可靠的工作区文件路径。
