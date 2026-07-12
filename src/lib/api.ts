// Thin REST client. All calls go to the local backend (via Vite's /api proxy in
// dev, or the Tauri sidecar in M5). The API key never lives here — it's backend-only.

import type { AppNotification, Automation, CreateAutomationInput, CustomExpert, CustomModelInput, InstalledSkill, Me, Milestone, ModelOption, ModelsResponse, ProjectInfo, ProjectMember, SessionInfo, SkillCard, SkillDetail, WorkAttachment, WorkItem, WorkPriority, WorkStatus } from './types'

// In the browser, /api is proxied to the backend by Vite. Inside the Tauri shell
// there's no proxy and the app is served from tauri://localhost, so hit the local
// backend directly (CORS on the backend allows the tauri origin).
const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
export const API_BASE =
  import.meta.env.VITE_API_BASE ?? (isTauri ? 'http://127.0.0.1:8000/api' : '/api')

// Bearer token for real accounts (M7 C1). Stored in localStorage so it survives
// reloads and is readable by both api.ts and the SSE reader. No token → the
// backend treats the request as the local owner.
export const TOKEN_KEY = 'wb.token'
export function authHeaders(): Record<string, string> {
  const t = localStorage.getItem(TOKEN_KEY)
  return t ? { Authorization: `Bearer ${t}` } : {}
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, { headers: authHeaders() })
  if (!r.ok) throw new Error(`GET ${path} → ${r.status}`)
  return r.json() as Promise<T>
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { ...(body ? { 'Content-Type': 'application/json' } : {}), ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) throw new Error(`${method} ${path} → ${r.status}`)
  return r.json() as Promise<T>
}

export interface AuthResult { token: string; user: { id: string; name: string; role: string; plan: string } }

