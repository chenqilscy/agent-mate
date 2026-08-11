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
  | 'skills'
  | 'connectors'
  | 'automation'
  | 'projexec'
  | 'knowledge'

// 金山文档面板一条文件（WB-140）— 后端 /connectors/kdocs/files 归一化后的形状。
export interface KdocsFile {
  name: string
  file_id: string
  drive_id: string
  parent_id: string
  link_url: string
  ext: string
  is_folder: boolean
  is_kb: boolean   // 知识库节点（kwiki）——点进去走 kwiki 而非 drive
  kuid: string     // 知识库 / 知识库子文件夹的下钻标识
  mtime: number
  size: number
  owner: string
}

// ---- 知识库（自托管 WeKnora RAG · WB-173/174）-----------------------------

export interface KnowledgeBase {
  id: string
  name: string
  description?: string
  icon?: string
  document_size?: number
  word_num?: number
}

// WeKnora 连接配置（WB-188）。**没有 api_key 字段**：密钥只写不回读，
// 后端只回 has_key 布尔（同厂商 Key 的做法）。*_source: 该字段来自 UI 表单('db')
// 还是 backend/.env('env')，''=未配 —— 用于如实提示「这项是 .env 配的」。
export interface KnowledgeConfig {
  configured: boolean
  url: string
  has_key: boolean
  embedding_model_id: string
  key_source: 'db' | 'env' | ''
  url_source: 'db' | 'env' | ''
}

export interface KbDocument {
  id: string
  name: string
  word_num?: number
  // 0 处理中 · 1 成功 · 2 失败（后端由 WeKnora parse_status 映射）
  embedding_stat?: number
  failInfo?: { embedding_code?: number; embedding_msg?: string }
}

export interface KbRetrieveHit {
  id?: string
  text: string
  score: number
  metadata?: { doc_name?: string; doc_id?: string; doc_url?: string; [k: string]: unknown }
}

// ---- SSE events -----------------------------------------------------------

export interface StatusEvent { state: 'running' | 'done'; secs?: number }
export interface ThinkEvent { text: string }
export interface StepEvent { tool: string; label: string }
export interface FileReadEvent { path: string; range: string }
export interface DiffEvent { op: string; file: string; add: number; del: number }
export interface TodoEvent { text: string }
export type RunPlanStatus = 'pending' | 'in_progress' | 'completed' | 'blocked'
export interface RunPlanItem {
  id: string
  title: string
  status: RunPlanStatus
  order: number
  depends_on: string[]
  work_item_id?: string
}
export interface RunPlanEvent {
  version?: number
  items: RunPlanItem[]
  project_id?: string | null
}
export interface TextEvent { md: string }
export interface AskUserEvent { questions: AskQuestion[]; question_event_id?: string }
export interface QaSummaryEvent { qa: QaPair[] }
export interface ContextDegradedEvent { reason: string; excerpt_messages: number; retry_on_next_turn: true }
export type RunStatus =
  | 'draft' | 'planning' | 'waiting_approval' | 'paused' | 'accepted'
  | 'queued' | 'leased' | 'running' | 'waiting_user' | 'recoverable'
  | 'completed' | 'succeeded' | 'failed' | 'cancelled'
export interface ArtifactEvent {
  id?: string
  run_id?: string
  name: string
  size: string
  path: string
  sha256?: string
  mime_type?: string
  is_primary?: boolean
  display_order?: number
  acceptance_status?: 'pending' | 'accepted' | 'rejected'
}
export interface RunEvent { run: AgentRun; user_message_id?: string }
export interface WorkItemEvent {
  item: {
    id: string; project_id: string; status: WorkStatus; title: string;
    sprint_id?: string; milestone_id?: string; version?: number;
  }
}
export interface UsageEvent { pct: number; used: number; detail: Record<string, number> }
export interface ErrorEvent { message: string }
export interface SessionEvent { id: string; title: string }
export interface DoneEvent { message_id?: string }
export interface RunRecoveredEvent { lease_epoch: number }
export interface RunStateEvent { status: RunStatus }

