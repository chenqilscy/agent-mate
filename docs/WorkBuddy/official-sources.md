# 腾讯 WorkBuddy 官方资料索引

> 基础资料访问日期：2026-07-21；动态能力目录访问日期：2026-07-24（Asia/Shanghai）。
> 以下均为腾讯或腾讯云官方页面。页面内容、更新时间、支持能力和商业信息可能变化；做新决策前
> 应重新打开原链接核对。

## 核心来源

| 主题 | 官方链接 | 本次核实到的关键信息 |
|---|---|---|
| 产品总览 | [腾讯云 WorkBuddy 产品页](https://cloud.tencent.com/product/workbuddy) | 定位为全场景 AI 办公工作台；核心闭环是自然语言下达任务、自主拆解、调用工具、自检修正并交付可验收结果。支持授权目录内的本地文件读写；产品页还描述项目空间中的多 Agent 并行和流程复用。 |
| 产品简介 | [WorkBuddy Enterprise 产品简介](https://cloud.tencent.com/document/product/1831/134384) | 官方将其与传统聊天产品区分为：能实际执行任务、自动操作本地文件、处理多步骤复杂任务并交付结果。典型场景含文档、表格、PPT、研究报告、邮件与批量文件处理。 |
| 本地任务工作台 | [新建任务栏（本地 AI 工作台）](https://cloud.tencent.com/document/product/1831/134391) | 任务栏统一管理工作目录、工作模式、模型、已安装 Skill 和连接器；每个对话是独立任务，多任务可并行。Ask 只问答，Plan 先规划后执行；权限范围与工作目录是任务上下文的一部分。 |
| 任务与产物 | [入门指南](https://cloud.tencent.com/document/product/1831/134389) | 任务按工作空间组织；执行过程展示步骤，右侧结果区集中查看产物、网页预览、全部文件和代码变更，强调“过程可观察、结果可验收”。 |
| Skill | [技能](https://cloud.tencent.com/document/product/1831/134432) | Skill 被定义为封装可执行脚本与工作流的工具能力，在用户授权下完成文件、外部 API 等具体动作。第三方 Skill 需要核对来源、脚本、权限与数据共享范围。 |
| 专家与专家团 | [专家](https://cloud.tencent.com/document/product/1831/134393) | Skill 是能力；专家是人设、方法论和能力组合；专家团是多位专家加协作流程，负责自动拆解、并行执行和完整交付。官方同时提示专家团成本通常高于单专家。 |
| 连接器 | [连接器](https://cloud.tencent.com/document/product/1831/134525) | 连接器是外部服务桥梁，形态包括 MCP+CLI 与 Skill+CLI；支持 OAuth/API Key、数据查询和写操作。每个连接器独立授权，只在用户指令触发时按需读取，写入操作需明确指令。 |
| 自动化 | [自动化](https://cloud.tencent.com/document/product/1831/134399) | 本地客户端保存任务名、prompt、调度规则、工作目录和执行状态，定时以当前身份启动 Agent；可选择模型/Skill、保存结果并推送小程序。无人值守任务需要特别限制写入、删除和资金操作。 |
| 远程助理 | [助理（远程任务）](https://cloud.tencent.com/document/product/1831/134392) | 用户可通过微信、企业微信、QQ、钉钉、飞书等渠道远程触发桌面任务并接收结果；本地任务仍是优先入口，助理负责远程控制和统一记录。 |
| 灵感与复用 | [灵感](https://cloud.tencent.com/document/product/1831/134394) | “做同款”把案例转成可执行入口，预填 Prompt 并加载相关 Skill/专家；灵感承担发现和转化，不等同于底层能力定义。 |
| 企业 Agent 控制面 | [WorkBuddy Enterprise 快速开始](https://cloud.tencent.com/document/product/1831/134527) | 企业后台为 Agent 配置模型、System Prompt、Skill、专家、MCP、连接器、记忆和知识库，并汇入 Manifest；同时提供 Test Run、渠道、凭据、Runtime、Session 和评测等治理入口。 |
| 企业能力原则 | [产品优势](https://cloud.tencent.com/document/product/1831/134330) | 强调多工具闭环、多 Agent 协同、开放 MCP 生态、身份/权限/加密/审计/内容安全，以及 SaaS、专属和私有化等交付形态。 |
| 官方站与下载 | [workbuddy.cn](https://www.workbuddy.cn/) | 提供桌面端下载、移动端入口和套餐信息。价格、积分和额度高度动态，只可作为带日期的商业信息参考，不应写死到 AgentMate 设计。 |

## 动态能力目录

以下页面可作为 AgentMate Server 运营能力目录时的**候选发现与展示字段参考**。2026-07-24
通过登录态页面核实到的结构如下；页面条目、分类、排序和安装状态均为动态信息，不记录为长期常量。

| 目录 | 官方链接 | 可参考的信息 |
|---|---|---|
| 专家 | [WorkBuddy 专家目录](https://www.workbuddy.cn/app/experts) | 提供综合/最热/最新排序、业务分类，以及专家名称、发布者或署名、简介、能力标签和“召唤”入口。可参考 AgentMate 的专家分类、卡片字段和推荐表达，但卡片本身不等于可注入 persona。 |
| 技能 | [WorkBuddy 技能目录](https://www.workbuddy.cn/app/skills) | 提供已安装、添加技能、精选、推荐/套件、分类筛选，以及图标、名称和描述等字段；目录同时包含腾讯能力与第三方能力。可参考发现、分类和卡片信息架构，但不能据此断言 Skill 包、脚本、权限或兼容性已经可用。 |
| 连接器 | [WorkBuddy 连接器目录](https://www.workbuddy.cn/app/connectors) | 展示连接器名称、简介和安装状态等信息，当前页面可见 GitHub MCP、TAPD、微云、CNB、Notion、Supabase、乐享知识库和腾讯文档等方向。可参考连接对象和文案，但不能据此推导 AgentMate 的启动命令、凭据变量、工具协议或读写权限。 |

### 用作 Server 数据参考的边界

1. 这些页面是**外部参考源**，不是 AgentMate 运行时依赖或远程权威源；Server 不自动整页抓取、
   定时镜像或在客户端运行时直连它们。
2. 只记录必要的来源 URL、访问日期、候选名称、分类和短摘要；不复制整页正文、图片或第三方
   Skill 包。
3. 候选条目必须先人工筛选和去重，再映射到 AgentMate schema。专家要补齐稳定 slug 与
   persona；Skill 要形成可校验安装快照并声明工具/权限；连接器要有受支持的 launch spec、
   凭据门禁和工具协议。
4. 只有通过测试和验收的条目才能由 Console 发布为 functional；发布后 AgentMate Server 数据库
   是本产品目录的唯一权威源，原页面变化只触发重新评估，不自动覆盖已运营数据。

## 稳定产品概念

下列概念在多个官方页面中交叉出现，可作为较稳定的产品设计依据：

1. **Task-first**：一段对话对应一个独立任务，而非把所有工作塞进一条无限增长的聊天上下文。
2. **Workspace boundary**：工作目录既是产物归属，也是本地文件权限边界。
3. **Plan / Ask / Execute**：工作模式同时表达交互方式和执行权限。
4. **Capability layers**：Tool/Skill 解决“能做什么”，Expert 解决“按什么专业方法做”，Team
   解决“如何多角色协作”，Connector 解决“连接谁的数据和操作”。
5. **Observable delivery**：计划、工具步骤、文件、预览、变更和最终结果共同构成交付，而非只有一段回答。
6. **Reuse loop**：模板、灵感、专家和 Skill 市场把成功任务转成可发现、可安装、可复用的能力。
7. **Local + control plane**：本地端负责授权目录和桌面执行，企业控制面负责目录、身份、渠道、凭据、
   发布和治理；具体云端执行范围随产品版本变化，引用时需再次核对。

## 易变信息

以下信息只记录对应访问日期看到的方向，不作为长期常量：

- 模型名称、默认路由和积分消耗；
- 内置 Skill、专家、连接器和远程渠道的具体数量、条目、分类与排序；
- SkillHub 商品规模、精选/排行和兼容生态；
- 免费额度、套餐价格、自动化数量上限；
- 云端托管任务和企业版功能的可用区域、版本与 SLA。

更新这些内容时应修改对应资料的访问日期，并在提交说明中注明重新核对过的官方来源。
