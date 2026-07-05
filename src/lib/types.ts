// Shared types. The SSE event union mirrors backend/agent/events.py — one event
// type ⇄ one render shape. When the OpenAPI generator runs (pnpm gen:api) the
// REST DTOs land in api-types.ts; these hand-written types cover the SSE stream
// (which is not part of the OpenAPI schema).

export type ViewId =
  | 'home'
  | 'chat'
  | 'assistant'
  | 'projects'
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
}