export const SSE_EVENT_TYPES = [
  'session', 'status', 'run', 'think', 'step', 'file_read', 'diff', 'todo',
  'plan_snapshot', 'plan_patch', 'text', 'ask_user', 'qa_summary',
  'context_degraded', 'artifact', 'work_item', 'usage', 'error', 'done',
] as const

// Events synthesized while following the durable Server Run protocol. They are
// part of the store contract but never accepted from the legacy wire SSE parser.
export const CLIENT_EVENT_TYPES = ['run_recovered', 'run_state'] as const

export interface AskQuestion { q: string; options: string[] }
export interface QaPair { q: string; a: string }

export type SSEEvent =
  | { type: 'session'; data: SessionEvent }
  | { type: 'status'; data: StatusEvent }
  | { type: 'run'; data: RunEvent }
  | { type: 'run_recovered'; data: RunRecoveredEvent }
  | { type: 'run_state'; data: RunStateEvent }
  | { type: 'think'; data: ThinkEvent }
  | { type: 'step'; data: StepEvent }
  | { type: 'file_read'; data: FileReadEvent }
  | { type: 'diff'; data: DiffEvent }
  | { type: 'todo'; data: TodoEvent }
  | { type: 'plan_snapshot'; data: RunPlanEvent }
  | { type: 'plan_patch'; data: RunPlanEvent }
  | { type: 'text'; data: TextEvent }
  | { type: 'ask_user'; data: AskUserEvent }
  | { type: 'qa_summary'; data: QaSummaryEvent }
  | { type: 'context_degraded'; data: ContextDegradedEvent }
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
  | { kind: 'plan_snapshot'; version: number; items: RunPlanItem[]; project_id?: string | null }
  | { kind: 'plan_patch'; version: number; items: RunPlanItem[]; project_id?: string | null }
  | { kind: 'qa'; qa: QaPair[] }
  | { kind: 'context_degraded'; reason: string; excerpt_messages: number; retry_on_next_turn: true }
  | { kind: 'artifact'; artifact: ArtifactEvent }

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
  runId?: string
  runStatus?: RunStatus
  pendingQuestion?: { questions: AskQuestion[]; recovery: 'retry_required'; source: string }
  queueContext?: RunQueueContext
  artifacts?: ArtifactEvent[]
}

export interface RunQueueContext {
  reason: 'waiting_confirmation' | 'blocked_by_paused_run' | 'resource_lock_wait' | 'device_busy' | 'device_unavailable' | 'device_offline' | 'capability_mismatch' | 'awaiting_claim' | 'recovering'
  message: string
  blocking_run?: {
    id: string
    session_id: string
    project_id?: string
    status: RunStatus
  }
}

export interface ArtifactManifest {
  id: string
  run_id: string
  owner_id: string
  project_id?: string | null
  kind: string
  path: string
  name: string
  mime_type: string
  source_tool: string
  size: number
  sha256: string
  validation_status: string
  validation: Record<string, unknown>
  preview_path?: string | null
  is_primary: boolean
  display_order: number
  acceptance_status: 'pending' | 'accepted' | 'rejected'
  accepted_by?: string | null
  accepted_at?: number | null
  created_at: number
  updated_at: number
  verification?: { exists: boolean; hash_matches: boolean }
}

