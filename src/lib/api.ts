// Compatibility facade over two explicit channels: durable business/auth data
// goes straight to AgentMate Server, while device credentials, files and agent
// execution stay on the loopback Local Agent. Provider API keys never enter UI state.

import type { AgentRun, AgentSettings, AppNotification, AppSettings, ArtifactManifest, AuditEntry, Automation, AutomationFire, AutomationWebhookConfig, BackgroundHealth, CreateAutomationInput, CustomExpert, CustomModelInput, DataSummary, DeviceDiagnostics, DeviceSettingsPayload, EmbedStatus, Idea, IdeaDetail, IdeaRelationType, IdeaSettlementType, InstalledSkill, KbDocument, KbRetrieveHit, KdocsFile, KnowledgeBase, KnowledgeConfig, LocalConnectorInstance, LocalConnectorPayload, Me, MemoryData, MemoryItem, MemorySearchResult, MemoryStats, MemoryTrace, Milestone, ModelGovernance, ModelOption, ModelPolicy, ModelsResponse, OpsSummary, Orchestration, PersonalActionItemsResponse, ProjectGovernanceRecord, ProjectHealth, ProjectHealthPortfolio, ProjectHealthTransition, ProjectInfo, RunStatus, SessionInfo, SharedPmPreferences, SharedPmPreferencesPatch, SkillBundle, SkillCard, SkillDetail, SkillSecurityReport, SystemSettings, WorkAttachment, WorkItem, WorkItemDelivery, WorkPriority, WorkStatus, WorkspaceMemory } from './types'
import { LOCAL_API_BASE, channelSnapshot, serverApiBase, serverGet, serverGetAll, serverSend } from './channels'

// In the browser, /api is proxied to the backend by Vite. Inside the Tauri shell
// there's no proxy and the app is served from tauri://localhost, so hit the local
// backend directly (CORS on the backend allows the tauri origin).
export const API_BASE = LOCAL_API_BASE

// Server-issued Bearer token for AgentMate accounts. Stored in localStorage so
// it survives reloads and is readable by both api.ts and the SSE reader. No
// token means anonymous guest scope, never a separate local account.
export const TOKEN_KEY = 'wb.token'
export const LOCAL_AUTH_INVALID_EVENT = 'agentmate:local-auth-invalid'

export function authHeaders(): Record<string, string> {
  const t = localStorage.getItem(TOKEN_KEY)
  return t ? { Authorization: `Bearer ${t}` } : {}
}

function invalidateStaleServerToken(): boolean {
  if (!localStorage.getItem(TOKEN_KEY)) return false
  localStorage.removeItem(TOKEN_KEY)
  window.dispatchEvent(new Event(LOCAL_AUTH_INVALID_EVENT))
  return true
}

