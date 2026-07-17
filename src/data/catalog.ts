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
  source: string          // 出品方，如 CodeBuddy Teams / Expert Marketplace / WorkBuddy Team
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
// 各一处引用），是原型迁移遗留的死代码。原型 workbuddy-v2.html:1361 用过，React 版从未渲染。

export const SK_CATS = ['全部', 'OPC·一人公司', '生活服务', '开发工具', '网站部署', '教育学习', '投资理财', '内容创作', '信息资讯', '效率工具', '办公协同', '商业运营', '数据分析', '知识与学习']

// 「推荐」段的技能浏览卡（我们自己的目录，Manager 可 CRUD 运营；上游商店那半是 SkillHub 段的镜像）。
// WB-184：删掉 7 张**上游根本不存在**的虚构卡（NeoData金融搜索服务 / A股全栈数据 / QQ音乐助手 /
// IMAP-SMTP邮件 / fbs-bookwriter / QQ邮箱 / 创业可以学）—— 逐个搜上游确认过：搜任何一个都只回
// self-improving-agent / find-skills / summarize 这几个通用结果，即无对应技能；点它们的安装
// 必然「SkillHub 未找到「X」」。留着就是给不存在的商品挂橱窗卡（铁律#1）。
// 剩下 9 张都是真的：6 张内置技能（定义在 catalog_skills，WB-183）+ 3 张名字能精确解析到真 slug
// （腾讯自选股-金融数据查询→westock-data / skill-creator / 腾讯新闻→tencent-news）。
export const SK_GRID: [string, string, string][] = [
  ['📈', '腾讯自选股-金融数据查询', '由腾讯自选股团队提供，查询 A股、港股、美股个股/指数/ETF 的详细数据。'],
  ['📝', 'MarkItDown', '文档转 Markdown（PDF/Word/PPT/图片 OCR/音频转写/网页）'],
  ['📊', 'Excel 文件处理', 'Excel 文件创建与分析'],
  ['🧩', '技能创建指南', '创建和维护自定义技能的指南'],
  ['🔧', 'skill-creator', 'Skill 创建/编辑助手：把你的需求转成规范的 SKILL.md 与配套脚本，支持新建与改写已有技能。'],
  ['🌐', 'Web Access（浏览器自动化）', '联网取材：按 URL 抓取网页正文再作答，并注明来源链接。'],
  ['📃', 'Word 文档生成', 'Word 文档生成与编辑'],
  ['📮', '腾讯新闻', '7x24 新闻搜索工具，聚焦国内外热点，支持热榜、早晚报、实时资讯查询。'],
  ['📈', '股票综合分析器', '基于东方财富的全球股票三维分析（基本面、新闻面、资金面）'],
]

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

// ---- SkillHub 技能商店（静态产品目录，同 SK_GRID/CONNS）------------------
// 「技能」页的 SkillHub 视图数据。安装/卸载/关闭的用户状态在客户端持久化（skillStore，
// localStorage），不与后端耦合；这里只是可浏览的目录内容。

// 精选技能（顶部大卡池；一次展示 4 个，「换一换」轮换）：[emoji, color, name, desc, badge?]
export const SKILLHUB_FEATURED: [string, string, string, string, string?][] = [
  ['☁️', '#2E7DF6', '腾讯微云', '管理腾讯微云网盘文件（列表、上传、下载、删除、分享）。'],
  ['✅', '#16B37A', '腾讯问卷', '腾讯问卷操作（创建、修改、逻辑设置、统计）。'],
  ['🐧', '#0EA5E9', '鹅厂辟谣助手', '面向腾讯相关传闻的辟谣辅助 Skill，结合内部参考与实时联网核查，给出结论、事实依据和防诈提醒，并生成可分享卡片。'],
  ['🗺️', '#4C6FFF', '腾讯地图·地图助手', '腾讯位置服务出品的地图助手 Skill。一句自然语言即可调用腾讯地图全套能力：AI 旅游攻略生成、POI 搜索（含评分/人均/营业时间）、路线规划与周边推荐。', '旅游规划'],
  ['📊', '#EF4444', 'ppt-generator-skill', '智能 PPT 生成助手，根据主题、行业、风格自动生成漂亮的 PPT 文件，覆盖商务、教育、科技、医疗、金融等行业。'],
  ['📈', '#1E6FFF', '腾讯自选股·金融数据', '实时查询股票（A股/港股/美股）、ETF、指数、板块、期货、外汇、可转债的 K 线与技术指标。', '金融数据'],
  ['📝', '#F59E0B', '文章去AI味工具', '去除文本中的 AI 写作痕迹，让文字读起来更像人类写作，支持润色、改写、降 AI 味。'],
  ['🐟', '#EF4444', '番茄小说写作助手', '专为番茄小说平台优化的分章节创作助手，支持悬疑/言情/奇幻/科幻/历史等题材，每章 2200-2800 字。', '长篇创作'],
]