export interface AgentRun {
  id: string
  session_id: string
  owner_id: string
  project_id?: string | null
  work_item_id?: string | null
  mode: 'ask' | 'plan' | 'exec'
  status: RunStatus
  workspace: string
  idempotency_key?: string | null
  retry_of?: string | null
  model_ref?: string | null
  model_id?: string | null
  model_snapshot?: Record<string, unknown>
  request_snapshot?: Record<string, unknown>
  estimated_cost?: number | null
  cost_currency?: string | null
  plan: RunPlanItem[]
  plan_version: number
  permission_snapshot: Record<string, unknown>
  checkpoint: Record<string, unknown>
  error_code?: string | null
  error_message?: string | null
  prompt_tokens: number
  cached_prompt_tokens: number
  completion_tokens: number
  tool_calls: number
  lease_epoch?: number
  recovery_count?: number
  started_at?: number | null
  ended_at?: number | null
  created_at: number
  updated_at: number
  queue_context?: RunQueueContext
  artifacts?: ArtifactManifest[]
}

export interface LocalConnectorInstance {
  id: string
  name: string
  transport: 'stdio' | 'sse'
  command: string
  args: string[]
  url: string
  environment: Record<string, string>
  secret_keys: string[]
  has_secrets: Record<string, boolean>
  enabled: boolean
  health_status: 'unknown' | 'healthy' | 'unhealthy'
  last_error: string
  tool_count: number
  last_checked_at: number
  created_at: number
  updated_at: number
}

export interface ConnectorRuntimeStatus {
  id: string
  name: string
  source: 'builtin' | 'local'
  transport: 'builtin' | 'stdio' | 'sse'
  enabled: boolean
  configured: boolean
  healthy: boolean
  health_status: string
  last_error: string
  credential_keys: string[]
  tool_count: number
}

export interface LocalConnectorPayload {
  instances: LocalConnectorInstance[]
  statuses: ConnectorRuntimeStatus[]
}

export interface DeviceDiagnosticIssue {
  code: string
  severity: 'warning' | 'error'
  title: string
  detail: string
  action: 'retry_transport' | 'open_run' | 'runtime_settings' | 'login' | 'recheck' | 'connectors'
  run_id?: string
}

export interface DeviceDiagnostics {
  checked_at: number
  healthy: boolean
  process: {
    pid: number; platform: string; release: string; python: string
    server_configured: boolean; server_url: string; protocol_version: number
  }
  transport: {
    identity: { bound: boolean; expires_at: number; updated_at: number }
    leases: Array<{ run_id: string; device_id: string; lease_epoch: number; expires_at: number; ack_high_water: number; status: string; last_error: string; updated_at: number }>
    wal: { count: number; bytes: number; oldest_at: number; max_attempts: number; runs: Array<{ run_id: string; lease_epoch: number; count: number; bytes: number; oldest_at: number; attempts: number }> }
    working_copies: Array<{ id: string; asset_id: string; project_id: string; run_id: string; relative_path: string; source_kind: string; state: string; size: number; updated_at: number }>
    staged_inputs: number
  }
  workers: { healthy: boolean; components: Array<{ name: string; last_attempt_at: number | null; last_success_at: number | null; last_failure_at: number | null; consecutive_failures: number; last_error: string | null }> }
  server_runs: {
    max_concurrency: number
    per_owner_concurrency: number
    active: number
    resident: number
    max_resident: number
    available: number
    leader: boolean
    runs: Array<{ run_id: string; device_id: string; project_id: string; workspace: string; phase: string; slot_held: boolean }>
    resources: {
      waiting: Array<{ run_id: string; resources: string[] }>
      holding: Array<{ run_id: string; resources: string[] }>
    }
  }
  connectors: ConnectorRuntimeStatus[]
  runtime: { items: DeviceSettingItem[] }
  issues: DeviceDiagnosticIssue[]
}

export interface OpsRecentArtifact {
  id: string
  run_id: string
  session_id: string
  session_title: string
  project_id?: string | null
  name: string
  path: string
  mime_type: string
  size: number
  sha256: string
  acceptance_status: 'pending' | 'accepted' | 'rejected'
  created_at: number
}

