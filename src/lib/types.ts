// Shared types. The SSE event union mirrors backend/agent/events.py — one event
// type ⇄ one render shape. When the OpenAPI generator runs (pnpm gen:api) the
// REST DTOs land in api-types.ts; these hand-written types cover the SSE stream
// (which is not part of the OpenAPI schema).

export type ViewId =
  | 'home'
  | 'chat'
  | 'assistant'
  | 'projects'
  | 'project'
  | 'experts'
  | 'automation'
  | 'projexec'
  | 'inspire'
  | 'myfiles'
  | 'kdocs'

// 金山文档面板一条文件（WB-140）— 后端 /connectors/kdocs/files 归一化后的形状。
export interface KdocsFile {
  name: string
  file_id: string
  drive_id: string
  link_url: string
  ext: string
  mtime: number
  size: number
  owner: string
}

// ---- SSE events -----------------------------------------------------------

export interface StatusEvent { state: 'running' | 'done'; secs?: number }
export interface ThinkEvent { text: string }
export interface StepEvent { tool: string; label: string }
export interface FileReadEvent { path: string; range: string }
export interface DiffEvent { op: string; file: string; add: number; del: number }
export interface TodoEvent { text: string }
export interface TextEvent { md: string }
export interface AskUserEvent { questions: AskQuestion[] }
export interface QaSummaryEvent { qa: QaPair[] }
export interface ArtifactEvent { name: string; size: string; path: string }
export interface WorkItemEvent { item: { id: string; project_id: string; status: WorkStatus; title: string } }
export interface UsageEvent { pct: number; used: number; detail: Record<string, number> }
export interface ErrorEvent { message: string }
export interface SessionEvent { id: string; title: string }
export interface DoneEvent { message_id?: string }

export interface AskQuestion { q: string; options: string[] }
export interface QaPair { q: string; a: string }

export type SSEEvent =
  | { type: 'session'; data: SessionEvent }
  | { type: 'status'; data: StatusEvent }
  | { type: 'think'; data: ThinkEvent }
  | { type: 'step'; data: StepEvent }
  | { type: 'file_read'; data: FileReadEvent }
  | { type: 'diff'; data: DiffEvent }
  | { type: 'todo'; data: TodoEvent }
  | { type: 'text'; data: TextEvent }
  | { type: 'ask_user'; data: AskUserEvent }
  | { type: 'qa_summary'; data: QaSummaryEvent }
  | { type: 'artifact'; data: ArtifactEvent }
  | { type: 'work_item'; data: WorkItemEvent }
  | { type: 'usage'; data: UsageEvent }
  | { type: 'error'; data: ErrorEvent }
  | { type: 'done'; data: DoneEvent }

// ---- trace items (accumulated into a message) -----------------------------

export type TraceItem =
  | { kind: 'think'; text: string }
  | { kind: 'step'; tool: string; label: string }
  | { kind: 'file_read'; path: string; range: string }
  | { kind: 'diff'; op: string; file: string; add: number; del: number }
  | { kind: 'todo'; text: string }
  | { kind: 'qa'; qa: QaPair[] }

// ---- domain ---------------------------------------------------------------

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  trace: TraceItem[]
  status?: 'running' | 'done'
  secs?: number
  usage?: { prompt: number; completion: number } | null
  error?: string
}

export interface SessionInfo {
  id: string
  title: string
  kind: string
  status: string
  space?: string | null
  project_id?: string | null
  ago?: string
  created_at?: number
  updated_at?: number
  owner_id?: string
  owner_name?: string // who ran it (M7 C3 activity feed)
  read_only?: boolean // true when the caller is a viewer, not the session's owner (M7 C3)
  // Per-run outcome for automation runs (WB-043); null for ordinary sessions.
  run_status?: 'running' | 'ok' | 'error' | null
  run_summary?: string | null
  run_kind?: 'test' | 'scheduled' | null
  workspace?: string | null
}

// Flat picker entry (WB-128). `key` is the selection value stored/sent to the backend:
//   '' = 默认(.env backstop) · '@{provider}:{model}' = built-in provider · custom name.
// 模型能力/成本元数据（WB-132，为 Auto 铺路）。source: 'default'=启发式默认 · 'custom'=用户已存。
export interface ModelMeta {
  capabilities: string[] // text/image/audio/video/tools/reasoning 子集
  input_cost: number | null // 每百万 token 输入价（缓存未命中）
  input_cost_cached: number | null // 缓存命中输入价（WB-134）
  output_cost: number | null
  context_window: number | null
  currency: string | null // ¥/$ 等（WB-134）
  note: string | null
  source?: 'default' | 'preset' | 'custom' // default=名字启发式 · preset=官方文档默认 · custom=用户覆盖
}

export interface ModelOption {
  key: string
  name: string
  icon: string
  color: string
  group: 'default' | 'provider' | 'custom'
  provider?: string
  providerName?: string
  meta?: ModelMeta
  // custom-only (WB-124): api_key never crosses to the frontend — only has_key.
  id?: string
  model_id?: string
  api_base?: string
  has_key?: boolean
}

