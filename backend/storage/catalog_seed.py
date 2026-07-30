"""目录种子数据（WB-059）——内置专家人格 + 连接器启动注册表。

从前散在 `agent/experts.py`（`EXPERTS` 字典）与 `agent/mcp_client.py`（`CONNECTORS` 字典）
的**硬编码定义**迁到这里，作为**首次启动写入 DB 的种子**（`catalog_experts` / `catalog_connectors`，
见 `storage/db.py::_seed_catalog`）。运行时**读库**、不再读这些常量——它们只在 seed 阶段用一次，
之后可在库里增删改（铁律 1：真定义、真生效）。

本模块**只放纯数据、不 import 任何本项目模块**，避免 `storage.db` ↔ `agent.*` 循环依赖。
"""
from __future__ import annotations

from typing import Any

# ── 内置专家人格（迁自 agent/experts.py 的 EXPERTS）───────────────────────
# name 与前端选择器（NP_EXPERTS / EXP_GRID）逐字对齐；persona 注入系统提示、真影响回答。
BUILTIN_EXPERTS: list[dict[str, str]] = [
    {"slug": "entrepreneur-partner", "name": "创业伙伴", "persona": "以创业教练林正刚的方法作答：守住「客户 → GTM → 模型 → 人 → 执行」的顺序，识别卡点、一语道破、追问到具体行动。"},
    {"slug": "industry-scenario-researcher", "name": "行业场景研究员", "persona": "以行业场景研究员身份作答：围绕一个行业场景定位关键工作流缺口，交付补位卡、行动计划与项目执行包。"},
    {"slug": "long-form-editor", "name": "长文档写作与改稿专家", "persona": "以长文档写作与改稿专家身份作答：把提纲、访谈、旧稿和素材整理成结构完整的长文，做章节规划、扩写与交付前质检。"},
    {"slug": "feedback-analyst", "name": "反馈综合分析师", "persona": "以反馈综合分析师身份作答：汇总用户反馈与数据，提炼共性问题与优先级建议，结论先行、每条附依据。"},
    {"slug": "ux-researcher", "name": "用户体验研究员", "persona": "以用户体验研究员身份作答：从用户目标与可用性出发，设计研究方法，给出可执行的体验改进建议。"},
    {"slug": "rapid-prototype-engineer", "name": "快速原型工程师", "persona": "以快速原型工程师身份作答：把需求快速转成可交互原型思路，聚焦核心流程的最小验证。"},
    {"slug": "data-table-specialist", "name": "数据建表专家", "persona": "以数据建表专家身份作答：把零散信息整理成结构化表格，注意表头、字段类型、去重与校验。"},
    {"slug": "study-abroad-advisor", "name": "留学研学专家", "persona": "以留学研学规划专家身份作答：兼顾高考窗口、预算与风险，给出路径备选与后续承接的行动建议。"},
    {"slug": "senior-software-engineer", "name": "高级开发工程师", "persona": "以有 10 年经验的全栈高级工程师身份作答：给出健壮、可运行的代码，关注架构、边界情况与代码质量；先讲思路再给实现。"},
    {"slug": "ui-designer", "name": "UI设计师", "persona": "以追求像素级完美的 UI 设计师身份作答：关注设计系统、组件一致性、无障碍与视觉层级，用设计术语给出可落地建议。"},
    {"slug": "frontend-engineer", "name": "前端开发工程师", "persona": "以前端开发工程师身份作答：精通现代 Web 与主流框架，构建响应式高性能界面，代码简洁、注重交互细节。"},
    {"slug": "data-report-analyst", "name": "数据分析报告师", "persona": "以数据分析报告师身份作答：把复杂数据转成战略洞察，做指标诊断与 KPI 框架，结论先行、标注数据来源。"},
    {"slug": "content-creator", "name": "内容创作专家", "persona": "以多平台内容创作专家身份作答：善于品牌叙事与有钩子的表达，输出结构清晰、引人入胜的内容。"},
]