export interface OpsSummary {
  window_days: number
  generated_at: number
  runs: {
    total: number; active: number; attention_sessions: number
    succeeded: number; failed: number; cancelled: number
    success_rate: number | null; avg_duration_sec: number
    prompt_tokens: number; completion_tokens: number; tool_calls: number
  }
  artifacts: { total: number; pending_review: number }
  recent_artifacts: OpsRecentArtifact[]
  projects: { total: number; work_items: number; doing: number; overdue: number }
  automations: { total: number; enabled: number; dead_letter: number; failed_window: number }
  assistants: {
    total: number; enabled: number; channels: number
    channels_running: number; channels_attention: number
  }
}

export interface BackgroundHealth {
  healthy: boolean
  components: {
    name: string
    last_attempt_at: number | null
    last_success_at: number | null
    last_failure_at: number | null
    consecutive_failures: number
    last_error: string | null
  }[]
  queue: {
    counts: Record<string, number>
    due: number
    oldest_due_at: number | null
  }
}

export type OrchestrationStatus = 'planning' | 'running' | 'reviewing' | 'completed' | 'failed' | 'cancelled'

export interface OrchestrationAttempt {
  id: string
  attempt: number
  session_id: string
  run_id?: string | null
  status: 'running' | 'completed' | 'failed' | 'cancelled'
  error: string
  prompt_tokens: number
  completion_tokens: number
  created_at: number
  ended_at?: number | null
}

export interface OrchestrationNode {
  id: string
  node_key: string
  title: string
  role: string
  expert_slug: string
  instruction: string
  depends_on: string[]
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped' | 'cancelled'
  session_id?: string | null
  run_id?: string | null
  output: string
  error: string
  prompt_tokens: number
  completion_tokens: number
  attempts: OrchestrationAttempt[]
}

export interface Orchestration {
  id: string
  project_id?: string | null
  team_name: string
  goal: string
  status: OrchestrationStatus
  max_nodes: number
  max_parallel: number
  max_total_tokens: number
  prompt_tokens: number
  completion_tokens: number
  artifact_id?: string | null
  error: string
  cancel_requested: boolean
  created_at: number
  updated_at: number
  ended_at?: number | null
  nodes: OrchestrationNode[]
  artifact?: ArtifactManifest | null
}

export interface WorkItemLaunch {
  id: string
  work_item_id: string
  owner_id: string
  idempotency_key: string
  session_id: string | null
  run_id: string | null
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  error_code: string | null
  error_message: string | null
  created_at: number
  updated_at: number
  finished_at: number | null
}

export interface WorkItemDelivery {
  work_item: WorkItem
  can_write: boolean
  launches: WorkItemLaunch[]
  runs: AgentRun[]
}

export interface SessionInfo {
  id: string
  title: string
  kind: string
  status: string
  space?: string | null
  project_id?: string | null
  latest_run_id?: string | null
  work_item_id?: string | null
  work_item_title?: string | null
  ago?: string
  created_at?: number
  updated_at?: number
  owner_id?: string
  owner_name?: string // who ran it (M7 C3 activity feed)
  version?: number // Server optimistic-concurrency token
  read_only?: boolean // true when the caller is a viewer, not the session's owner (M7 C3)
  // Per-run outcome for automation runs (WB-043); null for ordinary sessions.
  run_status?: 'running' | 'ok' | 'error' | null
  run_summary?: string | null
  run_kind?: 'test' | 'scheduled' | 'webhook' | null
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
  max_output_tokens: number | null
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
  credential_updated_at?: number | null
  credential_rotation_due?: boolean
  health?: { status: 'healthy' | 'unhealthy'; checked_at: number; latency_ms: number; error_code: string } | null
  models: ProviderModel[]
}

export interface ModelsResponse {
  // 用户选定的默认模型 ref（WB-136，按 owner 存后端 DB，取代 .env）。'' = 未设置。
  default_model: string
  providers: Provider[]
  custom: ModelOption[]
  models: ModelOption[]
}

