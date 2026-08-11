"""AgentMate Server 首次启动的自有能力目录种子。

运行时只读 catalog_items；本文件只负责把产品随附的默认技能写入 Server 权威目录。
第三方 SkillHub 数据、Key 与技能包不得进入这里。
"""
from __future__ import annotations

from typing import Any


# 仅用于首次建库/版本升级时 `INSERT OR IGNORE` 的实现清单。工具的运营字段一旦入库，
# Server API、发布校验与 Console 均只读写 tool_catalog，不再把本文件当管理面（WB-266）。
DEFAULT_TOOL_CATALOG: list[dict[str, Any]] = [
    {"name": "list_dir", "label": "列出目录", "description": "列出项目工作区中的文件和子目录。", "category": "工作区", "risk_level": "low", "exposure": "skill", "bindable": True, "permissions": ["workspace.read"]},
    {"name": "read_file", "label": "读取文件", "description": "读取项目工作区内的文本文件。", "category": "工作区", "risk_level": "low", "exposure": "skill", "bindable": True, "permissions": ["workspace.read"]},
    {"name": "write_file", "label": "写入文件", "description": "在项目工作区创建或覆盖文本文件。", "category": "工作区", "risk_level": "medium", "exposure": "skill", "bindable": True, "permissions": ["workspace.write"]},
    {"name": "create_docx", "label": "生成 Word", "description": "原生生成并校验 DOCX 文档。", "category": "Office", "risk_level": "medium", "exposure": "deferred", "bindable": True, "permissions": ["workspace.write"]},
    {"name": "create_xlsx", "label": "生成 Excel", "description": "原生生成并校验 XLSX 工作簿。", "category": "Office", "risk_level": "medium", "exposure": "deferred", "bindable": True, "permissions": ["workspace.write"]},
    {"name": "create_pptx", "label": "生成 PPT", "description": "原生生成并校验 PPTX 演示文稿。", "category": "Office", "risk_level": "medium", "exposure": "deferred", "bindable": True, "permissions": ["workspace.write"]},
    {"name": "create_pdf", "label": "生成 PDF", "description": "原生生成并重新解析校验 PDF。", "category": "Office", "risk_level": "medium", "exposure": "deferred", "bindable": True, "permissions": ["workspace.write"]},
    {"name": "inspect_office_file", "label": "检查 Office 文件", "description": "只读检查 DOCX、XLSX、PPTX 与 PDF 的结构和边界。", "category": "Office", "risk_level": "low", "exposure": "deferred", "bindable": True, "permissions": ["workspace.read"]},
    {"name": "browser_navigate", "label": "浏览器导航", "description": "使用隔离且可复用登录态的浏览器打开公共网页。", "category": "浏览器", "risk_level": "medium", "exposure": "deferred", "bindable": True, "permissions": ["network.read", "browser.state"]},
    {"name": "browser_read", "label": "读取浏览器", "description": "读取当前网页的可见文本、链接和表单控件。", "category": "浏览器", "risk_level": "low", "exposure": "deferred", "bindable": True, "permissions": ["network.read", "browser.state"]},
    {"name": "browser_interact", "label": "操作浏览器", "description": "在提交前确认门禁下操作网页、上传、下载和截图。", "category": "浏览器", "risk_level": "high", "exposure": "deferred", "bindable": True, "permissions": ["network.read", "browser.state", "workspace.write"]},
    {"name": "run_command", "label": "运行命令", "description": "在工作区执行有超时的本机 shell 命令；具备主机与网络高权限。", "category": "系统", "risk_level": "critical", "exposure": "skill", "bindable": True, "permissions": ["workspace.read", "workspace.write", "process.execute", "host.unrestricted", "network.unrestricted"]},
    {"name": "update_plan", "label": "更新计划", "description": "更新当前任务的结构化待办与进度。", "category": "任务", "risk_level": "low", "exposure": "skill", "bindable": True, "permissions": ["run.plan.write"]},
    {"name": "web_fetch", "label": "网页抓取", "description": "按 URL 抓取公共网页正文，用于联网取材。", "category": "网络", "risk_level": "low", "exposure": "skill", "bindable": True, "permissions": ["network.read"]},
    {"name": "html_to_markdown", "label": "网页转 Markdown", "description": "抓取网页并转换为结构化 Markdown。", "category": "网络", "risk_level": "low", "exposure": "skill", "bindable": True, "permissions": ["network.read"]},
    {"name": "analyze_csv", "label": "CSV 分析", "description": "读取工作区 CSV 并返回真实行列与数值统计。", "category": "数据", "risk_level": "low", "exposure": "skill", "bindable": True, "permissions": ["workspace.read"]},
    {"name": "create_local_skill", "label": "创建本地技能", "description": "经用户确认后创建并安装一个真实的本地技能。", "category": "技能系统", "risk_level": "high", "exposure": "internal", "bindable": False, "permissions": ["skill.manage"]},
    {"name": "propose_skill_candidate", "label": "沉淀技能候选", "description": "从有验收证据的成功 Run 创建受治理 Skill 候选，不直接安装或发布。", "category": "技能系统", "risk_level": "medium", "exposure": "internal", "bindable": False, "permissions": ["skill.manage", "run.read"]},
    {"name": "list_work_items", "label": "列出项目工作项", "description": "在项目 Run 中列出计划项及状态。", "category": "项目上下文", "risk_level": "low", "exposure": "contextual", "bindable": False, "permissions": ["project.read"]},
    {"name": "list_my_action_items", "label": "列出我的行动项", "description": "跨已授权项目读取当前账号的今日行动项。", "category": "工作入口", "risk_level": "low", "exposure": "automatic", "bindable": False, "permissions": ["project.read"]},
    {"name": "start_work_item_run", "label": "启动行动项执行", "description": "把用户明确选中的 Server WorkItem 交给当前 Local Agent 执行。", "category": "工作入口", "risk_level": "medium", "exposure": "automatic", "bindable": False, "permissions": ["project.write"]},
    {"name": "set_work_item_status", "label": "更新工作项状态", "description": "在项目 Run 中更新当前项目工作项状态。", "category": "项目上下文", "risk_level": "medium", "exposure": "contextual", "bindable": False, "permissions": ["project.write"]},
    {"name": "knowledge_retrieve", "label": "检索知识库", "description": "检索本会话挂载的知识库并返回来源片段。", "category": "知识库", "risk_level": "low", "exposure": "contextual", "bindable": False, "permissions": ["knowledge.read", "network.read"]},
    {"name": "knowledge_add", "label": "加入知识库", "description": "把工作区文件上传到指定知识库并触发解析。", "category": "知识库", "risk_level": "high", "exposure": "contextual", "bindable": False, "permissions": ["workspace.read", "knowledge.write", "network.write"]},
    {"name": "skills_list", "label": "发现技能", "description": "列出当前用户已安装、启用且可按需加载的 Skill 精简索引。", "category": "技能系统", "risk_level": "low", "exposure": "automatic", "bindable": False, "permissions": ["skill.definition.read"]},
    {"name": "skill_view", "label": "加载技能", "description": "按固定 release 加载 Skill 正文，并在下一轮启用其声明能力。", "category": "技能系统", "risk_level": "low", "exposure": "automatic", "bindable": False, "permissions": ["skill.definition.read"]},
    {"name": "skill_list_resources", "label": "列出技能资源", "description": "列出当前 Run 已挂载 Skill 声明的资源。", "category": "技能资源", "risk_level": "low", "exposure": "automatic", "bindable": False, "permissions": ["skill.resource.read"]},
    {"name": "skill_read_resource", "label": "读取技能资源", "description": "按需读取当前 Skill release 的 UTF-8 文本资源。", "category": "技能资源", "risk_level": "low", "exposure": "automatic", "bindable": False, "permissions": ["skill.resource.read"]},
    {"name": "skill_copy_template", "label": "复制技能模板", "description": "把 Skill release 的模板原子复制到项目工作区。", "category": "技能资源", "risk_level": "medium", "exposure": "automatic", "bindable": False, "permissions": ["skill.resource.read", "workspace.write"]},
    {"name": "tool_search", "label": "发现工具", "description": "检索当前 Run 有权使用的长尾工具，并从下一轮加载命中的 schema。", "category": "工具系统", "risk_level": "low", "exposure": "automatic", "bindable": False, "permissions": ["tool.definition.read"]},
    {"name": "ask_user", "label": "询问用户", "description": "挂起当前 Run，等待用户回答关键选择后继续。", "category": "交互", "risk_level": "low", "exposure": "automatic", "bindable": False, "permissions": []},
]

