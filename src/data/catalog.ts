// Static catalog data migrated from the prototype. These back the P2 views
// (experts / skills / connectors / automation / inspiration) with real static
// content until their APIs land in M5+ (spec section 7).

export const QUICK: Record<string, [string, string][]> = {
  day: [['📄', '文档处理'], ['💹', '金融服务'], ['🎓', '高考我帮你'], ['⋯', '更多']],
  code: [['🔍', '代码评审'], ['📜', '生成脚本'], ['🐞', '修复 Bug'], ['⋯', '更多']],
  design: [['🖼️', '海报设计'], ['✏️', '文案创意'], ['🎨', '配色方案'], ['⋯', '更多']],
}

export const PROJ_TPL: [string, string, string][] = [
  ['🧭', '产品需求全流程', '从需求规划、PRD 到研发测试验收'],
  ['🔍', '市场调研与竞品分析', '深度调研、竞品拆解、报告评审'],
  ['📚', '团队知识库', '持续沉淀 SOP、经验和 FAQ'],
  ['📦', '项目交付', '管理客户需求、计划、风险和周报'],
  ['🐞', 'Bug 跟踪/测试验收', '持续跟踪 Bug，统一测试用例和验收结论'],
]

export const EXP_SCENES: [string, string[]][] = [
  ['内容创作', ['内容创作专家', '长文档写作与改稿专家']],
  ['小微企业', ['创业伙伴']],
  ['数据分析', ['数据分析报告师', '深度研究团队']],
]

export const EXP_CATS = ['全部', 'OPC·一人公司', '产品设计', '技术工程', '数据智能', '内容创作']

// [icon, name, subtitle, badge, desc, tags, category(∈EXP_CATS)]
export const EXP_GRID: [string, string, string, string, string, string[], string][] = [
  ['👨‍💻', '高级开发工程师', '吴八哥', '', '10 年以上全栈经验，精通多种语言与框架，是团队的技术中坚。', ['高级开发', '架构设计', '代码质量'], '技术工程'],
  ['✍️', '内容创作专家', '文博凯', '', '擅长创作引人入胜的多平台内容，让品牌故事触达目标受众。', ['内容策略', '多平台创作', '品牌叙事'], '内容创作'],
  ['🚀', '创业伙伴', '林正刚', '', '基于林正刚体系，帮创业者守住客户→GTM→模型→人→执行顺序，识别卡点、追问到行动。', ['创业判断', 'GTM落地', '客户心法'], 'OPC·一人公司'],
  ['📊', '数据分析报告师', '舒明析', '', '将复杂数据转化为战略洞察，提供指标诊断、KPI 框架设计、数据质量评估与决策报告。', ['数据分析', '指标诊断', 'KPI报告'], '数据智能'],
  ['📝', '长文档写作与改稿专家', '福帮手', '', '擅长把提纲、访谈、旧稿和零散素材整理成长文档手稿，完成结构规划、章节扩写和交付前质检。', ['提纲成文', '章节扩写', '成稿收口'], '内容创作'],
  ['🎨', 'UI设计师', '像素君', '', '精通设计系统和组件库，追求像素级完美，打造无障碍用户界面。', ['UI设计', '组件库', '界面规范'], '产品设计'],
  ['🖥️', '前端开发工程师', '像素匠', '', '精通现代 Web 技术和主流框架，以像素级精度构建响应式高性能 Web 应用。', ['前端开发', '页面交互', '组件开发'], '技术工程'],
]

// 专家团（marketplace teams）。召唤专家团 = 把 members 里全部成员挂进本会话 loadout。
// members[].lead 标记主理人。这些是静态产品目录内容（同 EXP_GRID），非模拟 LLM 输出。
export interface TeamMember { role: string; name: string; lead?: boolean }
export interface ExpertTeam {
  icon: string
  name: string
  source: string          // 出品方，如 CodeBuddy Teams / Expert Marketplace / AgentMate Team
  badge?: string          // 如 特邀专家
  intro: string           // 能力介绍
  strengths: string[]     // 擅长领域
  members: TeamMember[]    // 团队成员（首个通常为主理人）
  prompts: string[]       // 试试这样问我
  category: string        // ∈ EXP_CATS
  tags: string[]
}