export interface ModelPolicy {
  allowlist: string[]
  fallback_chain: string[]
  daily_soft_tokens: number
  daily_hard_tokens: number
  monthly_soft_tokens: number
  monthly_hard_tokens: number
  daily_soft_cost: number
  daily_hard_cost: number
  monthly_soft_cost: number
  monthly_hard_cost: number
  currency: string
  provider_health_ttl_seconds: number
  credential_max_age_days: number
}

export interface ModelGovernance {
  policy: ModelPolicy & { default_run_token_budget: number }
  organization_policy?: (ModelPolicy & { org_id: string; revision: number }) | null
  usage: {
    period_start: number
    generated_at: number
    runs: number
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
    priced_runs: number
    unpriced_runs: number
    unresolved_runs: number
    costs: { currency: string; amount: number; runs: number }[]
    models: {
      model_ref: string
      model_id: string
      currency: string | null
      runs: number
      prompt_tokens: number
      completion_tokens: number
      estimated_cost: number | null
    }[]
  }
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
  authenticated: boolean
  role: string
  plan: string
  llm_configured: boolean
  model: string
}

// 设置 · 个性化（WB-147）：回复风格 + 自定义指令。
export interface StylePreset {
  key: string
  label: string
  desc: string
}
export interface AppSettings {
  style: string
  custom_instructions: string
  style_presets: StylePreset[]
}

export interface SystemSettings {
  interface_scale: 90 | 95 | 100 | 105 | 110
  reduce_motion: boolean
  default_permission: 'default' | 'full'
  startup_page: 'home' | 'projects' | 'knowledge' | 'automation'
}

export interface DeviceSettingItem {
  key: string
  group: 'observability' | 'voice' | 'collaboration' | string
  label: string
  description: string
  value_type: 'string' | 'boolean' | 'number' | 'secret' | 'choice'
  env_name: string
  secret: boolean
  minimum?: number | null
  maximum?: number | null
  choices: string[]
  placeholder?: string
  source: 'database' | 'environment' | 'default'
  configured: boolean
  value: string | number | boolean | null
  hot_reload: boolean
}

export interface DeviceSettingAudit {
  id: string
  setting_key: string
  actor_id: string
  action: string
  before_value: string
  after_value: string
  created_at: number
}

export interface DeviceSettingsPayload {
  items: DeviceSettingItem[]
  deployment_only: string[]
  audit: DeviceSettingAudit[]
}

// 设置 · 记忆（WB-148）：长期事实，注入之后对话。source: conversation(自动) / manual(手动)。
export interface MemoryItem {
  id: string
  content: string
  source: string
  created_at: number
  importance?: number
  usage_count?: number
  status?: string
  superseded_by?: string | null
  last_used_at?: number | null
  strength?: number
  scope: 'user' | 'project'
  project_id: string | null
}
export interface EmbedStatus {
  configured: string      // 用户所选后端 'local' | 'glm'
  active: string | null   // 实际生效后端（所选不可用会回退）
  local: boolean          // 本地 fastembed 是否可用
  glm: boolean            // 在线 GLM（是否配了智谱密钥）
}
export interface MemoryStats {
  active: number
  archived: number
  superseded: number
  total: number
  avg_strength: number
  decaying: number
  semantic: boolean
  embed?: EmbedStatus
  scope?: 'user' | 'project'
  project_id?: string | null
}
export interface MemoryData {
  enabled: boolean
  items: MemoryItem[]
  stats?: MemoryStats
}
export interface MemorySearchHit extends MemoryItem {
  similarity: number | null
  score: number
}
export interface MemorySearchResult {
  semantic: boolean
  hits: MemorySearchHit[]
}
export interface MemoryTrace {
  memory: MemoryItem
  superseded_by: MemoryItem | null
  superseded: MemoryItem | null
}
export interface WorkspaceMemory {
  project_id: string
  content: string
  daily_logs: { date: string; content: string }[]
  can_edit: boolean
  local_only: boolean
}

// 设置 · 数据管理（WB-149）：数据条数概览。
export interface DataSummary {
  sessions: number
  messages: number
  memories: number
}