export const SKILLHUB_CATS = ['全部', '办公效率', '内容创作', '开发编程', '数据分析', '设计多媒体', 'AI Agent', '知识管理', '商业运营', '教育学习', '行业专业', 'IT运维与安全', '生活服务']

// SkillHub 商店技能卡：[label(字母/字), color, name, desc, downloads, stars, category(∈SKILLHUB_CATS)]
export const SKILLHUB_GRID: [string, string, string, string, string, number, string][] = [
  ['W', '#4C6FFF', 'web-tools-guide', 'MANDATORY before calling web_search, web_fetch, browser, or opencli. Contains required error-handling procedures for web_search / web_fetch / browser.', '174k', 109, '开发编程'],
  ['I', '#6B7280', 'ima-skills', 'ima skills，支持写笔记、知识库的读取、写入和检索等操作，帮你随时记录、收入 ima 智能管理、随时调用。', '94k', 347, '知识管理'],
  ['K', '#16B37A', 'kdocs skill', '操作金山文档（WPS 云文档 / Kdocs / 365.kdocs.cn）云文档的官方 Skill，覆盖云端新建、读取、编辑、搜索、分享。', '37k', 66, '办公效率'],
  ['文', '#F59E0B', '文章去AI味工具', '去除文本中的 AI 写作痕迹，让文字读起来更像人类写作。当用户要求去AI味、降AI味、让回复更像人话、润色、改写得更自然时使用。', '27k', 180, '内容创作'],
  ['P', '#EF4444', 'ppt-generator-skill', '智能 PPT 生成助手。根据用户描述的主题、行业、风格，自动生成漂亮的 PPT 文件，支持商务、教育、科技、医疗、金融等所有行业。', '23k', 91, '设计多媒体'],
  ['A', '#7C5CFC', 'Agently Mail', 'Agently Mail 是 QQ 邮箱团队为 Agent 打造的专属邮箱服务，与个人邮箱隔离，原生适配 Agent，安全高效地收发邮件。', '21k', 28, '办公效率'],
  ['P', '#17181C', 'pptx', '专业 PPTX 文件读写与生成技能，支持从大纲一键生成演示文稿、批量替换文本、导出与二次编辑。', '21k', 13, '设计多媒体'],
  ['股', '#17181C', '股票价值投资分析系统', 'A股和港股价值投资分析系统。基于价值投资经典方法论，提供护城河分析、财务健康检查、DCF 估值、管理层评估等完整框架。', '18k', 98, '数据分析'],
  ['A', '#14B8A6', 'AnySearch', 'Real-time search engine including web search, vertical domain search, parallel batch search, and URL content extraction.', '18k', 41, 'AI Agent'],
  ['抖', '#17181C', '抖音文案一键提取', '粘贴抖音、快手、小红书、视频号公开可访问的短视频分享链接，一键提取标题、简介、口播文案，提供原版、优化朗读版、精简版。', '14k', 87, '内容创作'],
  ['C', '#2E7DF6', 'cloudbase', '在开发、设计、构建、部署、调试、迁移或排查 CloudBase（腾讯云开发、云托管、TCB、微信云开发）项目时使用本技能。', '14k', 10, '开发编程'],
  ['P', '#7C5CFC', 'PDF和图片文字提取', '从图片或 PDF 文档中识别并提取文字内容，支持多种图片格式和 PDF 文件，自动判断是否需要 OCR。', '13k', 44, '办公效率'],
  ['腾', '#1E6FFF', '腾讯自选股-金融数据查询', '金融市场结构化数据查询的权威入口，实时查询股票（A股/港股/美股）、ETF、指数、板块、期货、外汇、可转债的 K 线与技术指标。', '12k', 74, '数据分析'],
  ['番', '#EF4444', '番茄小说写作助手（单章2200-2800字）', '专为番茄小说平台优化的分章节创作助手，支持悬疑/言情/奇幻/科幻/历史等题材，支持长篇创作，每章 2200-2800 字。', '11k', 130, '内容创作'],
  ['海', '#F97316', '海报设计skill', '当用户提到海报、视觉设计、品牌视觉、排版系统、极简风格、设计美学、美学方案，或想制作商业海报时，必须触发本技能。', '10k', 55, '设计多媒体'],
  ['产', '#17181C', '产品经理综合技能（PM Master）', '需求分析、PRD 编写、产品需求文档、竞品分析、BRD、MRD、用户故事、原型设计、痛点分析、功能设计一站式覆盖。', '9k', 63, '商业运营'],
  ['T', '#1E6FFF', 'Tencent Cloud Lighthouse', '触发条件：用户提及 Lighthouse、轻量应用服务器或轻量服务器时，或请求检查/创建/管理/部署 Lighthouse 实例、部署应用到轻量服务器时。', '18k', 11, 'IT运维与安全'],
  ['T', '#2E7DF6', 'Tencent Cloud Infra', '腾讯云全产品统一管理 Skill，基于 tccli 覆盖 Lighthouse/CVM/CBS/COS/VPC/DNSPod/SSL/CAM/Monitor/TAT 等。', '3.7k', 5, 'IT运维与安全'],
  ['电', '#0EA5E9', '电脑智能清理助手', '电脑垃圾文件管理工具，核心功能是帮你解决文件重复、磁盘臃肿、整理低效的问题：智能识别重复文件，通过文件内容哈希核对判断。', '2.9k', 6, 'IT运维与安全'],
  ['T', '#7C5CFC', 'TencentCloud Image AIGC Detection', '腾讯云 AI 生成图片识别技能，可用于 AI 生成图片检测、图片真伪鉴别、AI 绘画检测，辅助内容合规审核。', '2.2k', 1, 'IT运维与安全'],
  ['S', '#16B37A', 'SkillScan', 'SkillScan 是 skill 的安全防护措施，可以自动检测已安装和新添加 skill 中的安全风险，并在高危/严重风险对你的环境造成损害之前提示。', '2.0k', 1, 'IT运维与安全'],
  ['垃', '#16B37A', '垃圾清理大师', '电脑优化，储存空间清理，系统临时文件、清理各系统临时目录、释放基础空间，回收站/废纸篓，清空无用文件，不影响个人重要文件。', '1.6k', 1, 'IT运维与安全'],
  ['敏', '#EF4444', '敏感信息检测与可逆脱敏工具', '名称：敏感信息检测与可逆脱敏工具。分类：安全/隐私保护。描述：文本敏感信息可逆脱敏，图片精准识别并拒绝处理，强制生成脱敏副本。', '1.5k', 5, 'IT运维与安全'],
  ['S', '#4C6FFF', 'Skill Vetter', 'Security-first skill vetting for AI agents. Use before installing any skill from ClawdHub, GitHub, or other sources. Checks for red flags.', '1.5k', 4, 'IT运维与安全'],
  ['C', '#2E7DF6', 'CloudQ', '在腾讯云、AWS、阿里云等多云环境下，提供智能架构图、目录、详情、评估结果，支持绘制架构图和开通智能顾问，含成本分析。', '1.3k', 2, 'IT运维与安全'],
  ['网', '#16B37A', '网络工程师', '专业的网络工程师技能，覆盖路由交换、计算/数据中心、光传输五大方向，用于解答网络设计、排障与优化问题。', '1.0k', 4, 'IT运维与安全'],
  ['T', '#17181C', 'TencentOS Server全栈运维诊断专家', 'TencentOS Server 全栈运维诊断，根据用户的自然语言描述，自动识别需要的能力接口，查询能力实现，使用具体能力解决客户问题。', '963', 5, 'IT运维与安全'],
  ['T', '#1E6FFF', 'Tencent Cloud TIONE', '腾讯云 TI-ONE 训练平台综合工具集，支持训练任务、在线服务、开发机、资源组、模型仓库、数据集、日志、事件等模块的查询与管理。', '736', 0, 'IT运维与安全'],
  ['T', '#2E7DF6', 'Tencent EdgeOne', '全面的腾讯云 EdgeOne（边缘安全与加速平台）技能，涵盖边缘加速、DNS、证书、缓存、规则引擎、四层代理等能力。', '736', 2, 'IT运维与安全'],
  ['W', '#16B37A', 'WorkBuddy使用指南', 'WorkBuddy 全功能使用指南与故障排查手册。当用户询问 WorkBuddy 的任何使用问题、配置方法、故障排查时触发。', '678', 3, 'IT运维与安全'],
  ['S', '#6B7280', 'shannon渗透测试', '基于 shannon 改进的人工智能驱动白盒渗透测试方法，遵循五阶段流程（前期侦察、侦察、漏洞分析、漏洞利用、报告生成），并形成闭环。', '673', 3, 'IT运维与安全'],
  ['E', '#0EA5E9', 'Edgeone Pages Deploy', '一键部署静态站点/前端项目到腾讯云 EdgeOne Pages，自动构建、生成访问域名与边缘加速。', '648', 1, 'IT运维与安全'],
  ['T', '#1E6FFF', 'tencentcloud-faceid-detectlivefaceaccurate', '腾讯云人脸核身活体检测高精度版（DetectLiveFaceAccurate）接口调用技能。当用户需要对人脸图片进行防翻拍活体检测时使用。', '653', 0, 'IT运维与安全'],
  ['磁', '#F59E0B', '磁盘垃圾清理大师', '磁盘垃圾清理助手，自动扫描磁盘找到老文件、大文件、垃圾文件，生成垃圾桶 md 让用户审核后再清理，避免误删。', '512', 1, 'IT运维与安全'],
  ['t', '#17181C', 'tsa', 'TSA - Tencent Cloud Smart Advisor，腾讯云智能顾问，巡检云上资源的成本、安全、性能与可靠性风险并给出优化建议。', '420', 2, 'IT运维与安全'],
  ['日', '#7C5CFC', '一个会自进化的日志分析工具', '日志智能分析工具，基于 mini-swe-agent 极简理念：确定性规则 + AI 推理，自动定位异常、聚类报错、给出修复建议。', '388', 1, 'IT运维与安全'],
  ['☁️', '#2E7DF6', '腾讯微云', '管理腾讯微云网盘文件（列表、上传、下载、删除、分享），生成分享链接。', '8k', 22, '生活服务'],
]

// SKILLHUB_KITS（技能套件）已删除（WB-182）：它是整次技能审查里唯一 100% 虚构的功能 ——
// 后端 grep kit|bundle|套件 零命中、DB 无表、Hub 无源、_SHOWCASE_SKIP 让它永不入库，
// 「N 个技能」的 N 是手写常量（8/6/5/4），且没有任何技能列表与之关联，「安装套件」按钮只 toast。
// 要真做的话，正确姿势是等 WB-183 的 catalog_skills（slug 主键）落地后在 Hub 建 kit 表，
// data 存 {name, icon, color, desc, slugs[]}，「N 个技能」由 slugs.length 真算，
// 安装 = 对 slugs[] 逐个走已有的 POST /api/skills/install（无需新后端端点）。

// 知识库模板（GLM RAG · WB-144/145）：策展的「一键建库」模板。Manager 目录管理下发覆盖本地，
// 离线/未接 Manager 时用下面这几个真实可用的内置模板兜底（非假数据——用户可直接按模板建库）。
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