export const EXP_TEAMS: ExpertTeam[] = [
  {
    icon: '💻', name: '软件开发团队', source: 'CodeBuddy Teams', category: '技术工程',
    intro: '高效软件研发团队，产品经理定需求、架构师设计+拆任务、工程师批量实现代码、QA 验证质量，小需求求快、大项目求稳。',
    strengths: ['软件公司', '组织管理', '产品交付'],
    members: [
      { role: '技术负责人', name: '柯睿', lead: true },
      { role: '产品经理', name: '需澄' },
      { role: '架构师', name: '构文' },
      { role: '后端工程师', name: '端野' },
      { role: '前端工程师', name: '像素匠' },
      { role: 'QA 工程师', name: '质衡' },
    ],
    prompts: ['帮我把这个需求拆成可执行的开发任务', '为这个功能设计一套后端接口和数据表', '评审这段代码并给出重构建议'],
    tags: ['软件公司', '组织管理', '产品交付'],
  },
  {
    icon: '🔬', name: '深度研究团队', source: 'Expert Marketplace', category: '数据智能',
    intro: '深度研究报告输出，7 角色 5 阶段聚合多源信息，经审稿修订循环输出带引用的专业报告。',
    strengths: ['深度调研', '报告撰写', '多源研究'],
    members: [
      { role: '研究主编', name: '博源', lead: true },
      { role: '资料检索员', name: '溯引' },
      { role: '数据分析师', name: '析数' },
      { role: '行业专家', name: '业衡' },
      { role: '撰稿人', name: '文墨' },
      { role: '审稿人', name: '校真' },
    ],
    prompts: ['给我一份某赛道的深度研究报告，带数据来源', '梳理这个行业近三年的关键变化', '把这些零散资料整理成一份结构化研究简报'],
    tags: ['深度调研', '报告撰写', '多源研究'],
  },
  {
    icon: '🧭', name: '产品战略团队', source: 'Expert Marketplace', category: '产品设计',
    intro: '由产品总监领衔的 5 人产品专家团队：需求分析师（PRD/功能规格书）、用户研究员（调研综合分析）、原型工程师协作，从想法到规格全流程。',
    strengths: ['产品战略', '竞品分析', '路线图规划'],
    members: [
      { role: '产品总监', name: '策衡', lead: true },
      { role: '需求分析师', name: '需澄' },
      { role: '用户研究员', name: '研之' },
      { role: '快速原型工程师', name: '原野' },
      { role: '数据分析师', name: '析数' },
    ],
    prompts: ['帮我把这个想法写成一份 PRD', '做一次竞品分析并给出差异化建议', '规划这个产品未来两个季度的路线图'],
    tags: ['产品战略', '竞品分析', '路线图规划'],
  },
]

// SK_RECO 已删除（WB-184）：前端**零消费**（全仓库只有本处定义 + catalogStore 的类型/兜底
// 各一处引用），是原型迁移遗留的死代码。原型 tencent-workbuddy-reference.html:1361 用过，React 版从未渲染。

// 推荐技能由后端 catalog_skills 真定义表生成。静态层只保留空类型兜底，后端不可用时诚实空态，
// 不再复制一份会漂移的展示名/category/slug 快照（WB-183/184/195）。
export interface RecommendedSkill {
  slug: string
  name: string
  icon: string
  description: string
  category: string
  source?: string
}
export const SK_CATS: string[] = []
export const SK_GRID: RecommendedSkill[] = []

export const CONNS: [string, string, string][] = [
  ['📉', '通达信', '通过通达信 MCP 查询全球股票行情数据、条件选股、研究报告、公告资讯和宏观信息。'],
  ['✉️', 'QQ邮箱', '收发、搜索和整理 QQ 邮件。用自然语言读取邮件内容、汇总邮件线程、管理文件夹。'],
  ['📚', 'WeKnora知识库', '检索自托管 WeKnora 知识库里的资料并据实作答；把工作区文件加入知识库，自动解析、切片与向量化。'],
  ['🎦', '腾讯会议', '通过命令行创建、查询和管理腾讯会议。支持快速发起会议、查看日程安排。'],
  ['💬', '企业微信', '企业微信 10 人及以下企业支持消息、文档、日程、会议、待办等 MCP 能力。'],
  ['🕊️', '飞书', '通过命令行管理飞书/Lark 全产品能力：即时通讯、邮箱、日历、云文档、多维表格等。'],
  ['🔷', '钉钉', '通过命令行管理钉钉全产品能力：AI 表格、考勤、日历、群聊机器人、通讯录等。'],
  ['📄', '金山文档', '创建、搜索和管理金山文档（WPS 云文档）。支持新建多种文档类型（Word/Excel/PDF/PPT/智能表格/多维表格/智能文档）、读取与搜索文档内容、编辑更新、分享、移动重命名整理、标签收藏管理、知识库空间操作、网页剪藏，以及接龙转表格、AI PPT 生成等。'],
]