// 设置 · 智能体设置（WB-150）：工具步数上限 + 回复发散度，run_chat 真读真用。
export interface AgentSettings {
  max_rounds: number
  temperature: number
  defaults: { max_rounds: number; temperature: number }
  limits: { max_rounds: [number, number]; temperature: [number, number] }
}

// 设置 · 安全中心（WB-152）：命令黑名单 + 审计日志。
export interface AuditEntry {
  id: string
  tool: string
  detail: string
  action: string // 'executed' | 'blocked'
  created_at: number
}

export interface ProjectInfo {
  id: string
  name: string
  instruction: string
  connectors: string[]
  experts: string[]
  skills: string[]
  knowledge_ids: string[]
  origin?: 'local' | 'server'
  org_id?: string | null
  ago?: string
  role?: string // the current user's role in this project (M7 C2): Owner|Admin|Member|Viewer
  sync_conflicts?: number // local-first compatibility; removed with WB-437 UI retirement
}

export interface ServerTimelineEvent {
  id: string
  project_id: string
  actor_id: string
  actor_name: string
  kind: string
  title: string
  summary: string
  ext_id: string | null
  created_at: number
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

export type WorkStatus = 'todo' | 'doing' | 'paused' | 'review' | 'done'
// 专业 PM 优先级（WB-108，与 Server 对齐）。'' = 未设。
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
  // 专业 PM 字段（WB-108）：随 server-origin 项目与门户双向同步。
  priority: WorkPriority
  start_date: string | null
  labels: string[]
  parent_id: string
  milestone_id: string
  estimate_h: number   // 工时预估/投入（WB-117）
  spent_h: number
  custom_fields: Record<string, string | number | boolean>
  dependency_ids: string[]
  sprint_id: string
  critical_path?: boolean
  delivery_accepted?: boolean
  ago?: string
  created_at?: number
  updated_at?: number
  version: number
}

export type WorkActionSignal =
  | 'overdue' | 'due_today' | 'blocked' | 'in_progress'
  | 'awaiting_acceptance' | 'starts_today' | 'ready' | 'urgent'

export interface PersonalActionItem extends WorkItem {
  project: { id: string; name: string; role: string }
  action_signals: WorkActionSignal[]
  action_reason: WorkActionSignal
}

export interface PersonalActionItemsResponse {
  as_of: string
  computed_at: number
  source: 'server'
  items: PersonalActionItem[]
  unassigned: PersonalActionItem[]
  summary: {
    assigned: number
    unassigned: number
    backlog: number
    overdue: number
    due_today: number
    blocked: number
    in_progress: number
    awaiting_acceptance: number
    starts_today: number
    ready: number
    urgent: number
  }
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

export type TriggerKind = 'interval' | 'daily' | 'health_daily' | 'webhook'

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
  last_status: 'ok' | 'error' | 'running' | 'retrying' | null
  timeout_sec: number
  max_attempts: number
  retry_backoff_sec: number
  max_total_tokens: number
  notify_policy: string
  concurrency_policy: 'skip'
  preauthorized_permissions: string[]
  next_run_label: string
  last_run_label: string
  version?: number // Server optimistic-concurrency token
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
  timeout_sec?: number
  max_attempts?: number
  retry_backoff_sec?: number
  max_total_tokens?: number
  notify_policy?: string
  concurrency_policy?: 'skip'
  preauthorized_permissions?: string[]
}

export interface SharedPmTemplate {
  id: string
  name: string
  values: Record<string, unknown>
}

export interface SharedPmView {
  id: string
  name: string
  filters: {
    group?: 'none' | 'assignee' | 'milestone'
    assignee?: string
    source?: string
    search?: string
  }
}

export interface SharedPmPreferences {
  templates: SharedPmTemplate[]
  views: SharedPmView[]
  wip: Record<string, number>
  shared_updated_at: number
  views_updated_at: number
}