for _index, _tool in enumerate(DEFAULT_TOOL_CATALOG):
    _tool.setdefault("enabled", True)
    _tool.setdefault("contract_version", "1")
    _tool.setdefault("min_app_version", "1.0.0")
    _tool.setdefault("sort", _index * 10)


DEFAULT_SKILL_CATEGORIES: list[dict[str, Any]] = [
    {"slug": "development", "name": "开发编程", "icon": "💻", "description": "开发、自动化与工程工具类技能。"},
    {"slug": "content", "name": "内容创作", "icon": "📝", "description": "写作、编辑与内容整理类技能。"},
    {"slug": "office", "name": "办公效率", "icon": "💼", "description": "文档、表格与日常办公提效技能。"},
    {"slug": "data", "name": "数据分析", "icon": "📊", "description": "数据处理、分析与洞察类技能。"},
    {"slug": "business", "name": "商业运营", "icon": "📈", "description": "商业研究、运营与决策支持技能。"},
    {"slug": "other", "name": "其他", "icon": "🧩", "description": "暂未归入其他目录的技能。"},
]

for _index, _category in enumerate(DEFAULT_SKILL_CATEGORIES):
    _category.setdefault("sort", _index * 10)


DEFAULT_APP_SKILLS: list[dict[str, Any]] = [
    {"slug": "web-access", "name": "Web Access（浏览器自动化）", "icon": "🌐", "category_slug": "development", "category": "开发编程", "description": "联网取材：按 URL 抓取网页正文再作答，并注明来源链接。", "instructions": "需要联网信息时，用 web_fetch 抓取网页内容再作答；引用来源 URL。", "tools": ["web_fetch"], "source": "Server"},
    {"slug": "markitdown", "name": "MarkItDown", "icon": "📝", "category_slug": "content", "category": "内容创作", "description": "把网页 / 文档整理成干净、结构化的 Markdown。", "instructions": "把网页 / 文档整理成干净、结构化的 Markdown：用 html_to_markdown 抓取并转换网页，再按需精修标题层级、列表与表格。", "tools": ["html_to_markdown"], "source": "Server"},
    {"slug": "skill-creator-guide", "name": "技能创建指南", "icon": "🧩", "category_slug": "development", "category": "开发编程", "description": "通过对话创建新技能，或从有证据的成功 Run 沉淀受治理候选。", "instructions": "帮助用户创建自定义技能：全新技能先澄清用途、触发场景、输入输出与约束，用户确认后可调用 create_local_skill；若用户要把已完成任务沉淀为经验，必须调用 propose_skill_candidate，并说明候选不会立即安装，仍需独立 Test Run 和用户确认。", "tools": ["create_local_skill", "propose_skill_candidate"], "source": "Server"},
    {"slug": "word-doc", "name": "Word 文档生成", "icon": "📄", "category_slug": "office", "category": "办公效率", "description": "以规范的长文档结构组织输出：标题层级、要点、表格与结论。", "instructions": "以规范的长文档结构组织输出：清晰的标题层级、要点、必要的表格与结论。", "tools": [], "source": "Server"},
    {"slug": "excel-csv", "name": "Excel 文件处理", "icon": "📊", "category_slug": "data", "category": "数据分析", "description": "对工作区里的 CSV 做行列/数值列统计，基于真实数据作答。", "instructions": "处理表格数据时：对工作区里的 CSV 用 analyze_csv 获取行列/数值列统计，再基于真实数据作答；输出用清晰的表格结构。", "tools": ["analyze_csv"], "source": "Server"},
    {"slug": "stock-analyzer", "name": "股票综合分析器", "icon": "📈", "category_slug": "business", "category": "商业运营", "description": "分基本面 / 消息面 / 资金面三维展开，结论先行并提示风险。", "instructions": "做股票分析时分三维展开：基本面、消息面、资金面，结论先行并提示风险。", "tools": [], "source": "Server"},
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


# 专家团成员只保存展示别名/角色 + 稳定专家 slug；运行人格始终引用 EXPERT_DEFS（WB-231）。
DEFAULT_EXPERT_TEAMS: list[dict[str, Any]] = [
    {
        "icon": "💻", "name": "软件开发团队", "source": "CodeBuddy Teams", "category": "技术工程",
        "intro": "高效软件研发团队，产品经理定需求、架构师设计+拆任务、工程师批量实现代码、QA 验证质量，小需求求快、大项目求稳。",
        "strengths": ["软件公司", "组织管理", "产品交付"], "tags": ["软件公司", "组织管理", "产品交付"],
        "members": [
            {"role": "技术负责人", "name": "柯睿", "expert_slug": "senior-software-engineer", "lead": True},
            {"role": "产品经理", "name": "需澄", "expert_slug": "feedback-analyst"},
            {"role": "架构师", "name": "构文", "expert_slug": "industry-scenario-researcher"},
            {"role": "后端工程师", "name": "端野", "expert_slug": "data-table-specialist"},
            {"role": "前端工程师", "name": "像素匠", "expert_slug": "frontend-engineer"},
            {"role": "QA 工程师", "name": "质衡", "expert_slug": "ux-researcher"},
        ],
        "prompts": ["帮我把这个需求拆成可执行的开发任务", "为这个功能设计一套后端接口和数据表", "评审这段代码并给出重构建议"],
    },
    {
        "icon": "🔬", "name": "深度研究团队", "source": "Expert Marketplace", "category": "数据智能",
        "intro": "深度研究报告输出，7 角色 5 阶段聚合多源信息，经审稿修订循环输出带引用的专业报告。",
        "strengths": ["深度调研", "报告撰写", "多源研究"], "tags": ["深度调研", "报告撰写", "多源研究"],
        "members": [
            {"role": "研究主编", "name": "博源", "expert_slug": "long-form-editor", "lead": True},
            {"role": "资料检索员", "name": "溯引", "expert_slug": "industry-scenario-researcher"},
            {"role": "数据分析师", "name": "析数", "expert_slug": "data-report-analyst"},
            {"role": "行业专家", "name": "业衡", "expert_slug": "entrepreneur-partner"},
            {"role": "撰稿人", "name": "文墨", "expert_slug": "content-creator"},
            {"role": "审稿人", "name": "校真", "expert_slug": "feedback-analyst"},
        ],
        "prompts": ["给我一份某赛道的深度研究报告，带数据来源", "梳理这个行业近三年的关键变化", "把这些零散资料整理成一份结构化研究简报"],
    },
    {
        "icon": "🧭", "name": "产品战略团队", "source": "Expert Marketplace", "category": "产品设计",
        "intro": "由产品总监领衔的 5 人产品专家团队：需求分析师（PRD/功能规格书）、用户研究员（调研综合分析）、原型工程师协作，从想法到规格全流程。",
        "strengths": ["产品战略", "竞品分析", "路线图规划"], "tags": ["产品战略", "竞品分析", "路线图规划"],
        "members": [
            {"role": "产品总监", "name": "策衡", "expert_slug": "entrepreneur-partner", "lead": True},
            {"role": "需求分析师", "name": "需澄", "expert_slug": "feedback-analyst"},
            {"role": "用户研究员", "name": "研之", "expert_slug": "ux-researcher"},
            {"role": "快速原型工程师", "name": "原野", "expert_slug": "rapid-prototype-engineer"},
            {"role": "数据分析师", "name": "析数", "expert_slug": "data-report-analyst"},
        ],
        "prompts": ["帮我把这个想法写成一份 PRD", "做一次竞品分析并给出差异化建议", "规划这个产品未来两个季度的路线图"],
    },
]