// 连接器详情元数据（按连接器名索引）。目录卡片只有 [icon,name,desc]；有 CONN_META 的
// 连接器可点开详情弹窗，展示状态、启用方式、真实能力清单（镜像后端桥接的工具，非伪造）与
// 试用问法。status: 'rdy' 内置即用 / 'tok' 需在 backend/.env 配置凭据（见 setup）。
export interface ConnTool { name: string; desc: string }
export interface ConnMeta {
  status: 'rdy' | 'tok'
  statusLabel: string
  // oauth: 详情弹窗走「连接」授权流（后端 /api/connectors/kdocs/*），点「连接」跳转
  // WPS 授权页；连上后才展示去试试/添加。非 oauth 连接器沿用静态展示。
  oauth?: boolean
  // configKind: 详情弹窗把「启用方式」渲染成真表单（配置存后端 DB，不用改 .env）。
  // 'weknora' → 服务地址 / API Key / 嵌入模型 id + 保存 + 测试连接（WB-188）。
  configKind?: 'weknora'
  setup?: string          // 'tok'/oauth 连接器的启用说明（有 configKind 时作表单上方的说明）
  fullDesc: string        // 详情弹窗里的完整能力介绍
  tools: ConnTool[]       // 真实工具清单，逐字对应后端 mcp_servers/kdocs.py
  prompts?: string[]      // 「试试这样问我」
}

export const CONN_META: Record<string, ConnMeta> = {
  // 自托管 WeKnora（WB-173/175）：知识库能力已真接后端，tools 逐字对应
  // backend/agent/tools.py 的 knowledge_retrieve / knowledge_add。
  WeKnora知识库: {
    status: 'tok',
    statusLabel: '需连接',
    configKind: 'weknora',
    setup: '填下面的表单即可接入，无需改配置文件、无需重启：API Key 在 WeKnora 账号页获取（sk- 开头的租户 Key）。填写的配置只存本机后端（密钥绝不回前端），可随时「测试连接」核验。WeKnora 本身的部署与嵌入模型注册见 docs/weknora-部署.md。',
    fullDesc: '接入你本机自托管的 WeKnora（腾讯开源 RAG）知识库：解析、切片、向量化与检索全在本机完成，资料不出本机。在「知识库」里把库挂到会话后，遇到需要事实依据的问题会先检索知识库、再基于命中内容作答并注明来源；也可以直接把工作区里的文件加入知识库沉淀下来。',
    tools: [
      { name: 'knowledge_retrieve', desc: '在挂载到本会话的知识库里语义检索，返回命中的原文片段与来源文件。' },
      { name: 'knowledge_add', desc: '把工作区里的一个文件加入知识库，由 WeKnora 解析/切片/向量化后即可被检索（支持 pdf/doc(x)/ppt(x)/xls(x)/txt/md/html/csv/图片，单文件≤50MB）。' },
    ],
    prompts: [
      '先检索知识库，再回答：我们的报销流程是什么？',
      '把工作区里的 README.md 加入知识库',
    ],
  },
  金山文档: {
    status: 'tok',
    statusLabel: '需连接',
    oauth: true,
    setup: '点「连接」会跳转到 WPS 授权页完成登录授权，成功后即可让 AI 直接操作你的金山文档（凭据仅存于本机，不进前端）。需本机已安装金山文档命令行工具 kdocs-cli。',
    fullDesc: '创建、搜索和管理金山文档（WPS 云文档）。支持新建多种文档类型（Word/Excel/PDF/PPT/智能表格/多维表格/智能文档）、读取与搜索文档内容、编辑更新、分享、移动重命名整理、标签收藏管理、知识库空间操作、网页剪藏，以及接龙转表格、AI PPT 生成等。',
    tools: [
      { name: 'search_files', desc: '在云盘中按文件名或全文搜索文件（夹），拿到 file_id 供后续操作。' },
      { name: 'read_file', desc: '按 URL / file_id / link_id 读取文档正文，返回 Markdown、纯文本或结构化数据。' },
      { name: 'create_doc', desc: '一步新建并写入内容，按后缀决定类型（.otl 智能文档 / .docx / .pdf / .xlsx）。' },
      { name: 'list_files', desc: '列出指定云盘目录下的子文件（夹）。' },
      { name: 'share_file', desc: '开启文件分享并返回分享链接（所有人 / 仅企业 / 指定用户）。' },
      { name: 'scrape_url', desc: '网页剪藏：抓取网页内容并自动保存为智能文档。' },
      { name: 'generate_ppt', desc: 'AI PPT：输入一句话主题，联网研究后生成可下载的演示文稿。' },
      { name: 'run', desc: '通用透传：调用 drive / sheet / otl / dbsheet / form / wpp / aippt / wps / pdf / kwiki 全部 170+ 动作。' },
      { name: 'list_actions', desc: '查询任意服务 / 动作的参数说明（等价 --help），供 run 精确调用。' },
    ],
    prompts: [
      '搜索我金山文档里最近的周报并总结要点',
      '把这个网页剪藏进我的金山文档：<粘贴网页链接>',
      '用金山文档帮我新建一份本周工作周报（.otl）',
    ],
  },
}

