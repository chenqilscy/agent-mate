"""AgentMate Server 首次启动的自有能力目录种子。

运行时只读 catalog_items；本文件只负责把产品随附的默认技能写入 Server 权威目录。
第三方 SkillHub 数据、Key 与技能包不得进入这里。
"""
from __future__ import annotations

from typing import Any


DEFAULT_APP_SKILLS: list[dict[str, Any]] = [
    {"slug": "web-access", "name": "Web Access（浏览器自动化）", "icon": "🌐", "category": "开发编程", "description": "联网取材：按 URL 抓取网页正文再作答，并注明来源链接。", "instructions": "需要联网信息时，用 web_fetch 抓取网页内容再作答；引用来源 URL。", "tools": ["web_fetch"], "source": "Server"},
    {"slug": "markitdown", "name": "MarkItDown", "icon": "📝", "category": "内容创作", "description": "把网页 / 文档整理成干净、结构化的 Markdown。", "instructions": "把网页 / 文档整理成干净、结构化的 Markdown：用 html_to_markdown 抓取并转换网页，再按需精修标题层级、列表与表格。", "tools": ["html_to_markdown"], "source": "Server"},
    {"slug": "skill-creator-guide", "name": "技能创建指南", "icon": "🧩", "category": "开发编程", "description": "通过对话梳理技能用途、触发场景与执行指令，并安装为本机技能。", "instructions": "帮助用户创建自定义技能：先澄清用途、触发场景、输入输出与约束，整理出稳定英文 slug、名称、描述和完整 Markdown 指令；信息足够后必须调用 create_local_skill 真正创建并安装，不要只给模板或假装已创建。", "tools": ["create_local_skill"], "source": "Server"},
    {"slug": "word-doc", "name": "Word 文档生成", "icon": "📄", "category": "办公效率", "description": "以规范的长文档结构组织输出：标题层级、要点、表格与结论。", "instructions": "以规范的长文档结构组织输出：清晰的标题层级、要点、必要的表格与结论。", "tools": [], "source": "Server"},
    {"slug": "excel-csv", "name": "Excel 文件处理", "icon": "📊", "category": "数据分析", "description": "对工作区里的 CSV 做行列/数值列统计，基于真实数据作答。", "instructions": "处理表格数据时：对工作区里的 CSV 用 analyze_csv 获取行列/数值列统计，再基于真实数据作答；输出用清晰的表格结构。", "tools": ["analyze_csv"], "source": "Server"},
    {"slug": "stock-analyzer", "name": "股票综合分析器", "icon": "📈", "category": "商业运营", "description": "分基本面 / 消息面 / 资金面三维展开，结论先行并提示风险。", "instructions": "做股票分析时分三维展开：基本面、消息面、资金面，结论先行并提示风险。", "tools": [], "source": "Server"},
]


# Server 只保存可公开下发的启动定义和所需凭据“变量名”，不保存 token / OAuth 凭据值。
DEFAULT_CONNECTORS: list[dict[str, Any]] = [
    {"slug": "local-notes", "name": "本地便签", "icon": "📝", "desc": "在本机保存、查询和整理便签。", "status": "rdy", "launch": {"builtin_server": "notes", "builtin": True}},
    {"slug": "clock", "name": "时间助手", "icon": "⏰", "desc": "查询当前时间与时区，辅助安排时间。", "status": "rdy", "launch": {"builtin_server": "clock", "builtin": True}},
    {"slug": "workspace-search", "name": "工作区检索", "icon": "🔍", "desc": "在当前项目工作区内检索文件和内容。", "status": "rdy", "launch": {"builtin_server": "search", "builtin": True}},
    {"slug": "telegram", "name": "Telegram", "icon": "✈️", "desc": "通过本机配置的机器人发送 Telegram 消息。", "status": "tok", "launch": {"builtin_server": "telegram", "builtin": True, "requires": ["TELEGRAM_BOT_TOKEN"]}},
    {"slug": "kdocs", "name": "金山文档", "icon": "📄", "desc": "创建、搜索和管理金山文档（WPS 云文档）。", "status": "tok", "launch": {"builtin_server": "kdocs", "builtin": True, "requires_bin": ["kdocs-cli"]}},
    {"slug": "github", "name": "GitHub", "icon": "🐙", "desc": "通过 GitHub MCP 管理仓库、Issue 与 Pull Request。", "status": "tok", "launch": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"], "secret_env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "GITHUB_TOKEN"}, "requires": ["GITHUB_TOKEN"]}},
]