export type SharedPmPreferencesPatch = Partial<Pick<SharedPmPreferences, 'templates' | 'views' | 'wip'>> & {
  expected_shared_updated_at?: number
  expected_views_updated_at?: number
}

export interface ServerProjectField {
  id: string
  name: string
  field_type: string
  options: string[]
  required: boolean
}

export interface ServerProjectSprint {
  id: string
  name: string
  goal: string
  start_date: string
  end_date: string
  status: string
  milestone_id?: string
}

export type IdeaStatus = 'inbox' | 'active' | 'settled' | 'archived'
export type IdeaRelationType = 'related' | 'derived' | 'duplicate'
export type IdeaSettlementType = 'work_item' | 'decision' | 'memory'

export interface Idea {
  id: string
  owner_id: string
  project_id: string | null
  title: string
  content: string
  processed_content: string
  status: IdeaStatus
  tags: string[]
  source_type: string
  source_session_id: string | null
  source_message_id: string | null
  processing_session_id: string | null
  settled_type: IdeaSettlementType | ''
  settled_id: string
  created_at: number
  updated_at: number
  can_write: boolean
}

export interface IdeaRelation {
  source_idea_id: string
  target_idea_id: string
  relation: IdeaRelationType
  direction: 'outbound' | 'inbound'
  created_at: number
  related: Idea
}

export interface IdeaDetail extends Idea {
  relations: IdeaRelation[]
}

export interface AutomationFire {
  id: string
  automation_id: string
  owner_id: string
  fire_key: string
  trigger_kind: 'scheduled' | 'health_daily' | 'manual' | 'replay' | 'webhook'
  planned_at: number
  status: 'queued' | 'running' | 'retry_wait' | 'succeeded' | 'dead_letter' | 'ignored'
  attempt: number
  max_attempts: number
  session_id: string | null
  run_id: string | null
  retry_of_run_id: string | null
  error_code: string | null
  error_message: string | null
  prompt_tokens: number
  completion_tokens: number
  next_attempt_at: number | null
  notified: string[]
  created_at: number
  updated_at: number
  finished_at: number | null
}

export type GovernanceRecordType = 'risk' | 'decision'
export type RiskStatus = 'open' | 'mitigating' | 'closed'
export type DecisionStatus = 'proposed' | 'accepted' | 'superseded'
export type RiskSeverity = 'low' | 'medium' | 'high' | 'critical'

export interface ProjectGovernanceRecord {
  id: string
  project_id: string
  record_type: GovernanceRecordType
  title: string
  description: string
  status: RiskStatus | DecisionStatus
  severity: RiskSeverity | ''
  owner_id: string
  owner_name?: string
  response: string
  rationale: string
  work_item_id: string
  work_item_title?: string
  milestone_id: string
  milestone_name?: string
  run_id: string
  artifact_id: string
  evidence_label: string
  created_by: string
  created_at: number
  updated_at: number
  resolved_at: number
}

export type ProjectHealthStatus = 'healthy' | 'attention' | 'critical'
export interface ProjectHealthReason { code: string; count: number; label: string }
export interface MilestoneHealth {
  id: string
  name: string
  status: string
  health: ProjectHealthStatus
  reasons: string[]
  due_date: string
  overdue: boolean
  total_tasks: number
  completed_tasks: number
  completion_percent: number
  blocked_tasks: number
  high_risks: number
  critical_risks: number
  pending_decisions: number
}
export interface ProjectHealth {
  status: ProjectHealthStatus
  source: 'local' | 'server' | 'server-cache'
  stale: boolean
  computed_at: number
  as_of: string
  summary: {
    total_tasks: number
    completed_tasks: number
    completion_percent: number
    overdue_tasks: number
    blocked_tasks: number
    open_milestones: number
    overdue_milestones: number
    open_risks: number
    high_risks: number
    critical_risks: number
    pending_decisions: number
  }
  reasons: ProjectHealthReason[]
  milestones: MilestoneHealth[]
}