// Built-in provider channel (WB-128). Key lives backend-only; `has_key` reflects存否.
export interface ProviderModel { model_id: string; preset: boolean; hidden: boolean; meta?: ModelMeta }
export interface Provider {
  id: string
  name: string
  icon: string
  color: string
  base_url: string        // 有效值（含用户覆盖，WB-129）
  chat_path: string
  default_base_url: string // 预置默认（判断是否已覆盖 / 恢复默认）
  default_chat_path: string
  key_hint: string
  site: string
  has_key: boolean
  models: ProviderModel[]
}

export interface ModelsResponse {
  // 用户选定的默认模型 ref（WB-136，按 owner 存后端 DB，取代 .env）。'' = 未设置。
  default_model: string
  providers: Provider[]
  custom: ModelOption[]
  models: ModelOption[]
}

export interface CustomModelInput {
  name: string
  model_id: string
  api_base?: string
  api_key?: string
  icon?: string
  color?: string
  mult?: string
}

export interface Me {
  id: string
  name: string
  role: string
  plan: string
  llm_configured: boolean
  model: string
}

export interface ProjectInfo {
  id: string
  name: string
  instruction: string
  connectors: string[]
  experts: string[]
  skills: string[]
  ago?: string
  role?: string // the current user's role in this project (M7 C2): Owner|Admin|Member|Viewer
}

// 自定义专家（我的专家 · WB-049）。persona 在后端注入系统提示，让自造专家真生效。
export interface CustomExpert {
  id: string
  name: string
  subtitle: string
  avatar: string
  intro: string
  persona: string
  tags: string[]
  created_at: number
  updated_at: number
}

export interface ProjectMember {
  user_id: string
  name: string
  role: string // Owner|Admin|Member|Viewer
  is_owner: boolean
}

// In-app message center (M7 C4). `read` is 0/1 straight from SQLite.
export interface AppNotification {
  id: string
  kind: string // member_added | role_changed | member_removed
  title: string
  body: string
  project_id: string | null
  actor_name: string | null
  read: number
  created_at: number
}

export type WorkStatus = 'todo' | 'doing' | 'paused' | 'done'
// 专业 PM 优先级（WB-108，与 Hub 对齐）。'' = 未设。
export type WorkPriority = '' | 'low' | 'medium' | 'high' | 'urgent'

export interface WorkAttachment {
  name: string
  kind: 'local' | 'asset'
  path: string | null
}

export interface WorkItem {
  id: string
  project_id: string
  title: string
  status: WorkStatus
  source: string
  assignee: string
  assignee_name: string
  description: string
  due_date: string | null
  attachments: WorkAttachment[]
  // 专业 PM 字段（WB-108）：随 hub-origin 项目与门户双向同步。
  priority: WorkPriority
  start_date: string | null
  labels: string[]
  parent_id: string
  milestone_id: string
  estimate_h: number   // 工时预估/投入（WB-117）
  spent_h: number
  ago?: string
  created_at?: number
  updated_at?: number
}

// 项目里程碑 / 迭代（WB-108）。
export interface Milestone {
  id: string
  project_id: string
  name: string
  description: string
  due_date: string | null
  status: 'open' | 'closed'
  sort: number
}

export type TriggerKind = 'interval' | 'daily'

export interface Automation {
  id: string
  name: string
  prompt: string
  trigger_kind: TriggerKind
  interval_min: number
  at_time: string // "HH:MM"
  project_id: string | null
  model: string | null
  enabled: boolean
  created_at: number
  updated_at: number
  next_run_at: number
  last_run_at: number | null
  last_session_id: string | null
  last_status: 'ok' | 'error' | 'running' | null
  next_run_label: string
  last_run_label: string
}

export interface CreateAutomationInput {
  name: string
  prompt: string
  trigger_kind: TriggerKind
  interval_min?: number
  at_time?: string
  project_id?: string | null
  model?: string | null
  enabled?: boolean
}

// SkillHub 商店卡（WB-070）：搜索/浏览的目录条目。
// - Hub 查询代理/镜像 → 富字段（下载/星/图标/分类齐全）；
// - 本地 CLI 搜索兜底 → 仅 slug/name/description/version（其余可选、缺省）。
export interface SkillCard {
  slug: string
  name: string
  description: string
  version?: string
  category?: string
  downloads?: number
  installs?: number
  stars?: number
  iconUrl?: string
  tags?: string[]
  verified?: boolean
  skillhub_category?: string
  skillhub_category_name?: string
}

// SkillHub 已安装技能（WB-055）——磁盘扫描结果。key = 技能目录名。
export interface InstalledSkill {
  key: string
  slug: string
  name: string
  description: string
  version: string
  source: string
  disabled: boolean
}

export interface SkillDetail extends InstalledSkill {
  markdown: string                       // 完整 SKILL.md（含 front-matter）
  body: string                           // 去掉 front-matter 的正文
  frontmatter: Record<string, unknown>
  references: string[]
  dir: string
  installed?: boolean                    // true=本地已安装；false=安装前预览（WB-057）
}