async function get<T>(path: string): Promise<T> {
  let r = await fetch(`${API_BASE}${path}`, { headers: authHeaders() })
  // A Server switch can leave an opaque token from the previous authority in
  // the browser. Local GETs are idempotent: clear that identity and retry once
  // as the existing anonymous device scope. Writes are never replayed below.
  if (r.status === 401 && invalidateStaleServerToken()) {
    r = await fetch(`${API_BASE}${path}`)
  }
  if (!r.ok) throw new Error(`GET ${path} → ${r.status}`)
  return r.json() as Promise<T>
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { ...(body ? { 'Content-Type': 'application/json' } : {}), ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (r.status === 401) invalidateStaleServerToken()
  if (!r.ok) throw new Error(`${method} ${path} → ${r.status}`)
  return r.json() as Promise<T>
}

export interface AuthResult {
  token: string
  expires_at: number
  user: { id: string; name: string; role: string; plan: string }
}

async function serverAutomationSessions(automationId?: string): Promise<SessionInfo[]> {
  const [runResult, sessionResult] = await Promise.all([
    serverGetAll<AgentRun>('/runs', 'runs'),
    serverGetAll<SessionInfo>('/sessions', 'sessions'),
  ])
  const bySession = new Map<string, AgentRun>()
  for (const run of runResult) {
    const linkedId = String(run.request_snapshot?.automation_id || '')
    if (!linkedId || (automationId && linkedId !== automationId)) continue
    const previous = bySession.get(run.session_id)
    if (!previous || (run.updated_at || 0) >= (previous.updated_at || 0)) {
      bySession.set(run.session_id, run)
    }
  }
  return sessionResult.flatMap((session) => {
    const run = bySession.get(session.id)
    if (!run) return []
    const runStatus = run.status === 'completed' ? 'ok'
      : run.status === 'failed' || run.status === 'cancelled' ? 'error'
        : 'running'
    return [{ ...session, run_status: runStatus, run_kind: 'test' as const }]
  })
}

type ServerAccount = {
  id: string
  name: string
  plan?: string
  is_platform_admin?: boolean
}

type ServerAccountPayload = { account?: ServerAccount; user?: ServerAccount }

function serverAccount(value: ServerAccountPayload): ServerAccount {
  const account = value.account ?? value.user
  if (!account?.id) throw new Error('AgentMate Server 返回了无效账号信息')
  return account
}

function authResult(value: { token: string; expires_at: number } & ServerAccountPayload): AuthResult {
  const account = serverAccount(value)
  return {
    token: value.token,
    expires_at: value.expires_at,
    user: {
      id: account.id,
      name: account.name,
      role: account.is_platform_admin ? 'admin' : 'user',
      plan: account.plan || 'free',
    },
  }
}

export interface SsoProvider { id: 'google' | 'wechat' | 'telegram'; label: string }
export interface SsoStartResult {
  attempt_id: string
  attempt_token: string
  auth_url: string
  expires_at: number
}

export class SkillSecurityError extends Error {
  code: string
  report: SkillSecurityReport

  constructor(code: string, message: string, report: SkillSecurityReport) {
    super(message)
    this.name = 'SkillSecurityError'
    this.code = code
    this.report = report
  }
}

async function readSkillResponse<T>(response: Response, fallback: string): Promise<T> {
  if (response.ok) return response.json() as Promise<T>
  let message = `${fallback}（${response.status}）`
  try {
    const payload = await response.json() as {
      detail?: string | {
        code?: string
        message?: string
        security_scan?: SkillSecurityReport
      }
    }
    const detail = payload.detail
    if (detail && typeof detail === 'object' && detail.security_scan) {
      throw new SkillSecurityError(
        detail.code || 'skill_security_rejected',
        detail.message || message,
        detail.security_scan,
      )
    }
    if (detail) message = String(detail)
  } catch (error) {
    if (error instanceof SkillSecurityError) throw error
  }
  throw new Error(message)
}

export const api = {
  me: async () => {
    const account = serverAccount(await serverGet<ServerAccountPayload>('/me', { cache: false }))
    return {
      id: account.id,
      name: account.name,
      authenticated: true,
      role: account.is_platform_admin ? 'admin' : 'user',
      plan: account.plan || 'free',
      // Runtime credentials are device-local and are intentionally not inferred
      // from the Server account response.
      llm_configured: false,
      model: '',
    } satisfies Me
  },
  opsSummary: (days = 7) => get<OpsSummary>(`/ops/summary?days=${days}`),
  backgroundHealth: () => get<BackgroundHealth>('/ops/background-health'),

  // 设置 · 个性化（WB-147）：回复风格 + 自定义指令，按 owner 存后端 KV、注入 agent 系统提示。
  settings: () => get<AppSettings>('/settings'),
  saveSettings: (body: { style?: string; custom_instructions?: string }) =>
    send<AppSettings>('PUT', '/settings', body),
  systemSettings: () => get<SystemSettings>('/settings/system'),
  saveSystemSettings: (body: Partial<SystemSettings>) =>
    send<SystemSettings>('PUT', '/settings/system', body),
  runtimeSettings: () => get<DeviceSettingsPayload>('/settings/runtime'),
  saveRuntimeSettings: (values: Record<string, unknown>, clear: string[] = []) =>
    send<DeviceSettingsPayload>('PUT', '/settings/runtime', { values, clear }),
  testRuntimeSettings: (group: string) =>
    send<{ ok: boolean; error?: string; [key: string]: unknown }>('POST', '/settings/runtime/test', { group }),
  deviceDiagnostics: () => get<DeviceDiagnostics>('/device-diagnostics'),
  deviceDiagnosticAction: (action: 'retry_transport' | 'register_device' | 'clear_completed') =>
    send<{ result: Record<string, unknown>; diagnostics: DeviceDiagnostics }>('POST', '/device-diagnostics/actions', { action }),

  // 设置 · 记忆（WB-148；WB-166/167 认知记忆；WB-168 白盒管理）。
  memory: (status?: string, projectId?: string | null) => {
    const q = new URLSearchParams()
    if (status) q.set('status', status)
    if (projectId) q.set('project_id', projectId)
    return get<MemoryData>(`/memory${q.size ? `?${q}` : ''}`)
  },
  addMemory: (content: string, projectId?: string | null) =>
    send<MemoryItem>('POST', '/memory', { content, project_id: projectId || null }),
  editMemory: (id: string, content: string) => send<MemoryItem>('PUT', `/memory/${id}`, { content }),
  deleteMemory: (id: string) => send<{ ok: boolean }>('DELETE', `/memory/${id}`),
  clearMemory: (projectId?: string | null) =>
    send<{ ok: boolean; removed: number }>('POST', `/memory/clear${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''}`),
  setMemoryEnabled: (enabled: boolean) => send<{ enabled: boolean }>('PUT', '/memory/enabled', { enabled }),
  setEmbedBackend: (backend: string) => send<EmbedStatus>('PUT', '/memory/embed-backend', { backend }),
  memoryStats: (projectId?: string | null) =>
    get<MemoryStats>(`/memory/stats${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''}`),
  searchMemory: (query: string, top_k = 8, projectId?: string | null) =>
    send<MemorySearchResult>('POST', '/memory/search', { query, top_k, project_id: projectId || null }),
  setMemoryImportance: (id: string, importance: number) => send<MemoryItem>('PATCH', `/memory/${id}/importance`, { importance }),
  archiveMemory: (id: string) => send<MemoryItem>('POST', `/memory/${id}/archive`),
  rollbackMemory: (id: string) => send<MemoryItem>('POST', `/memory/${id}/rollback`),
  memoryDetail: (id: string) => get<MemoryTrace>(`/memory/${id}`),
  workspaceMemory: (projectId: string) =>
    get<WorkspaceMemory>(`/memory/workspace?project_id=${encodeURIComponent(projectId)}`),
  saveWorkspaceMemory: (projectId: string, content: string) =>
    send<WorkspaceMemory>('PUT', '/memory/workspace', { project_id: projectId, content }),

  // WB-422 local-only idea inbox. Raw idea content never syncs to Server.
  listIdeas: (filters?: { projectId?: string; status?: string; q?: string }) => {
    const query = new URLSearchParams()
    if (filters?.projectId) query.set('project_id', filters.projectId)
    if (filters?.status) query.set('status', filters.status)
    if (filters?.q) query.set('q', filters.q)
    return get<{ ideas: Idea[] }>(`/ideas${query.size ? `?${query}` : ''}`)
  },
  getIdea: (id: string) => get<IdeaDetail>(`/ideas/${id}`),
  createIdea: (body: {
    title?: string; content: string; project_id?: string | null; tags?: string[]
    source_type?: string; source_session_id?: string | null; source_message_id?: string | null
  }) => send<{ idea: Idea; created: boolean }>('POST', '/ideas', body),
  updateIdea: (id: string, patch: {
    title?: string; content?: string; project_id?: string | null
    status?: string; tags?: string[]; processing_session_id?: string | null
  }) => send<IdeaDetail>('PATCH', `/ideas/${id}`, patch),
  addIdeaRelation: (id: string, targetIdeaId: string, relation: IdeaRelationType) =>
    send<IdeaDetail>('POST', `/ideas/${id}/relations`, { target_idea_id: targetIdeaId, relation }),
  removeIdeaRelation: (id: string, targetIdeaId: string, relation: IdeaRelationType) =>
    send<IdeaDetail>('DELETE', `/ideas/${id}/relations/${targetIdeaId}/${relation}`),
  applyIdeaProcessing: (id: string) => send<IdeaDetail>('POST', `/ideas/${id}/apply-processing`),
  ideaMemoryPreview: (id: string) => get<{
    current: string; addition: string; proposed: string; base_sha256: string; would_exceed: boolean
  }>(`/ideas/${id}/memory-preview`),
  settleIdea: (id: string, kind: IdeaSettlementType, memoryBaseSha256 = '') =>
    send<{ idea: IdeaDetail; target: { type: IdeaSettlementType; id: string }; created: boolean }>(
      'POST', `/ideas/${id}/settle`, { kind, memory_base_sha256: memoryBaseSha256 },
    ),

  // 设置 · 数据管理（WB-149）：导出本人数据（下载 JSON）+ 清空个人对话。
  dataSummary: () => get<DataSummary>('/data/summary'),
  dataExport: () => get<Record<string, unknown>>('/data/export'),
  clearConversations: () => send<{ ok: boolean; removed: number }>('POST', '/data/clear-conversations'),

  // 设置 · 智能体设置（WB-150）：工具步数上限 + 回复发散度，run_chat 真读真用。
  agentSettings: () => get<AgentSettings>('/settings/agent'),
  saveAgentSettings: (body: { max_rounds?: number; temperature?: number }) =>
    send<AgentSettings>('PUT', '/settings/agent', body),

  // 设置 · 安全中心（WB-152）：命令黑名单(真拦截) + 审计日志(真记录)。
  securityPolicy: () => get<{ command_blocklist: string[] }>('/security/policy'),
  saveSecurityPolicy: (command_blocklist: string[]) =>
    send<{ command_blocklist: string[] }>('PUT', '/security/policy', { command_blocklist }),
  securityAudit: () => get<{ items: AuditEntry[] }>('/security/audit'),
  clearAudit: () => send<{ ok: boolean; removed: number }>('POST', '/security/audit/clear'),

  register: async (name: string, password: string) =>
    authResult(await serverSend<{ token: string; expires_at: number } & ServerAccountPayload>('POST', '/auth/register', { name, password })),
  login: async (name: string, password: string) =>
    authResult(await serverSend<{ token: string; expires_at: number } & ServerAccountPayload>('POST', '/auth/login', { name, password })),
  ssoProviders: () => serverGet<{ providers: SsoProvider[] }>('/auth/sso/providers', { cache: false }),
  authCapabilities: () => serverGet<{ password_registration: boolean; registration_policy: string; min_password_length: number; bootstrap_available: boolean }>('/auth/capabilities', { cache: false }),
  ssoStart: (provider: string, invite_code = '') =>
    serverSend<SsoStartResult>('POST', '/auth/sso/start', { provider, invite_code }),
  ssoPoll: async (attempt_id: string, attempt_token: string) => {
    const result = await serverSend<(
      { status: 'pending' | 'error'; error_code?: string }
      | ({ status: 'completed'; token: string; expires_at: number } & ServerAccountPayload)
    )>('POST', '/auth/sso/poll', { attempt_id, attempt_token })
    return result.status === 'completed'
      ? { status: 'completed' as const, ...authResult(result) }
      : result
  },
  logout: () => serverSend<{ ok: boolean }>('POST', '/auth/logout'),

  // 厂商预置 + 自定义兜底（WB-128）。providers 供配置弹窗分组；models 是 picker 扁平可选列表。
  models: () => get<ModelsResponse>('/models'),
  modelGovernance: () => get<ModelGovernance>('/models/governance'),
  setModelGovernance: (policy: ModelPolicy & { default_run_token_budget: number }) =>
    send<ModelGovernance>('PUT', '/models/governance', policy),
  // 默认模型（WB-136）：未显式选模型时跟随它，按 owner 存后端 DB（取代 .env）。''=清除。
  setDefaultModel: (model_ref: string) =>
    send<{ ok: boolean; default_model: string }>('PUT', '/models/default', { model_ref }),
  // 厂商 API Key（空串 = 撤销）；模型增删/隐藏（厂商上新/清理）。key 只后端存、绝不回前端。
  setProviderKey: (pid: string, api_key: string) =>
    send<{ ok: boolean; has_key: boolean }>('PUT', `/providers/${pid}/key`, { api_key }),
  // base_url/请求路径覆盖（空串=恢复预置默认）+ 在线拉取厂商真实模型（WB-129）。
  setProviderConfig: (pid: string, base_url: string, chat_path: string) =>
    send<{ ok: boolean; base_url: string; chat_path: string }>('PATCH', `/providers/${pid}/config`, { base_url, chat_path }),
  fetchProviderModels: (pid: string) =>
    send<{ ok: boolean; models?: string[]; error?: string }>('POST', `/providers/${pid}/models/fetch`),
  checkProviderHealth: (pid: string) =>
    send<{ provider_id: string; status: 'healthy' | 'unhealthy'; checked_at: number; latency_ms: number; error_code: string }>('POST', `/providers/${pid}/health`),
  addProviderModel: (pid: string, model_id: string) =>
    send<{ ok: boolean }>('POST', `/providers/${pid}/models`, { model_id }),
  // 模型能力/成本元数据（WB-132）。model_ref = 选择键（@provider:model 或自定义名）。
  setModelMeta: (model_ref: string, meta: { capabilities: string[]; input_cost: number | null; input_cost_cached: number | null; output_cost: number | null; context_window: number | null; max_output_tokens: number | null; currency: string | null; note: string | null }) =>
    send<{ ok: boolean }>('PUT', '/models/meta', { model_ref, ...meta }),
  resetModelMeta: (model_ref: string) =>
    send<{ ok: boolean }>('PUT', '/models/meta', { model_ref, reset: true }),
  // 删除厂商模型（WB-133，统一动作）：预置 → 内部标记移除、自加 → 删行。复用既有 /hide 端点(hidden:true)。
  deleteProviderModel: (pid: string, model_id: string) =>
    send<{ ok: boolean }>('POST', `/providers/${pid}/models/hide`, { model_id, hidden: true }),
  // 自由填写的自定义模型（WB-124，兜底）。
  createCustomModel: (m: CustomModelInput) => send<ModelOption>('POST', '/models/custom', m),
  updateCustomModel: (id: string, m: Partial<CustomModelInput>) =>
    send<ModelOption>('PATCH', `/models/custom/${id}`, m),
  deleteCustomModel: (id: string) => send<{ ok: boolean }>('DELETE', `/models/custom/${id}`),

  // 橱窗目录（WB-060）：原 data/catalog.ts 静态商品卡，现由后端供给。按 export 名分组的对象。
  getCatalog: async () => {
    const { items } = await serverGet<{ items: Array<{ category: string; data: unknown }> }>('/catalog')
    const grouped: Record<string, unknown[]> = {}
    for (const item of items) {
      if (!grouped[item.category]) grouped[item.category] = []
      grouped[item.category].push(item.data)
    }
    return grouped as Record<string, unknown>
  },
  inspirationFavorites: () => get<{ ids: string[] }>('/catalog/inspiration-favorites'),
  setInspirationFavorite: (templateId: string, favorite: boolean) =>
    send<{ ids: string[] }>('PUT', `/catalog/inspiration-favorites/${encodeURIComponent(templateId)}`, { favorite }),

  // Server collaboration reads/writes are direct. These compatibility method
  // names remain temporarily so view components can migrate independently.
  serverComments: async (pid: string) => ({
    server: true,
    ...(await serverGet<{ comments: { id: string; author_name: string; body: string; created_at: number }[] }>(`/projects/${pid}/comments`)),
  }),
  serverPostComment: (pid: string, body: string) =>
    serverSend<{ id: string; mentioned?: number }>('POST', `/projects/${pid}/comments`, { body }),
  serverItemComments: async (pid: string, wid: string) => ({
    server: true,
    ...(await serverGet<{ comments: { id: string; author_name: string; body: string; created_at: number }[] }>(`/projects/${pid}/work-items/${wid}/comments`)),
  }),
  serverPostItemComment: (pid: string, wid: string, body: string) =>
    serverSend<{ id: string; mentioned?: number }>('POST', `/projects/${pid}/work-items/${wid}/comments`, { body }),
  serverPresence: async (pid: string) => ({
    server: true,
    ...(await serverGet<{ presence: { account_id: string; name: string; role: string; online: boolean; last_seen: number }[] }>(`/projects/${pid}/presence`)),
  }),
  serverTimeline: async (pid: string) => {
    const result = await serverGet<{ events: import('./types').ServerTimelineEvent[] }>(`/projects/${pid}/timeline`)
    const stale = channelSnapshot().server.state === 'cached'
    return { server: true, reachable: !stale, stale, ...result }
  },
  serverProjectActivity: async (pid: string) => ({
    server: true,
    ...(await serverGet<{ activity: { id: string; actor: string; kind: string; detail: string; created_at: number }[] }>(`/projects/${pid}/activity`)),
  }),
  serverProjectCustomFields: async (pid: string) => ({
    server: true,
    ...(await serverGet<{ fields: import('./types').ServerProjectField[] }>(`/projects/${pid}/custom-fields`)),
  }),
  serverCreateProjectCustomField: async (pid: string, body: Omit<import('./types').ServerProjectField, 'id'>) => ({
    server: true,
    field: await serverSend<import('./types').ServerProjectField>('POST', `/projects/${pid}/custom-fields`, body),
  }),
  serverUpdateProjectCustomField: async (pid: string, fieldId: string, body: Partial<Omit<import('./types').ServerProjectField, 'id'>>) => ({
    server: true,
    field: await serverSend<import('./types').ServerProjectField>('PATCH', `/projects/${pid}/custom-fields/${fieldId}`, body),
  }),
  serverDeleteProjectCustomField: async (pid: string, fieldId: string) => ({
    server: true,
    ...(await serverSend<{ ok: boolean }>('DELETE', `/projects/${pid}/custom-fields/${fieldId}`)),
  }),
  serverProjectSprints: async (pid: string) => ({
    server: true,
    ...(await serverGet<{ sprints: import('./types').ServerProjectSprint[] }>(`/projects/${pid}/sprints`)),
  }),
  serverCreateProjectSprint: async (pid: string, body: Omit<import('./types').ServerProjectSprint, 'id'> & { milestone_id?: string }) => ({
    server: true,
    sprint: await serverSend<import('./types').ServerProjectSprint>('POST', `/projects/${pid}/sprints`, body),
  }),
  serverUpdateProjectSprint: async (pid: string, sprintId: string, body: Partial<Omit<import('./types').ServerProjectSprint, 'id'> & { milestone_id?: string }>) => ({
    server: true,
    sprint: await serverSend<import('./types').ServerProjectSprint>('PATCH', `/projects/${pid}/sprints/${sprintId}`, body),
  }),
  serverDeleteProjectSprint: async (pid: string, sprintId: string) => ({
    server: true,
    ...(await serverSend<{ ok: boolean }>('DELETE', `/projects/${pid}/sprints/${sprintId}`)),
  }),
  serverProjectPmPreferences: async (pid: string) => ({
    server: true,
    preferences: await serverGet<SharedPmPreferences>(`/projects/${pid}/pm-preferences`),
  }),
  serverUpdateProjectPmPreferences: async (pid: string, patch: SharedPmPreferencesPatch) => ({
    server: true,
    preferences: await serverSend<SharedPmPreferences>('PUT', `/projects/${pid}/pm-preferences`, patch),
  }),
  serverNotifications: async () => ({
    server: true,
    ...(await serverGet<{ notifications: { id: string; title: string; body: string; created_at: number; read: number }[]; unread: number }>('/notifications')),
  }),
  serverMarkNotifs: (ids?: string[]) => serverSend<{ ok: boolean }>('POST', '/notifications/read', ids ? { ids } : {}),

  // 助理外部渠道 · Telegram（WB-072）。状态 + 真实会话历史；say = 从 App 驱动同一助手
  // （与 Telegram 共用同一助理会话）。渠道是本机 local-first 特性，不携带项目/登录作用域。
  // 多助理 · 多渠道（WB-086/087/088）。token 为 write-only：只在非空时传，后端绝不回传其值。
  listAssistants: () => get<{ assistants: Assistant[] }>('/assistants'),
  getAssistant: (id: string) => get<Assistant>(`/assistants/${id}`),
  createAssistant: (body: AssistantInput) => send<Assistant>('POST', '/assistants', body),
  updateAssistant: (id: string, patch: AssistantInput) => send<Assistant>('PATCH', `/assistants/${id}`, patch),
  deleteAssistant: (id: string) => send<{ ok: boolean }>('DELETE', `/assistants/${id}`),
  assistantSay: (id: string, text: string) =>
    send<{ session_id: string; reply: string }>('POST', `/assistants/${id}/say`, { text }),
  channelTypes: () => get<{ types: ChannelType[] }>('/channels/types'),
  addAssistantChannel: (id: string, body: ChannelInput) =>
    send<AssistantChannel>('POST', `/assistants/${id}/channels`, body),
  updateAssistantChannel: (id: string, cid: string, body: ChannelInput) =>
    send<AssistantChannel>('PATCH', `/assistants/${id}/channels/${cid}`, body),
  deleteAssistantChannel: (id: string, cid: string) =>
    send<{ ok: boolean }>('DELETE', `/assistants/${id}/channels/${cid}`),
  unbindAssistantChannel: (id: string, cid: string) =>
    send<AssistantChannel>('POST', `/assistants/${id}/channels/${cid}/unbind`),

  listSessions: async (space?: string) => {
    const sessions = await serverGetAll<SessionInfo>('/sessions', 'sessions')
    return { sessions: space ? sessions.filter((session) => session.space === space) : sessions }
  },

  getMessages: async (id: string) => {
    const [session, result, runs] = await Promise.all([
      serverGet<SessionInfo>(`/sessions/${id}`),
      serverGetAll<RawMessage & { actor_id?: string }>(`/sessions/${id}/messages`, 'messages', 500),
      serverGetAll<AgentRun>(`/runs?session_id=${encodeURIComponent(id)}`, 'runs'),
    ])
    const runById = new Map(runs.map((run) => [run.id, run]))
    return {
      session,
      runs,
      messages: result.map((message) => ({
        ...message,
        actor: message.actor || message.actor_id || message.role,
        usage: message.usage || null,
        run_status: message.run_id ? runById.get(message.run_id)?.status : undefined,
        run_plan: message.run_id ? runById.get(message.run_id)?.plan : undefined,
        run_plan_version: message.run_id ? runById.get(message.run_id)?.plan_version : undefined,
        run_project_id: message.run_id ? runById.get(message.run_id)?.project_id : undefined,
        run_queue_context: message.run_id ? runById.get(message.run_id)?.queue_context : undefined,
      })),
    }
  },

  listRuns: (filters?: { sessionId?: string; projectId?: string; workItemId?: string }) => {
    const query = new URLSearchParams()
    if (filters?.sessionId) query.set('session_id', filters.sessionId)
    if (filters?.projectId) query.set('project_id', filters.projectId)
    if (filters?.workItemId) query.set('work_item_id', filters.workItemId)
    return serverGetAll<AgentRun>(`/runs${query.size ? `?${query}` : ''}`, 'runs')
      .then((runs) => ({ runs }))
  },
  getRun: (id: string) => serverGet<AgentRun>(`/runs/${id}`),
  listRunArtifacts: async (id: string) => {
    const assets = await serverGetAll<ArtifactManifest & { object_ref?: string }>(`/assets?run_id=${encodeURIComponent(id)}`, 'assets')
    return {
      artifacts: assets.map((asset) => ({
        ...asset,
        path: asset.path || asset.object_ref || '',
        acceptance_status: asset.acceptance_status || 'pending',
      })),
    }
  },
  reviewArtifact: async (id: string, status: 'accepted' | 'rejected' | 'pending') => {
    const current = await serverGet<ArtifactManifest & { version: number }>(`/assets/${id}`, { cache: false })
    return serverSend<ArtifactManifest>('PATCH', `/assets/${id}`, {
      expected_version: current.version,
      acceptance_status: status,
      accepted_at: status === 'accepted' ? Date.now() / 1000 : null,
    })
  },
  retryRun: async (id: string, idempotencyKey?: string) => {
    const current = await serverGet<AgentRun>(`/runs/${id}`, { cache: false })
    const result = await serverSend<{ run: AgentRun; duplicate: boolean }>('POST', '/runs', {
      session_id: current.session_id,
      work_item_id: current.work_item_id || null,
      mode: current.mode,
      workspace: current.workspace,
      retry_of: id,
      model_ref: current.model_ref || null,
      model_id: current.model_id || null,
      model_snapshot: current.model_snapshot || {},
      permission_snapshot: current.permission_snapshot || {},
      request_snapshot: {},
    }, { headers: { 'Idempotency-Key': idempotencyKey || `retry:${crypto.randomUUID()}` } })
    return { run: result.run, created: !result.duplicate }
  },
  promoteRunPlanItem: (runId: string, itemId: string) =>
    send<{ run: AgentRun; work_item: WorkItem; created: boolean }>(
      'POST', `/runs/${runId}/plan/${itemId}/promote`,
    ),

  createOrchestration: (body: {
    team_name: string; goal: string; project_id?: string | null; idempotency_key: string
    max_nodes?: number; max_parallel?: number; max_total_tokens?: number
  }) => send<{ orchestration: Orchestration; created: boolean }>('POST', '/orchestrations', body),
  getOrchestration: (id: string) => get<{ orchestration: Orchestration }>(`/orchestrations/${id}`),
  listOrchestrations: () => get<{ orchestrations: Orchestration[] }>('/orchestrations'),
  cancelOrchestration: (id: string) =>
    send<{ cancelled: boolean; orchestration: Orchestration }>('POST', `/orchestrations/${id}/cancel`),

  renameSession: async (id: string, title: string) => {
    const current = await serverGet<SessionInfo & { version: number }>(`/sessions/${id}`, { cache: false })
    await serverSend<SessionInfo>('PATCH', `/sessions/${id}`, { title, expected_version: current.version })
    return { ok: true }
  },

  deleteSession: async (id: string) => {
    const current = await serverGet<SessionInfo & { version: number }>(`/sessions/${id}`, { cache: false })
    return serverSend<{ ok: boolean }>('DELETE', `/sessions/${id}?expected_version=${current.version}`)
  },

  pauseRun: (runId: string) => serverSend<{ run: AgentRun }>('POST', `/runs/${runId}/pause`),
  resumeRun: (runId: string) => serverSend<{ run: AgentRun }>('POST', `/runs/${runId}/resume`),
  cancelRun: (runId: string) => serverSend<{ run: AgentRun }>('POST', `/runs/${runId}/cancel`),
  // Compatibility alias for older callers.  "stop" is terminal cancellation;
  // interactive pause uses pauseRun and never aborts the Server event follower.
  stopRun: (runId: string) => serverSend<{ run: AgentRun }>('POST', `/runs/${runId}/cancel`),

  answerRun: (runId: string, questionEventId: string, answers: string[]) =>
    serverSend<{ command: { id: string } }>('POST', `/runs/${runId}/answer`, {
      question_event_id: questionEventId,
      answers,
    }),

  listProjects: async () => {
    const result = await serverGet<{ projects: ProjectInfo[] }>('/projects')
    return { projects: result.projects.map((project) => ({ ...project, origin: 'server' as const })) }
  },

  createProject: (body: {
    name: string
    instruction: string
    connectors: string[]
    experts: string[]
    skills: string[]
    knowledge_ids: string[]
  }) => {
    if (body.knowledge_ids.length) {
      return Promise.reject(new Error('项目知识库绑定必须由 Server/Console 管理'))
    }
    return serverSend<ProjectInfo>('POST', '/projects', {
      name: body.name,
      instruction: body.instruction,
      connectors: body.connectors,
      experts: body.experts,
      skills: body.skills,
    }).then((project) => ({ ...project, origin: 'server' as const }))
  },

  getProject: (id: string) => serverGet<ProjectInfo>(`/projects/${id}`).then((project) => ({ ...project, origin: 'server' as const })),

  // Custom experts (我的专家 · WB-049).
  listExperts: () => get<{ experts: CustomExpert[] }>('/experts'),
  createExpert: (body: {
    name: string; subtitle?: string; avatar?: string; intro?: string; persona?: string; tags?: string[]
  }) => send<CustomExpert>('POST', '/experts', body),
  deleteExpert: (id: string) => send<{ ok: boolean }>('DELETE', `/experts/${id}`),

  // 金山文档连接器 · WPS OAuth 授权（连接/状态/断开）。connect 触发浏览器授权，
  // 返回 authUrl 供前端兜底打开；轮询 kdocsStatus 直到 authenticated。
  kdocsStatus: () => get<{ installed: boolean; authenticated: boolean }>('/connectors/kdocs/status'),
  kdocsConnect: () =>
    send<{ status: 'connected' | 'pending'; authUrl: string | null }>('POST', '/connectors/kdocs/connect'),
  kdocsDisconnect: () => send<{ status: string }>('POST', '/connectors/kdocs/disconnect'),
  localConnectors: () => get<LocalConnectorPayload>('/connectors/local'),
  createLocalConnector: (body: {
    name: string; transport: 'stdio' | 'sse'; command?: string; args?: string[]; url?: string
    environment?: Record<string, string>; secrets?: Record<string, string>; secret_keys?: string[]; enabled?: boolean
  }) => send<LocalConnectorPayload & { instance: LocalConnectorInstance }>('POST', '/connectors/local', body),
  updateLocalConnector: (id: string, body: {
    name: string; transport: 'stdio' | 'sse'; command?: string; args?: string[]; url?: string
    environment?: Record<string, string>; secrets?: Record<string, string>; secret_keys?: string[]; enabled?: boolean
  }) => send<LocalConnectorPayload & { instance: LocalConnectorInstance }>('PUT', `/connectors/local/${id}`, body),
  setLocalConnectorEnabled: (id: string, enabled: boolean) =>
    send<LocalConnectorPayload & { instance: LocalConnectorInstance }>('POST', `/connectors/local/${id}/enabled`, { enabled }),
  testLocalConnector: (id: string) =>
    send<{ ok: boolean; name: string; tools: Array<{ name: string; description: string }>; error: string }>('POST', `/connectors/local/${id}/test`),
  testConnectorByName: (name: string) =>
    send<{ ok: boolean; name: string; tools: Array<{ name: string; description: string }>; error: string }>('POST', '/connectors/local/test-by-name', { name }),
  setBuiltinConnectorCredentials: (name: string, values: Record<string, string>, clear: string[] = []) =>
    send<LocalConnectorPayload>('PUT', `/connectors/local/builtins/${encodeURIComponent(name)}/credentials`, { values, clear }),
  deleteLocalConnector: (id: string) => send<LocalConnectorPayload>('DELETE', `/connectors/local/${id}`),
  // 侧栏「金山文档」面板取数（WB-140）：空 keyword=最近访问文档，有则搜索。
  // installed/authenticated 反映连接态，供面板做诚实降级引导。
  // kind: 'recent'（最近访问）| 'star'（收藏/星标）；非空 keyword 一律走搜索。
  kdocsFiles: (keyword = '', kind: 'recent' | 'star' = 'recent') =>
    get<{ installed: boolean; authenticated: boolean; files: KdocsFile[] }>(
      `/connectors/kdocs/files?keyword=${encodeURIComponent(keyword)}&kind=${kind}`,
    ),
  // 「我的云文档」目录树浏览（WB-140）：driveId 空 → 后端自动发现个人云盘根并列根目录；
  // 传 driveId+parentId 下钻某文件夹。返回解析出的 drive_id 供继续下钻。
  // kuid 非空 → 走知识库（kwiki）列内容；否则走云盘 drive_id+parentId。
  kdocsFolder: (driveId = '', parentId = '0', kuid = '') =>
    get<{ installed: boolean; authenticated: boolean; drive_id: string; files: KdocsFile[] }>(
      `/connectors/kdocs/folder?drive_id=${encodeURIComponent(driveId)}&parent_id=${encodeURIComponent(parentId)}&kuid=${encodeURIComponent(kuid)}`,
    ),

  // SkillHub 技能 · 真实安装/发现/管理（WB-055）。清单来自 ~/.agentmate/skills 磁盘扫描，
  // 安装走真实 skillhub CLI 下载解压。key = 技能目录名。
  listSkills: () => get<{ skills: InstalledSkill[]; cli: boolean }>('/skills'),
  listSkillBundles: () => get<{ bundles: SkillBundle[] }>('/skill-bundles'),
  createSkillBundle: (body: { name: string; description?: string; skills: string[] }) =>
    send<{ bundle: SkillBundle }>('POST', '/skill-bundles', body),
  updateSkillBundle: (id: string, body: { name: string; description?: string; skills: string[] }) =>
    send<{ bundle: SkillBundle }>('PUT', `/skill-bundles/${encodeURIComponent(id)}`, body),
  deleteSkillBundle: (id: string) =>
    send<{ ok: boolean }>('DELETE', `/skill-bundles/${encodeURIComponent(id)}`),
  // SkillHub 实时搜索：本地 App 直接查询第三方市场，Server 不参与（WB-215）。
  searchSkills: (q: string, limit = 12) =>
    get<{ results: SkillCard[]; source?: string }>(`/skills/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  // SkillHub 实时排行：本地 App 后端直接执行 skill rankings。
  skillRankings: (type = 'featured') =>
    get<{ type: string; skills: SkillCard[]; source: 'app' }>(`/skills/rankings?type=${encodeURIComponent(type)}`),
  skillDetail: (key: string) => get<{ skill: SkillDetail }>(`/skills/${encodeURIComponent(key)}`),
  skillCatalogDetail: (key: string) => get<{ skill: SkillDetail }>(`/skills/catalog/${encodeURIComponent(key)}`),
  installCatalogSkill: (key: string) =>
    send<{ ok: boolean; skill: InstalledSkill }>('POST', `/skills/catalog/${encodeURIComponent(key)}/install`),
  upgradeCatalogSkill: (key: string, acceptPermissions: string[] = []) =>
    send<{ ok: boolean; skill: InstalledSkill }>('POST', `/skills/catalog/${encodeURIComponent(key)}/upgrade`, {
      accept_permissions: acceptPermissions,
    }),
  updateSkill: (key: string, body: { name: string; description: string; instructions: string; accept_security_warnings?: boolean }) =>
    send<{ ok: boolean; skill: InstalledSkill }>('PATCH', `/skills/${encodeURIComponent(key)}`, body),
  installSkill: async (body: { slug?: string; name?: string; accept_security_warnings?: boolean }) => {
    const r = await fetch(`${API_BASE}/skills/install`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(body),
    })
    return readSkillResponse<{ ok: boolean; skill: InstalledSkill }>(r, '安装失败')
  },
  importSkillFile: async (file: File, acceptSecurityWarnings = false) => {
    const query = new URLSearchParams({
      filename: file.name,
      accept_security_warnings: String(acceptSecurityWarnings),
    })
    const r = await fetch(`${API_BASE}/skills/import?${query}`, {
      method: 'POST', headers: { 'Content-Type': 'application/octet-stream', ...authHeaders() }, body: file,
    })
    return readSkillResponse<{ ok: boolean; skill: InstalledSkill }>(r, '导入失败')
  },
  importSkillDirectory: async (files: { path: string; content: string }[], acceptSecurityWarnings = false) => {
    const r = await fetch(`${API_BASE}/skills/import-directory`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ files, accept_security_warnings: acceptSecurityWarnings }),
    })
    return readSkillResponse<{ ok: boolean; skill: InstalledSkill }>(r, '导入失败')
  },
  uninstallSkill: (key: string) => send<{ ok: boolean }>('POST', `/skills/${encodeURIComponent(key)}/uninstall`),
  restoreSkill: (key: string) => send<{ ok: boolean }>('POST', `/skills/${encodeURIComponent(key)}/restore`),
  toggleSkill: (key: string, disabled: boolean, acceptSecurityWarnings = false) =>
    send<{ ok: boolean; disabled: boolean }>('POST', `/skills/${encodeURIComponent(key)}/toggle`, {
      disabled,
      accept_security_warnings: acceptSecurityWarnings,
    }),
  rateSkill: (key: string, rating: 'helpful' | 'neutral' | 'not_helpful') =>
    send<{ rating: { slug: string; release_id: string; rating: string } }>(
      'POST',
      `/skills/${encodeURIComponent(key)}/rating`,
      { rating },
    ),
  revealSkill: (key: string) => send<{ ok: boolean }>('POST', `/skills/${encodeURIComponent(key)}/reveal`),

  updateProject: (id: string, patch: Partial<Pick<ProjectInfo, 'name' | 'instruction' | 'connectors' | 'experts' | 'skills' | 'knowledge_ids'>>) => {
    if (patch.knowledge_ids !== undefined) {
      return Promise.reject(new Error('项目知识库绑定必须由 Server/Console 管理'))
    }
    return serverSend<ProjectInfo>('PATCH', `/projects/${id}`, patch)
  },

  projectSessions: (id: string) =>
    serverGetAll<SessionInfo>(`/sessions?project_id=${encodeURIComponent(id)}`, 'sessions')
      .then((sessions) => ({ sessions })),

  // Project members / roles (M7 C2).
  listMembers: async (id: string) => {
    const result = await serverGet<{ members: Array<{ account_id: string; name: string; role: string; is_owner?: boolean }> }>(`/projects/${id}/members`)
    return { members: result.members.map((member) => ({ ...member, user_id: member.account_id, is_owner: member.is_owner || false })) }
  },
  addMember: async (id: string, name: string, role: string) => {
    await serverSend('POST', `/projects/${id}/members`, { name, role })
    return api.listMembers(id)
  },
  updateMemberRole: async (id: string, userId: string, role: string) => {
    await serverSend('PATCH', `/projects/${id}/members/${userId}`, { role })
    return api.listMembers(id)
  },
  removeMember: (id: string, userId: string) =>
    serverSend<{ ok: boolean }>('DELETE', `/projects/${id}/members/${userId}`),

  // Message center (M7 C4).
  listNotifications: () => serverGet<{ notifications: AppNotification[]; unread: number }>('/notifications'),
  markNotificationsRead: (ids?: string[]) =>
    serverSend<{ ok: boolean; unread: number }>('POST', '/notifications/read', ids ? { ids } : {}),

  listWorkItems: (project: string) => serverGet<{ items: WorkItem[] }>(`/projects/${project}/work-items`),

  listPersonalActionItems: (asOf: string) =>
    serverGet<PersonalActionItemsResponse>(`/work-items/action-items?as_of=${encodeURIComponent(asOf)}`),

  createWorkItem: (body: {
    project_id: string; title: string; status?: WorkStatus
    source?: string; assignee?: string; description?: string; due_date?: string | null; attachments?: WorkAttachment[]
    priority?: WorkPriority; start_date?: string | null; labels?: string[]
    parent_id?: string; milestone_id?: string; estimate_h?: number; spent_h?: number
    custom_fields?: Record<string, string | number | boolean>; dependency_ids?: string[]; sprint_id?: string
  }) => {
    if (body.attachments?.length) {
      return Promise.reject(new Error('任务附件必须先上传为 Server 资产'))
    }
    const { project_id, ...values } = body
    return serverSend<WorkItem>('POST', `/projects/${project_id}/work-items`, {
      ...values,
      due_date: values.due_date || '',
      start_date: values.start_date || '',
      attachments: undefined,
    })
  },

  updateWorkItem: (projectId: string, id: string, patch: {
    status?: WorkStatus; title?: string
    description?: string; due_date?: string | null; attachments?: WorkAttachment[]
    priority?: WorkPriority; start_date?: string | null; labels?: string[]
    parent_id?: string; milestone_id?: string; estimate_h?: number; spent_h?: number
    custom_fields?: Record<string, string | number | boolean>; dependency_ids?: string[]; sprint_id?: string
  }) => {
    if (patch.attachments?.length) {
      return Promise.reject(new Error('任务附件必须先上传为 Server 资产'))
    }
    return serverSend<WorkItem>('PATCH', `/projects/${projectId}/work-items/${id}`, {
      ...patch,
      due_date: patch.due_date === null ? '' : patch.due_date,
      start_date: patch.start_date === null ? '' : patch.start_date,
      attachments: undefined,
    })
  },

  deleteWorkItem: (projectId: string, id: string) => serverSend<{ ok: boolean }>('DELETE', `/projects/${projectId}/work-items/${id}`),

  getWorkItemDelivery: (projectId: string, id: string) =>
    serverGet<WorkItemDelivery>(`/projects/${projectId}/work-items/${id}/delivery`, { cache: false }),
  acceptWorkItemDelivery: (projectId: string, id: string, runId: string, artifactCount: number) =>
    serverSend<WorkItem>('POST', `/projects/${projectId}/work-items/${id}/accept`, {
      run_id: runId, artifact_count: artifactCount,
    }),
  downloadServerAsset: async (assetId: string, name: string) => {
    const grant = await serverSend<{
      token: string
    }>('POST', `/assets/${assetId}/download-grant`)
    const base = await serverApiBase()
    const response = await fetch(`${base}/assets/${assetId}/content?download=true`, {
      headers: { 'X-Asset-Token': grant.token },
    })
    if (!response.ok) throw new Error(`GET /assets/${assetId}/content → ${response.status}`)
    const href = URL.createObjectURL(await response.blob())
    const anchor = document.createElement('a')
    anchor.href = href
    anchor.download = name
    anchor.click()
    URL.revokeObjectURL(href)
  },

  // 里程碑（WB-108）：server-origin 项目走 Server 权威 + 本地镜像，离线回退本地。
  listMilestones: (project: string) => serverGet<{ milestones: Milestone[] }>(`/projects/${project}/milestones`),
  createMilestone: (body: { project_id: string; name: string; description?: string; due_date?: string | null; status?: 'open' | 'closed' }) => {
    const { project_id, ...values } = body
    return serverSend<Milestone>('POST', `/projects/${project_id}/milestones`, {
      ...values, due_date: values.due_date || '',
    })
  },
  updateMilestone: (projectId: string, id: string, patch: { name?: string; description?: string; due_date?: string | null; status?: 'open' | 'closed'; sort?: number }) =>
    serverSend<Milestone>('PATCH', `/projects/${projectId}/milestones/${id}`, patch),
  deleteMilestone: (projectId: string, id: string) => serverSend<{ ok: boolean }>('DELETE', `/projects/${projectId}/milestones/${id}`),

  listProjectGovernance: (project: string) =>
    serverGet<{ records: ProjectGovernanceRecord[] }>(`/projects/${encodeURIComponent(project)}/governance`),
  createProjectGovernance: (body: Partial<ProjectGovernanceRecord> & Pick<ProjectGovernanceRecord, 'project_id' | 'record_type' | 'title'>) =>
    serverSend<ProjectGovernanceRecord>('POST', `/projects/${body.project_id}/governance`, body),
  updateProjectGovernance: (projectId: string, id: string, patch: Partial<ProjectGovernanceRecord>) =>
    serverSend<ProjectGovernanceRecord>('PATCH', `/projects/${projectId}/governance/${id}`, patch),
  createRiskActionTask: (projectId: string, id: string, body: {
    title: string
    due_date?: string
    acceptance_criteria: string
  }) => serverSend<{ created: boolean; work_item: WorkItem; risk: ProjectGovernanceRecord }>(
    'POST', `/projects/${projectId}/governance/${id}/action-task`, body,
  ),
  deleteProjectGovernance: (projectId: string, id: string) => serverSend<{ ok: boolean }>('DELETE', `/projects/${projectId}/governance/${id}`),
  projectHealth: (project: string) => serverGet<ProjectHealth>(`/projects/${encodeURIComponent(project)}/health`),
  projectHealthPortfolio: () => serverGet<ProjectHealthPortfolio>('/project-health'),
  projectHealthEvents: (project: string) => serverGet<{ events: ProjectHealthTransition[]; source: string; stale: boolean }>(`/projects/${encodeURIComponent(project)}/health-events`),

  listAutomations: async () => {
    const result = await serverGet<{ automations: Array<Automation & { model_ref?: string | null }> }>('/automations')
    return { automations: result.automations.map((item) => ({ ...item, model: item.model_ref || null })) }
  },

  createAutomation: async (body: CreateAutomationInput) => {
    const { automation } = await serverSend<{ automation: Automation & { model_ref?: string | null } }>('POST', '/automations', {
      ...body, model_ref: body.model || null, model: undefined,
    })
    return { ...automation, model: automation.model_ref || null }
  },

  updateAutomation: async (id: string, patch: Partial<CreateAutomationInput> & {
    last_run_at?: number; last_session_id?: string | null; last_status?: Automation['last_status']
  }) => {
    const current = await serverGet<Automation & { version: number }>(`/automations/${id}`, { cache: false })
    const updated = await serverSend<Automation & { model_ref?: string | null }>('PATCH', `/automations/${id}`, {
      ...patch, model_ref: patch.model ?? undefined, model: undefined,
      expected_version: current.version,
    })
    return { ...updated, model: updated.model_ref || null }
  },

  deleteAutomation: async (id: string) => {
    const current = await serverGet<Automation & { version: number }>(`/automations/${id}`, { cache: false })
    return serverSend<{ ok: boolean }>('DELETE', `/automations/${id}?expected_version=${current.version}`)
  },

  runAutomation: (id: string) => serverSend<{
    session: SessionInfo
    user_message: RawMessage
    run: AgentRun
    duplicate: boolean
  }>('POST', `/automations/${id}/run`),

  listAutomationFires: (status = 'dead_letter') =>
    serverGet<{ fires: AutomationFire[] }>(`/automation-fires?status=${encodeURIComponent(status)}`),

  replayAutomationFire: (id: string, idempotencyKey: string) =>
    serverSend<{ ok: boolean; fire: AutomationFire }>('POST', `/automation-fires/${id}/replay`, { idempotency_key: idempotencyKey }),

  ignoreAutomationFire: (id: string) =>
    serverSend<{ ok: boolean; fire: AutomationFire }>('POST', `/automation-fires/${id}/ignore`, {}),

  listAutomationRuns: async (id: string) => ({ runs: await serverAutomationSessions(id) }),

  getAutomationWebhook: (id: string) =>
    serverGet<AutomationWebhookConfig>(`/automations/${id}/webhook`),

  createAutomationWebhook: (id: string) =>
    serverSend<AutomationWebhookConfig>('POST', `/automations/${id}/webhook`, {}),

  rotateAutomationWebhook: (id: string) =>
    serverSend<AutomationWebhookConfig>('POST', `/automations/${id}/webhook/rotate`, {}),

  deleteAutomationWebhook: (id: string) =>
    serverSend<{ ok: boolean }>('DELETE', `/automations/${id}/webhook`),

  listAllAutomationRuns: async () => ({ runs: await serverAutomationSessions() }),

  filesTree: (opts?: { project?: string; session?: string }) => {
    const q = opts?.project ? `?project=${opts.project}` : opts?.session ? `?session=${opts.session}` : ''
    return get<{ root: string; entries: FileEntry[] }>(`/files/tree${q}`)
  },

  fileContent: (path: string, opts?: { project?: string; session?: string }) => {
    let q = `?path=${encodeURIComponent(path)}`
    if (opts?.project) q += `&project=${opts.project}`
    else if (opts?.session) q += `&session=${opts.session}`
    return get<FileContent>(`/files/content${q}`)
  },

  fileUsage: (opts?: { project?: string; session?: string }) => {
    const q = opts?.project ? `?project=${opts.project}` : opts?.session ? `?session=${opts.session}` : ''
    return get<{ used: number; quota: number }>(`/files/usage${q}`)
  },

  uploadFile: async (path: string, file: File | Blob, opts?: { project?: string; session?: string }) => {
    let q = `?path=${encodeURIComponent(path)}`
    if (opts?.project) q += `&project=${opts.project}`
    else if (opts?.session) q += `&session=${opts.session}`
    // Carry the Bearer token like every other authed call — a raw fetch bypasses
    // the get()/send() helpers, so a logged-in user's upload would otherwise be
    // treated as the local owner and 404 on their own/shared project (WB-046).
    const r = await fetch(`${API_BASE}/files/upload${q}`, { method: 'POST', body: file, headers: authHeaders() })
    if (!r.ok) throw new Error(`upload → ${r.status}`)
    return r.json() as Promise<{ ok: boolean; path: string; size: number }>
  },

  // A plain <a href> can't carry the Authorization header, so fetch the bytes with
  // auth, then hand the browser a blob URL to save (token never enters the URL —
  // WB-046). Returns once the download has been triggered.
  downloadFile: async (path: string, name: string, opts?: { project?: string; session?: string }) => {
    let q = `?path=${encodeURIComponent(path)}`
    if (opts?.project) q += `&project=${opts.project}`
    else if (opts?.session) q += `&session=${opts.session}`
    const r = await fetch(`${API_BASE}/files/download${q}`, { headers: authHeaders() })
    if (!r.ok) throw new Error(`download → ${r.status}`)
    const url = URL.createObjectURL(await r.blob())
    const a = document.createElement('a')
    a.href = url
    a.download = name
    document.body.appendChild(a)
    a.click()
    a.remove()
    // Defer revoke so the browser has grabbed the blob before we free it.
    setTimeout(() => URL.revokeObjectURL(url), 10_000)
  },

  mkdir: (path: string, opts?: { project?: string; session?: string }) =>
    send<{ ok: boolean; path: string }>('POST', '/files/mkdir', { path, ...opts }),

  renameFile: (path: string, newName: string, opts?: { project?: string; session?: string }) =>
    send<{ ok: boolean; path: string; name: string }>('POST', '/files/rename', { path, new_name: newName, ...opts }),

  deleteFile: (path: string, opts?: { project?: string; session?: string }) =>
    send<{ ok: boolean }>('POST', '/files/delete', { path, ...opts }),

  // 语音输入本地转写（WB-139）。status 让 UI 提前知道能不能用；transcribe 把录音 Blob
  // 直接作 body 发（非 multipart，仿 uploadFile 带 Bearer token），后端本机 ASR 转文字。
  asrStatus: () =>
    get<{ enabled: boolean; available: boolean; model: string; loaded: boolean; error: string | null }>('/asr/status'),
  transcribeAudio: async (blob: Blob): Promise<{ text: string; language: string | null }> => {
    const r = await fetch(`${API_BASE}/asr/transcribe`, { method: 'POST', body: blob, headers: authHeaders() })
    if (!r.ok) {
      // 后端把「依赖没装 / 模型没就绪」诚实报成 503，把原因带出来给用户看。
      let detail = `转写失败（${r.status}）`
      try { detail = (await r.json())?.detail ?? detail } catch { /* 非 JSON 错误 */ }
      throw new Error(detail)
    }
    return r.json() as Promise<{ text: string; language: string | null }>
  },

  // ---- 知识库（自托管 WeKnora RAG · WB-173/174）。全走本地 backend /api/knowledge，API Key 只在后端。
  // 连接配置（WB-188）：表单填 → 后端按 owner 入库（.env 兜底）。**响应绝不含 api_key**，
  // 只有 has_key 布尔；保存时 api_key 省略=不改 / ''=撤销 / 非空=覆盖。
  knowledgeConfig: () => get<KnowledgeConfig>('/knowledge/config'),
  saveKnowledgeConfig: (body: { url?: string; api_key?: string; embedding_model_id?: string }) =>
    send<KnowledgeConfig>('PUT', '/knowledge/config', body),
  testKnowledgeConfig: () =>
    send<{ ok: boolean; error?: string; url?: string; kb_count?: number }>('POST', '/knowledge/config/test'),
  listKb: () => get<{ list: KnowledgeBase[]; total: number }>('/knowledge'),
  createKb: (body: { name: string; description?: string; icon?: string }) =>
    send<{ id: string }>('POST', '/knowledge', body),
  deleteKb: (id: string) => send<{ ok: boolean }>('DELETE', `/knowledge/${id}`),
  listKbDocs: (id: string) => get<{ list: KbDocument[]; total: number }>(`/knowledge/${encodeURIComponent(id)}/documents`),
  deleteKbDoc: (docId: string) => send<{ ok: boolean }>('DELETE', `/knowledge/documents/${docId}`),
  retrieveKb: (body: { query: string; knowledge_ids: string[]; top_k?: number }) =>
    send<{ data: KbRetrieveHit[] }>('POST', '/knowledge/retrieve', body),
  // 传文件：原始 body（非 multipart），文件名走 query，仿 uploadFile 带 Bearer（后端流式读）。
  uploadKbDoc: async (id: string, file: File | Blob, filename: string) => {
    const q = `?filename=${encodeURIComponent(filename)}`
    const r = await fetch(`${API_BASE}/knowledge/${encodeURIComponent(id)}/documents${q}`, {
      method: 'POST', body: file, headers: authHeaders(),
    })
    if (!r.ok) {
      let detail = `上传失败（${r.status}）`
      try { detail = (await r.json())?.detail ?? detail } catch { /* 非 JSON */ }
      throw new Error(detail)
    }
    return r.json() as Promise<{ successInfos: { documentId: string; fileName: string }[]; failedInfos: { fileName: string; failReason: string }[] }>
  },
}

// 多助理（WB-086/087/088）。渠道 token 绝不回传，只有 has_token 布尔。
export type AssistantMode = 'exec' | 'plan' | 'ask'
export interface AssistantChannel {
  id: string
  assistant_id: string
  type: string
  enabled: boolean
  running: boolean
  has_token: boolean
  token: string              // WB-093：本机可见的原始 token（local-first，仅本机设置 UI）
  chat_id: string            // 白名单固定 chat（telegram）
  config: Record<string, string> // WB-096：邮件渠道配置（host/port/账号/密码/白名单/暗号，本机可见）
  bound_chat_id: string | null
}
export interface Assistant {
  id: string
  name: string
  avatar: string
  instruction: string
  model: string
  mode: AssistantMode
  workspace: string          // default | project:<id> | dedicated
  experts: string[]
  skills: string[]
  connectors: string[]
  enabled: boolean
  session_id: string | null
  channels: AssistantChannel[]
  messages?: { id: string; role: 'user' | 'assistant'; content: string; created_at: number }[]
}
export interface ChannelType { type: string; label: string; available: boolean }
export interface AssistantInput {
  name?: string; avatar?: string; instruction?: string; model?: string
  mode?: AssistantMode; workspace?: string
  experts?: string[]; skills?: string[]; connectors?: string[]; enabled?: boolean
}
export interface ChannelInput {
  type?: string; config?: Record<string, unknown>; token?: string; enabled?: boolean
}

export interface RawMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  actor: string
  trace: unknown[]
  usage: { prompt: number; completion: number } | null
  run_id?: string | null
  run_status?: RunStatus | null
  run_plan?: import('./types').RunPlanItem[]
  run_plan_version?: number
  run_project_id?: string | null
  run_queue_context?: import('./types').RunQueueContext
  pending_question?: { questions: import('./types').AskQuestion[]; recovery: 'retry_required'; source: string } | null
  error?: string | null
  created_at: number
}

export interface FileEntry {
  name: string
  path: string
  type: 'd' | 'f'
  size: number | null
  mtime?: number
  children?: FileEntry[]
}

export interface FileContent {
  path: string
  name: string
  mime: string
  kind: 'text' | 'binary'
  content?: string
  size?: number
}