export const AUTO: [string, string, string][] = [
  ['📰', '每日 AI 新闻推送', '关注当天 AI 领域的重要动态，侧重 AI coding 与具身智能进展，筛选 3-5 条值得关注…'],
  ['🔤', '每日 5 个英语单词', '每天推荐 5 个高频实用英语单词，包含词义、音标、例句与记忆提示。'],
  ['🌙', '每日儿童睡前故事', '生成 3-5 分钟可读的温和睡前故事，情节完整并附简短寓意。'],
  ['📋', '每周工作周报', '每周五汇总仓库 PR 与 Issue 进展，输出关键变更与待关注事项。'],
  ['🎬', '经典电影推荐', '推荐一部高分经典电影，简要介绍剧情梗概、亮点与推荐理由，全程不剧透。'],
  ['📅', '历史上的今天', '从科技、电影、音乐等领域挑选一件"今天发生过"的有趣事件，200-300 字…'],
  ['💡', '每日一个为什么', '每天抛出一个有趣问题，先提问再解答，语气轻松、通俗易懂，答案控制在 200-300…'],
  ['⏰', '父母联系提醒', '每周日 10:00 提醒你给家人打电话或发消息，简单问候近况。'],
  ['🖼️', '可爱萌宠手机壁纸', '随机从 7 种不同风格中挑选一种，为你生成一张 9:16 竖版高清萌宠手机壁纸。'],
]

export const INSTALLED: [string, string, string, string][] = [
  ['知', '#16B37A', '知识框架梳理', '课程知识框架梳理工具 — 把课程主题或教材资料提炼成结构化知识脉络图，支持三档深度输出与多格式导出。'],
  ['M', '#EA4335', 'Google全家桶', 'Google Workspace CLI for Gmail, Calendar, Drive, Contacts, Sheets, and Docs.'],
  ['gh', '#17181C', 'github', 'Interact with GitHub using the `gh` CLI. Use `gh issue`, `gh pr`, `gh run`, and `gh api` for issues, PRs, CI runs…'],
  ['◆', '#7C5CFC', 'obsidian', 'Work with Obsidian vaults (plain Markdown notes) and automate via obsidian-cli.'],
]

// ---- new-project flow data (migrated from the prototype) ------------------

