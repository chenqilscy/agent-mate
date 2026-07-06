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
  updated_at?: number
  owner_id?: string
  owner_name?: string // who ran it (M7 C3 activity feed)
  read_only?: boolean // true when the caller is a viewer, not the session's owner (M7 C3)
}

export interface ModelOption {
  icon: string
  color: string
  name: string
  level: string
  mult: string
  off: string
  group: 'builtin' | 'custom'
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
  ago?: string
  created_at?: number
  updated_at?: number
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
