// Thin REST client. All calls go to the local backend (via Vite's /api proxy in
// dev, or the Tauri sidecar in M5). The API key never lives here — it's backend-only.

import type { AppNotification, Automation, CreateAutomationInput, CustomExpert, InstalledSkill, Me, ModelOption, ProjectInfo, ProjectMember, SessionInfo, SkillDetail, WorkAttachment, WorkItem, WorkStatus } from './types'

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

  models: () => get<{ default: string; effective: string; models: ModelOption[] }>('/models'),

  // 橱窗目录（WB-060）：原 data/catalog.ts 静态商品卡，现由后端供给。按 export 名分组的对象。
  getCatalog: () => get<Record<string, unknown>>('/catalog'),

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
  }) => send<WorkItem>('POST', '/work-items', body),

  updateWorkItem: (id: string, patch: {
    status?: WorkStatus; title?: string
    description?: string; due_date?: string | null; attachments?: WorkAttachment[]
  }) => send<WorkItem>('PATCH', `/work-items/${id}`, patch),

  deleteWorkItem: (id: string) => send<{ ok: boolean }>('DELETE', `/work-items/${id}`),

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