// [name, instruction, default connectors, default experts]
export const NP_TPLS: [string, string, string[], string[]][] = [
  ['产品需求全流程', `# 角色
你是一个产品需求全流程协同助手，服务于产品团队从需求规划到测试上线的完整周期。

## 阶段一：需求规划
- 帮助梳理目标用户、用户痛点、使用场景和业务目标
- 输出结构化需求清单与优先级建议（附判断依据）

## 阶段二：PRD 撰写
- 按团队模板生成 PRD 草稿，包含功能描述、交互说明与验收标准

## 阶段三：研发协同
- 跟进需求流转与缺陷状态，重要变更同步给相关方并留档

## 阶段四：测试验收
- 生成测试用例，汇总验收结论，输出上线检查清单`, [], ['反馈综合分析师', '用户体验研究员', '快速原型工程师']],
  ['市场调研与竞品分析', `# 角色
你是一个市场调研与竞品分析协同助手。

## 工作方式
- 先给调研提纲，确认范围后再动手
- 输出结构化报告，每个结论标注数据来源
- 竞品拆解覆盖定位、功能、定价与增长策略
- 最后组织报告评审要点与开放问题`, [], ['行业场景研究员']],
  ['团队知识库', `# 角色
你是团队知识库的守护者。

## 工作方式
- 持续把项目中的 SOP、经验和 FAQ 沉淀为结构化文档
- 新增内容需打标签并给出目录位置建议
- 定期提示待归档的零散结论`, [], []],
  ['项目交付', `# 角色
你是项目交付协同助手，管理客户需求、计划、风险与周报。

## 工作方式
- 每周五自动汇总进展并生成周报草稿
- 风险项需给出应对建议与责任人占位
- 客户往来关键结论同步到项目空间`, ['企业微信'], []],
  ['Bug 跟踪/测试验收', `# 角色
你是 Bug 跟踪与测试验收协同助手。

## 工作方式
- 持续跟踪 Bug 状态，统一测试用例格式与验收结论模板
- 高优缺陷即时提醒并附复现路径
- 版本验收前输出遗留缺陷清单`, ['CNB'], []],
  ['自定义', '', [], []],
]

// [icon, name, desc]
export const NP_CONNS: [string, string, string][] = [
  ['📝', '本地便签', '内置 MCP 连接器（stdio）：add_note / list_notes，本地便签本读写。'],
  ['⏰', '时间助手', '内置 MCP 连接器：now / today / days_until，给智能体一个真实的时钟与日期计算。'],
  ['🔍', '工作区检索', '内置 MCP 连接器：search_files / list_workspace，对当前工作区做全文检索。'],
  ['🐙', 'GitHub', '真实第三方 MCP 连接器：管理仓库、Issue、PR、文件。需在 backend/.env 配置 GITHUB_TOKEN 且本机有 Node/npx。'],
  ['✈️', 'Telegram', '内置 MCP 连接器：get_me / send_message / get_updates，通过 Bot API 收发 Telegram 消息。需在 backend/.env 配置 TELEGRAM_BOT_TOKEN（@BotFather 获取）。'],
  ['☁️', '微云', '查看、下载、删除微云文件，上传文件到微云、生成分享链接。'],
  ['🟠', 'CNB', 'CNB 代码托管平台，支持仓库、Issue、PR、流水线管理'],
  ['🅝', 'Notion', 'Notion 知识库与项目管理 MCP 连接器，读取、搜索和管理页面与数据库'],
  ['🟩', 'Supabase', 'Supabase MCP，支持数据库与项目管理相关能力。'],
  ['💬', '企业微信', '消息、文档、日程、会议、待办等 MCP 能力，同步项目动态。'],
]

// Connectors that are actually wired to a real MCP server on the backend
// (CONNECTORS in backend/agent/mcp_client.py). The rest of NP_CONNS is an
// aspirational catalog — selecting them is a no-op until a server is registered.
// READY = works now; NEEDS_TOKEN = ready but needs a credential in backend/.env.
export const READY_CONNECTORS = new Set(['本地便签', '时间助手', '工作区检索', 'GitHub', 'Telegram'])
export const NEEDS_TOKEN_CONNECTORS = new Set(['GitHub', 'Telegram'])

