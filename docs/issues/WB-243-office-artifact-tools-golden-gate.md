---
id: WB-243
title: 缺少 DOCX/XLSX/PPTX/PDF 专用生成校验工具与黄金任务门禁
severity: P1
area: backend
status: open
origin: WB-239 R1
files:
  - backend/agent/tools.py:1
  - backend/requirements.txt:1
  - backend/agentmate-backend.spec:1
  - backend/tests/golden:1
created: 2026-07-21
---

## 问题

AgentMate 只能用 `write_file` 写纯文本或用 `run_command` 调外部命令；本机后端没有 DOCX、XLSX、PPTX、PDF
专用工具和依赖。现有金山文档连接器属于可选云服务，知识库只负责解析上传文件，都不能证明本机能按
“生成 → 检查 → 修正 → 交付”完成办公任务。路线图列出的黄金任务也没有离线夹具与统一验收报告。

## 触发场景

用户要求把资料生成 Word 报告、将数据整理成带公式/图表的 Excel、制作可打开的演示文稿或合并 PDF。
模型只能输出 Markdown、尝试临时安装包或调用通用 shell；结果是否可打开、结构是否正确、页面是否溢出均不可追溯。

## 影响

P1：R1 “可交付”退出条件无法成立；Skill 卡片和任务模板即使展示办公场景，也没有稳定工具 schema、Artifact
manifest、渲染/结构校验与 sidecar 打包保证，真机和自动化运行会因本机环境不同而漂移。

## 建议修法

- 引入并固定 `python-docx`、`openpyxl`、`python-pptx`、`reportlab`、`pypdf`，纳入 sidecar 打包；
- 新增窄而真实的 `create_docx`、`create_xlsx`、`create_pptx`、`create_pdf` 与 `inspect_office_file` 工具，
  输入采用结构化 JSON，不让模型拼二进制或依赖任意 shell；
- 每个工具在沙箱内原子写入，返回 Artifact descriptor 和格式专属验证（段落/表/公式/图表/页数等）；
- 建立 10 个黄金任务定义与可机器执行的离线门禁，首批至少覆盖四种办公文件和已有文本/项目/自动化/能力链路；
- 缺少字体、渲染器或浏览器时如实报告结构校验边界，不把“文件可解包”写成视觉验收通过。

## 验证

- 四类文件均由专用工具生成，能被对应库重新打开，且 Artifact manifest 哈希与磁盘一致；
- XLSX 公式/图表、PPTX 页与文本框边界、DOCX 标题/表格、PDF 页数与文本可自动核对；
- 非法路径和格式错误不留下半成品，计划模式不暴露写工具；
- sidecar spec 收集运行模块，生产构建与离线黄金门禁通过；
- 真 LLM 分别调用至少一个办公工具并产生可下载 Artifact，临时产物验收后清理。