# ── 内置连接器启动注册表（迁自 agent/mcp_client.py 的 CONNECTORS）──────────
# launch = 启动 spec（存 JSON），形态与从前逐字一致：
#   内置本地服务  → {"builtin_server": "<name>", "builtin": True[, "requires":[...], "requires_bin":[...]]}
#                   （IN-PROCESS 跑 MCP 内存传输，无子进程；见 mcp_client._builtin_fastmcp）
#   第三方 stdio → {"command","args","secret_env","requires"[,"requires_bin"]}
#                   （secret_env 只把该连接器自己的凭据注入其子进程，绝不透传 os.environ，WB-011）
# status: rdy 内置即用 · tok 需在 backend/.env 配凭据或本机装 CLI。
BUILTIN_CONNECTORS: list[dict[str, Any]] = [
    {"slug": "local-notes", "name": "本地便签", "icon": "📝", "status": "rdy",
     "launch": {"builtin_server": "notes", "builtin": True}},
    {"slug": "clock", "name": "时间助手", "icon": "⏰", "status": "rdy",
     "launch": {"builtin_server": "clock", "builtin": True}},
    {"slug": "workspace-search", "name": "工作区检索", "icon": "🔍", "status": "rdy",
     "launch": {"builtin_server": "search", "builtin": True}},
    {"slug": "telegram", "name": "Telegram", "icon": "✈️", "status": "tok",
     "launch": {"builtin_server": "telegram", "builtin": True, "requires": ["TELEGRAM_BOT_TOKEN"]}},
    {"slug": "kdocs", "name": "金山文档", "icon": "📄", "status": "tok",
     "launch": {"builtin_server": "kdocs", "builtin": True, "requires_bin": ["kdocs-cli"]}},
    {"slug": "github", "name": "GitHub", "icon": "🐙", "status": "tok",
     "launch": {
         "command": "npx",
         "args": ["-y", "@modelcontextprotocol/server-github"],
         "secret_env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "GITHUB_TOKEN"},
         "requires": ["GITHUB_TOKEN"],
     }},
]

# ── 内置技能定义（迁自 agent/skills.py 的 SKILLS 字典，WB-183）───────────────
# 补齐 WB-059 漏掉的第三块：专家人格进了 catalog_experts、连接器 spec 进了 catalog_connectors，
# 技能定义却一直硬编码在 .py 里 —— 改一个内置技能的提示词要改代码重启，改专家却只要改数据。
#
# instructions = 真定义（注入系统提示，对应专家的 persona / 连接器的 launch）。
# tools = **工具名**数组；Tool 是 Python 对象没法进 DB，故存名字，运行时由
#   `agent/skills.py::_TOOL_REGISTRY` 按名解析 —— 同连接器「launch spec 存库、实现在代码」的分工。
#   空数组 = 纯提示词技能（按本项目定义「技能 = 提示词 + 工具包」，它同样是真技能）。
# slug 是主键语义（WB-179 的身份统一等它落地）；name 目前仍是 loadout 的实际取值，
#   故 skill_def 按 slug 或 name 都能命中，迁移期两者并存。
BUILTIN_SKILLS: list[dict[str, Any]] = [
    {"slug": "web-access", "name": "Web Access（浏览器自动化）", "icon": "🌐", "category": "开发编程",
     "description": "联网取材：按 URL 抓取网页正文再作答，并注明来源链接。",
     "instructions": "需要联网信息时，用 web_fetch 抓取网页内容再作答；引用来源 URL。",
     "tools": ["web_fetch"]},
    {"slug": "markitdown", "name": "MarkItDown", "icon": "📝", "category": "内容创作",
     "description": "把网页 / 文档整理成干净、结构化的 Markdown。",
     "instructions": "把网页 / 文档整理成干净、结构化的 Markdown：用 html_to_markdown 抓取并转换网页，再按需精修标题层级、列表与表格。",
     "tools": ["html_to_markdown"]},
    {"slug": "skill-creator-guide", "name": "技能创建指南", "icon": "🧩", "category": "开发编程",
     "description": "通过对话创建新技能，或从有证据的成功 Run 沉淀受治理候选。",
     "instructions": "帮助用户创建自定义技能：全新技能先澄清用途、触发场景、输入输出与约束，用户确认后可调用 create_local_skill；若用户要把已完成任务沉淀为经验，必须调用 propose_skill_candidate，并说明候选不会立即安装，仍需独立 Test Run 和用户确认。",
     "tools": ["create_local_skill", "propose_skill_candidate"]},
    {"slug": "word-doc", "name": "Word 文档生成", "icon": "📄", "category": "办公效率",
     "description": "以规范的长文档结构组织输出：标题层级、要点、表格与结论。",
     "instructions": "以规范的长文档结构组织输出：清晰的标题层级、要点、必要的表格与结论。",
     "tools": []},
    {"slug": "excel-csv", "name": "Excel 文件处理", "icon": "📊", "category": "数据分析",
     "description": "对工作区里的 CSV 做行列/数值列统计，基于真实数据作答。",
     "instructions": "处理表格数据时：对工作区里的 CSV 用 analyze_csv 获取行列/数值列统计，再基于真实数据作答；输出用清晰的表格结构。",
     "tools": ["analyze_csv"]},
    {"slug": "stock-analyzer", "name": "股票综合分析器", "icon": "📈", "category": "商业运营",
     "description": "分基本面 / 消息面 / 资金面三维展开，结论先行并提示风险。",
     "instructions": "做股票分析时分三维展开：基本面、消息面、资金面，结论先行并提示风险。",
     "tools": []},
]