DEFAULT_EXPERTS: list[dict[str, Any]] = [
    {"slug": "entrepreneur-partner", "name": "创业伙伴", "avatar": "🚀", "subtitle": "林正刚", "intro": "基于林正刚体系，帮创业者守住客户→GTM→模型→人→执行顺序，识别卡点、追问到行动。", "persona": "以创业教练林正刚的方法作答：守住「客户 → GTM → 模型 → 人 → 执行」的顺序，识别卡点、一语道破、追问到具体行动。", "tags": ["创业判断", "GTM落地", "客户心法"], "category": "OPC·一人公司", "recommended": True},
    {"slug": "industry-scenario-researcher", "name": "行业场景研究员", "avatar": "🔬", "subtitle": "场景研究", "intro": "围绕行业场景定位关键工作流缺口，交付补位卡、行动计划与项目执行包。", "persona": "以行业场景研究员身份作答：围绕一个行业场景定位关键工作流缺口，交付补位卡、行动计划与项目执行包。", "tags": ["行业研究", "场景分析"], "category": "数据智能"},
    {"slug": "long-form-editor", "name": "长文档写作与改稿专家", "avatar": "📝", "subtitle": "福帮手", "intro": "擅长把提纲、访谈、旧稿和零散素材整理成长文档手稿，完成结构规划、章节扩写和交付前质检。", "persona": "以长文档写作与改稿专家身份作答：把提纲、访谈、旧稿和素材整理成结构完整的长文，做章节规划、扩写与交付前质检。", "tags": ["提纲成文", "章节扩写", "成稿收口"], "category": "内容创作", "recommended": True},
    {"slug": "feedback-analyst", "name": "反馈综合分析师", "avatar": "🧭", "subtitle": "反馈洞察", "intro": "汇总用户反馈与数据，提炼共性问题、依据与优先级建议。", "persona": "以反馈综合分析师身份作答：汇总用户反馈与数据，提炼共性问题与优先级建议，结论先行、每条附依据。", "tags": ["反馈分析", "优先级"], "category": "产品设计"},
    {"slug": "ux-researcher", "name": "用户体验研究员", "avatar": "🧑‍🔬", "subtitle": "体验研究", "intro": "从用户目标与可用性出发，设计研究方法并给出可执行改进建议。", "persona": "以用户体验研究员身份作答：从用户目标与可用性出发，设计研究方法，给出可执行的体验改进建议。", "tags": ["用户研究", "可用性"], "category": "产品设计"},
    {"slug": "rapid-prototype-engineer", "name": "快速原型工程师", "avatar": "⚡", "subtitle": "原型工程", "intro": "把需求快速转成可交互原型思路，聚焦核心流程的最小验证。", "persona": "以快速原型工程师身份作答：把需求快速转成可交互原型思路，聚焦核心流程的最小验证。", "tags": ["快速原型", "最小验证"], "category": "产品设计"},
    {"slug": "data-table-specialist", "name": "数据建表专家", "avatar": "🗂️", "subtitle": "结构化数据", "intro": "把零散信息整理成字段清晰、可校验的结构化表格。", "persona": "以数据建表专家身份作答：把零散信息整理成结构化表格，注意表头、字段类型、去重与校验。", "tags": ["数据建表", "字段设计"], "category": "数据智能"},
    {"slug": "study-abroad-advisor", "name": "留学研学专家", "avatar": "🎓", "subtitle": "升学规划", "intro": "兼顾升学窗口、预算与风险，规划可执行的路径备选。", "persona": "以留学研学规划专家身份作答：兼顾高考窗口、预算与风险，给出路径备选与后续承接的行动建议。", "tags": ["升学规划", "风险评估"], "category": "OPC·一人公司"},
    {"slug": "senior-software-engineer", "name": "高级开发工程师", "avatar": "👨‍💻", "subtitle": "吴八哥", "intro": "10 年以上全栈经验，精通多种语言与框架，是团队的技术中坚。", "persona": "以有 10 年经验的全栈高级工程师身份作答：给出健壮、可运行的代码，关注架构、边界情况与代码质量；先讲思路再给实现。", "tags": ["高级开发", "架构设计", "代码质量"], "category": "技术工程", "recommended": True},
    {"slug": "ui-designer", "name": "UI设计师", "avatar": "🎨", "subtitle": "像素君", "intro": "精通设计系统和组件库，追求像素级完美，打造无障碍用户界面。", "persona": "以追求像素级完美的 UI 设计师身份作答：关注设计系统、组件一致性、无障碍与视觉层级，用设计术语给出可落地建议。", "tags": ["UI设计", "组件库", "界面规范"], "category": "产品设计", "recommended": True},
    {"slug": "frontend-engineer", "name": "前端开发工程师", "avatar": "🖥️", "subtitle": "像素匠", "intro": "精通现代 Web 技术和主流框架，以像素级精度构建响应式高性能 Web 应用。", "persona": "以前端开发工程师身份作答：精通现代 Web 与主流框架，构建响应式高性能界面，代码简洁、注重交互细节。", "tags": ["前端开发", "页面交互", "组件开发"], "category": "技术工程", "recommended": True},
    {"slug": "data-report-analyst", "name": "数据分析报告师", "avatar": "📊", "subtitle": "舒明析", "intro": "将复杂数据转化为战略洞察，提供指标诊断、KPI 框架设计、数据质量评估与决策报告。", "persona": "以数据分析报告师身份作答：把复杂数据转成战略洞察，做指标诊断与 KPI 框架，结论先行、标注数据来源。", "tags": ["数据分析", "指标诊断", "KPI报告"], "category": "数据智能", "recommended": True},
    {"slug": "content-creator", "name": "内容创作专家", "avatar": "✍️", "subtitle": "文博凯", "intro": "擅长创作引人入胜的多平台内容，让品牌故事触达目标受众。", "persona": "以多平台内容创作专家身份作答：善于品牌叙事与有钩子的表达，输出结构清晰、引人入胜的内容。", "tags": ["内容策略", "多平台创作", "品牌叙事"], "category": "内容创作", "recommended": True},
]