// [icon, name, subtitle, desc, tags]
export const NP_EXPERTS: [string, string, string, string, string[]][] = [
  ['🎓', '留学研学专家', '福帮手', '面向家庭生成留学研学首轮规划，兼顾高考窗口、预算风险、路径备选与后续承接行动建议。', ['留学规划', '研学规划', '高考窗口']],
  ['🚀', '创业伙伴', '林正刚', '基于林正刚体系，帮创业者守住客户→GTM→模型→人→执行顺序，识别卡点、追问到行动。', ['创业判断', 'GTM落地', '客户心法']],
  ['🔎', '行业场景研究员', '福帮手', '围绕一个行业场景定位关键工作流缺口，并交付补位卡、3 天行动计划、项目动作执行包。', ['行业调研', '流程补位', '行动包']],
  ['📝', '长文档写作与改稿专家', '福帮手', '擅长把提纲、访谈、旧稿和零散素材整理成长文档手稿，完成结构规划、章节扩写和交付前质检。', ['提纲成稿', '章节扩写', '成稿收口']],
  ['🧑‍💼', '反馈综合分析师', '腾讯', '汇总用户反馈与数据，提炼共性问题与优先级建议。', ['反馈分析', '优先级', '洞察']],
  ['🕵️', '用户体验研究员', '腾讯', '设计并执行用户研究，输出可执行的体验改进建议。', ['用研', '可用性', '体验']],
  ['⚡', '快速原型工程师', '腾讯', '把需求快速转成可交互原型，验证核心流程。', ['原型', '交互', '验证']],
  ['📊', '数据建表专家', '金山文档', '将接龙转结构化表格，支持收集表、美化、校验和去重。', ['接龙转表格', '信息收集表', '智能表格']],
]

export const INSP_CATS = ['全部', '精选', '办公协同', '投资理财', '内容创作', '数据分析', '效率工具', '开发工具', '知识与学习', '信息与资讯', '商业运营', '旅行出行', '智能体能力']

export const INSP: [string, string, string][] = [
  ['#FFF7ED', '今日 AI 日报一键生成', '一句话生成可交互 HTML AI 晨报，把当日 AI 精选整理成五版块新闻仪表盘'],
  ['#15181D', '团队 OKR 雷达图', '多维度目标达成可视化，一图看清团队健康度'],
  ['#2E4954', '大理古城民宿推荐', '去哪儿+携程搜大理古城3人民宿，带院子和苍山景观的精选房源'],
  ['#FAFAFB', '实时协作白板原型', '便签拖拽 × 画笔绘制 × 连线标注，类 Miro 协作白板一键生成'],
  ['#101726', '指标看板智能页面', '把 MVP 核心指标做成可解释、可推演的在线数据看板'],
  ['#0F1420', '按需选择，随团队一起成长', '从 1 个人到 500 人团队的功能与定价对比页，一键生成'],
]

// SkillHub 浏览目录只来自本地 App 的真实 rankings；离线不可达时展示诚实空态（WB-215）。

// 知识库模板（GLM RAG · WB-144/145）：策展的「一键建库」模板。Console 目录管理下发覆盖本地，
// 离线/未接 Server 时用下面这几个真实可用的内置模板兜底（非假数据——用户可直接按模板建库）。
export interface KbTemplate {
  key: string
  name: string
  desc: string
  icon: string
  embedding_id: number
  contextual: number
  knowledge_type: number
  sentence_size?: number
  doc_types?: string[]
  tags?: string[]
}
export const KB_TPLS: KbTemplate[] = [
  { key: 'product-manual', name: '产品手册库', desc: '产品说明书、操作手册、FAQ——客服/售前问答用', icon: '📗', embedding_id: 11, contextual: 1, knowledge_type: 5, sentence_size: 300, doc_types: ['pdf', 'docx', 'md'], tags: ['产品', '手册'] },
  { key: 'legal-contract', name: '法律合同库', desc: '合同、条款、法规原文——条款检索与合规问答', icon: '⚖️', embedding_id: 12, contextual: 1, knowledge_type: 5, sentence_size: 500, doc_types: ['pdf', 'docx'], tags: ['法律', '合同'] },
  { key: 'tech-docs', name: '技术文档库', desc: 'API 文档、架构说明、研发规范——开发答疑', icon: '🛠️', embedding_id: 11, contextual: 0, knowledge_type: 5, sentence_size: 300, doc_types: ['md', 'pdf', 'txt'], tags: ['研发', '文档'] },
  { key: 'company-kb', name: '公司知识库', desc: '规章制度、流程、培训资料——员工自助问答', icon: '🏢', embedding_id: 11, contextual: 1, knowledge_type: 5, sentence_size: 300, doc_types: ['pdf', 'docx', 'md', 'xlsx'], tags: ['制度', '流程'] },
]