export const api = {
  me: () => get<Me>('/me'),

  register: (name: string, password: string) =>
    send<AuthResult>('POST', '/auth/register', { name, password }),
  login: (name: string, password: string) =>
    send<AuthResult>('POST', '/auth/login', { name, password }),
  logout: () => send<{ ok: boolean }>('POST', '/auth/logout'),

  // 厂商预置 + 自定义兜底（WB-128）。providers 供配置弹窗分组；models 是 picker 扁平可选列表。
  models: () => get<ModelsResponse>('/models'),
  // 厂商 API Key（空串 = 撤销）；模型增删/隐藏（厂商上新/清理）。key 只后端存、绝不回前端。
  setProviderKey: (pid: string, api_key: string) =>
    send<{ ok: boolean; has_key: boolean }>('PUT', `/providers/${pid}/key`, { api_key }),
  // base_url/请求路径覆盖（空串=恢复预置默认）+ 在线拉取厂商真实模型（WB-129）。
  setProviderConfig: (pid: string, base_url: string, chat_path: string) =>
    send<{ ok: boolean; base_url: string; chat_path: string }>('PATCH', `/providers/${pid}/config`, { base_url, chat_path }),
  fetchProviderModels: (pid: string) =>
    send<{ ok: boolean; models?: string[]; error?: string }>('POST', `/providers/${pid}/models/fetch`),
  addProviderModel: (pid: string, model_id: string) =>
    send<{ ok: boolean }>('POST', `/providers/${pid}/models`, { model_id }),
  // 模型能力/成本元数据（WB-132）。model_ref = 选择键（@provider:model 或自定义名）。
  setModelMeta: (model_ref: string, meta: { capabilities: string[]; input_cost: number | null; output_cost: number | null; context_window: number | null; note: string | null }) =>
    send<{ ok: boolean }>('PUT', '/models/meta', { model_ref, ...meta }),
  resetModelMeta: (model_ref: string) =>
    send<{ ok: boolean }>('PUT', '/models/meta', { model_ref, reset: true }),
  hideProviderModel: (pid: string, model_id: string, hidden: boolean) =>
    send<{ ok: boolean }>('POST', `/providers/${pid}/models/hide`, { model_id, hidden }),
  // 自由填写的自定义模型（WB-124，兜底）。
  createCustomModel: (m: CustomModelInput) => send<ModelOption>('POST', '/models/custom', m),
  updateCustomModel: (id: string, m: Partial<CustomModelInput>) =>
    send<ModelOption>('PATCH', `/models/custom/${id}`, m),
  deleteCustomModel: (id: string) => send<{ ok: boolean }>('DELETE', `/models/custom/${id}`),

  // 橱窗目录（WB-060）：原 data/catalog.ts 静态商品卡，现由后端供给。按 export 名分组的对象。
  getCatalog: () => get<Record<string, unknown>>('/catalog'),

  // 触发本地 backend 从 Hub 下行 pull（项目/成员/目录镜像，WB-062/066/070）。
  // 未接 Hub → 后端无害返回 {hub:false}；用于登录后刷新 Hub SkillHub 镜像目录等。
  hubPull: () => send<{ hub: boolean; catalog?: number }>('POST', '/hub/pull'),

  // 前端接 Hub 协作（WB-067 Slice 2）：都经本地 backend 代理转发到 Hub；未接 Hub → {hub:false}/空。
  hubStatus: () => get<{ enabled: boolean; linked: { account_id: string; name: string } | null }>('/hub/status'),
  hubLogin: (name: string, password: string, register = false) =>
    send<{ token: string; account: { id: string; name: string; is_platform_admin?: boolean } }>('POST', '/hub/login', { name, password, register }),
  hubImport: () => send<{ hub: boolean; imported: number; skipped: number }>('POST', '/hub/import'),
  hubComments: (pid: string) =>
    get<{ hub: boolean; comments: { id: string; author_name: string; body: string; created_at: number }[] }>(`/hub/projects/${pid}/comments`),
  hubPostComment: (pid: string, body: string) =>
    send<{ id: string; mentioned?: number }>('POST', `/hub/projects/${pid}/comments`, { body }),
  hubItemComments: (pid: string, wid: string) =>
    get<{ hub: boolean; comments: { id: string; author_name: string; body: string; created_at: number }[] }>(`/hub/projects/${pid}/work-items/${wid}/comments`),
  hubPostItemComment: (pid: string, wid: string, body: string) =>
    send<{ id: string; mentioned?: number }>('POST', `/hub/projects/${pid}/work-items/${wid}/comments`, { body }),
  hubPresence: (pid: string) =>
    get<{ hub: boolean; presence: { account_id: string; name: string; role: string; online: boolean; last_seen: number }[] }>(`/hub/projects/${pid}/presence`),
  hubNotifications: () =>
    get<{ hub: boolean; notifications: { id: string; title: string; body: string; created_at: number; read: number }[]; unread: number }>('/hub/notifications'),
  hubMarkNotifs: (ids?: string[]) => send<{ ok: boolean }>('POST', '/hub/notifications/read', ids ? { ids } : {}),

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

  listSessions: (space?: string) =>
    get<{ sessions: SessionInfo[] }>(`/sessions${space ? `?space=${encodeURIComponent(space)}` : ''}`),

  getMessages: (id: string) =>
    get<{ session: SessionInfo; messages: RawMessage[] }>(`/sessions/${id}/messages`),

  renameSession: (id: string, title: string) =>
    send<{ ok: boolean }>('PATCH', `/sessions/${id}`, { title }),

  deleteSession: (id: string) => send<{ ok: boolean }>('DELETE', `/sessions/${id}`),

  stopChat: (id: string) => send<{ stopped: boolean }>('POST', `/chat/${id}/stop`),

  answer: (id: string, answers: string[]) =>
    send<{ ok: boolean }>('POST', `/chat/${id}/answer`, { answers }),

  listProjects: () => get<{ projects: ProjectInfo[] }>('/projects'),

  createProject: (body: {
    name: string
    instruction: string
    connectors: string[]
    experts: string[]
    skills: string[]
  }) => send<ProjectInfo>('POST', '/projects', body),

  getProject: (id: string) => get<ProjectInfo>(`/projects/${id}`),

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

  // SkillHub 技能 · 真实安装/发现/管理（WB-055）。清单来自 ~/.workbuddy/skills 磁盘扫描，
  // 安装走真实 skillhub CLI 下载解压。key = 技能目录名。
  listSkills: () => get<{ skills: InstalledSkill[]; cli: boolean }>('/skills'),
  // SkillHub 实时搜索（WB-070）：本地 backend 优先经 Hub 查询代理（富字段），未接/不可达 → 回退本地 CLI。
  searchSkills: (q: string, limit = 12) =>
    get<{ results: SkillCard[]; source?: string }>(`/skills/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  // SkillHub 实时排行（WB-064 端点）：无 Hub 镜像时技能浏览的真实兜底源（本地 CLI 跑 skill rankings）。
  skillRankings: (type = 'featured') =>
    get<{ type: string; skills: SkillCard[] }>(`/skills/rankings?type=${encodeURIComponent(type)}`),
  skillDetail: (key: string) => get<{ skill: SkillDetail }>(`/skills/${encodeURIComponent(key)}`),
  // 安装前预览：未安装也能看 SKILL.md（后端临时下载，不落盘）。
  skillPreview: (q: { slug?: string; name?: string }) =>
    get<{ skill: SkillDetail }>(`/skills/preview?slug=${encodeURIComponent(q.slug ?? '')}&name=${encodeURIComponent(q.name ?? '')}`),
  installSkill: (body: { slug?: string; name?: string }) =>
    send<{ ok: boolean; skill: InstalledSkill }>('POST', '/skills/install', body),
  uninstallSkill: (key: string) => send<{ ok: boolean }>('POST', `/skills/${encodeURIComponent(key)}/uninstall`),
  toggleSkill: (key: string, disabled: boolean) =>
    send<{ ok: boolean; disabled: boolean }>('POST', `/skills/${encodeURIComponent(key)}/toggle`, { disabled }),
  revealSkill: (key: string) => send<{ ok: boolean }>('POST', `/skills/${encodeURIComponent(key)}/reveal`),

  updateProject: (id: string, patch: Partial<Pick<ProjectInfo, 'name' | 'instruction' | 'connectors' | 'experts' | 'skills'>>) =>
    send<ProjectInfo>('PATCH', `/projects/${id}`, patch),

  projectSessions: (id: string) =>
    get<{ sessions: SessionInfo[] }>(`/projects/${id}/sessions`),

  // Project members / roles (M7 C2).
  listMembers: (id: string) => get<{ members: ProjectMember[] }>(`/projects/${id}/members`),
  addMember: (id: string, name: string, role: string) =>
    send<{ members: ProjectMember[] }>('POST', `/projects/${id}/members`, { name, role }),
  updateMemberRole: (id: string, userId: string, role: string) =>
    send<{ members: ProjectMember[] }>('PATCH', `/projects/${id}/members/${userId}`, { role }),
  removeMember: (id: string, userId: string) =>
    send<{ ok: boolean }>('DELETE', `/projects/${id}/members/${userId}`),

  // Message center (M7 C4).
  listNotifications: () => get<{ notifications: AppNotification[]; unread: number }>('/notifications'),
  markNotificationsRead: (ids?: string[]) =>
    send<{ ok: boolean; unread: number }>('POST', '/notifications/read', ids ? { ids } : {}),

  listWorkItems: (project: string) => get<{ items: WorkItem[] }>(`/work-items?project=${project}`),

  createWorkItem: (body: {
    project_id: string; title: string; status?: WorkStatus
    description?: string; due_date?: string | null; attachments?: WorkAttachment[]
    priority?: WorkPriority; start_date?: string | null; labels?: string[]
    parent_id?: string; milestone_id?: string; estimate_h?: number; spent_h?: number
  }) => send<WorkItem>('POST', '/work-items', body),

  updateWorkItem: (id: string, patch: {
    status?: WorkStatus; title?: string
    description?: string; due_date?: string | null; attachments?: WorkAttachment[]
    priority?: WorkPriority; start_date?: string | null; labels?: string[]
    parent_id?: string; milestone_id?: string; estimate_h?: number; spent_h?: number
  }) => send<WorkItem>('PATCH', `/work-items/${id}`, patch),

  deleteWorkItem: (id: string) => send<{ ok: boolean }>('DELETE', `/work-items/${id}`),

  // 里程碑（WB-108）：hub-origin 项目走 Hub 权威 + 本地镜像，离线回退本地。
  listMilestones: (project: string) => get<{ milestones: Milestone[] }>(`/milestones?project=${project}`),
  createMilestone: (body: { project_id: string; name: string; description?: string; due_date?: string | null; status?: 'open' | 'closed' }) =>
    send<Milestone>('POST', '/milestones', body),
  updateMilestone: (id: string, patch: { name?: string; description?: string; due_date?: string | null; status?: 'open' | 'closed'; sort?: number }) =>
    send<Milestone>('PATCH', `/milestones/${id}`, patch),
  deleteMilestone: (id: string) => send<{ ok: boolean }>('DELETE', `/milestones/${id}`),

  listAutomations: () => get<{ automations: Automation[] }>('/automations'),

  createAutomation: (body: CreateAutomationInput) =>
    send<Automation>('POST', '/automations', body),

  updateAutomation: (id: string, patch: Partial<CreateAutomationInput>) =>
    send<Automation>('PATCH', `/automations/${id}`, patch),

  deleteAutomation: (id: string) => send<{ ok: boolean }>('DELETE', `/automations/${id}`),

  runAutomation: (id: string) =>
    send<{ ok: boolean; session_id: string | null }>('POST', `/automations/${id}/run`),

  listAutomationRuns: (id: string) =>
    get<{ runs: SessionInfo[] }>(`/automations/${id}/runs`),

  listAllAutomationRuns: () =>
    get<{ runs: SessionInfo[] }>('/automation-runs'),

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