export interface ProjectHealthTransition {
  id: string
  project_id: string
  from_status: ProjectHealthStatus
  to_status: ProjectHealthStatus
  direction: 'worsened' | 'recovered'
  rank_delta: number
  source: 'local' | 'server'
  snapshot: ProjectHealth
  created_at: number
}

export interface ProjectHealthPortfolioItem {
  project: {
    id: string
    name: string
    origin: 'local' | 'server'
    role: string
    updated_at: number
  }
  health: ProjectHealth
  last_transition: ProjectHealthTransition | null
}
export interface ProjectHealthPortfolio {
  items: ProjectHealthPortfolioItem[]
  summary: {
    total_projects: number
    critical_projects: number
    attention_projects: number
    healthy_projects: number
    stale_projects: number
    overdue_tasks: number
    blocked_tasks: number
    critical_risks: number
    pending_decisions: number
  }
  source: 'local' | 'server' | 'server-cache' | 'mixed'
  stale: boolean
  computed_at: number
}

export interface AutomationWebhookDelivery {
  id: string
  idempotency_key: string
  payload_sha256: string
  status: 'received' | 'accepted'
  fire_id: string | null
  fire_status: AutomationFire['status'] | null
  error_code: string | null
  received_at: number
  updated_at: number
}

export interface AutomationWebhookConfig {
  configured: boolean
  automation_id: string
  webhook_id: string | null
  endpoint: string | null
  created_at: number | null
  rotated_at: number | null
  deliveries: AutomationWebhookDelivery[]
  secret?: string
}

// SkillHub 商店卡（WB-070）：搜索/浏览的目录条目。
// - Server 查询代理/镜像 → 富字段（下载/星/图标/分类齐全）；
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
    source?: string
    score?: number
    subCategories?: string[]
    installed?: boolean
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
  trust_level?: 'agentmate' | 'trusted' | 'community' | 'local'
  security_scan?: SkillSecurityReport
  security_warnings_accepted?: boolean
}

export interface SkillSecurityFinding {
  code: string
  severity: 'warning' | 'dangerous'
  path: string
  line: number
  message: string
}

export interface SkillSecurityReport {
  schema_version: number
  trust_level: 'agentmate' | 'trusted' | 'community' | 'local'
  verdict: 'safe' | 'warning' | 'dangerous'
  findings: SkillSecurityFinding[]
  scanned_files: number
  scanned_bytes: number
  content_hash: string
  scripts_executable: false
}

export interface SkillUsageSummary {
  slug: string
  name: string
  release_id: string
  content_hash: string
  disabled: boolean
  installed_at: number
  discoveries: number
  loads: number
  successes: number
  failures: number
  success_rate: number | null
  last_loaded_at: number | null
  last_event_at: number | null
  rating: 'helpful' | 'neutral' | 'not_helpful' | null
}

export interface SkillBundle {
  id: string
  owner_id: string
  name: string
  description: string
  skills: string[]
  created_at: number
  updated_at: number
}

export interface SkillDetail extends InstalledSkill {
  markdown: string                       // 完整 SKILL.md（含 front-matter）
  body: string                           // 去掉 front-matter 的正文
  frontmatter: Record<string, unknown>
  references: string[]
  dir: string
  installed?: boolean                  // true=本地已安装
  catalog?: boolean                    // true=AgentMate 推荐目录定义；仍需本地安装（WB-216）
  category?: string
  tools?: string[]
  catalog_version?: string               // Server 当前目录版本；仅 AgentMate 目录技能
  update_available?: boolean             // 本机快照与目录版本不一致
  compatible?: boolean
  compatibility_error?: string
  min_app_version?: string
  release_id?: string
  content_hash?: string
  integrity_valid?: boolean
  permissions?: string[]
  catalog_permissions?: string[]
  added_permissions?: string[]
  usage?: SkillUsageSummary | null
}
