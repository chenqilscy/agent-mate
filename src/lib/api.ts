// Thin REST client. All calls go to the local backend (via Vite's /api proxy in
// dev, or the Tauri sidecar in M5). The API key never lives here — it's backend-only.

import type { Automation, CreateAutomationInput, Me, ModelOption, ProjectInfo, SessionInfo, WorkItem, WorkStatus } from './types'

export const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`)
  if (!r.ok) throw new Error(`GET ${path} → ${r.status}`)
  return r.json() as Promise<T>
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!r.ok) throw new Error(`${method} ${path} → ${r.status}`)
  return r.json() as Promise<T>
}

export const api = {
  me: () => get<Me>('/me'),

  models: () => get<{ default: string; effective: string; models: ModelOption[] }>('/models'),

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

  updateProject: (id: string, patch: Partial<Pick<ProjectInfo, 'name' | 'instruction' | 'connectors' | 'experts' | 'skills'>>) =>
    send<ProjectInfo>('PATCH', `/projects/${id}`, patch),

  projectSessions: (id: string) =>
    get<{ sessions: SessionInfo[] }>(`/projects/${id}/sessions`),

  listWorkItems: (project: string) => get<{ items: WorkItem[] }>(`/work-items?project=${project}`),

  createWorkItem: (body: { project_id: string; title: string; status?: WorkStatus }) =>
    send<WorkItem>('POST', '/work-items', body),

  updateWorkItem: (id: string, patch: { status?: WorkStatus; title?: string }) =>
    send<WorkItem>('PATCH', `/work-items/${id}`, patch),

  deleteWorkItem: (id: string) => send<{ ok: boolean }>('DELETE', `/work-items/${id}`),

  listAutomations: () => get<{ automations: Automation[] }>('/automations'),

  createAutomation: (body: CreateAutomationInput) =>
    send<Automation>('POST', '/automations', body),

  updateAutomation: (id: string, patch: Partial<CreateAutomationInput>) =>
    send<Automation>('PATCH', `/automations/${id}`, patch),

  deleteAutomation: (id: string) => send<{ ok: boolean }>('DELETE', `/automations/${id}`),

  runAutomation: (id: string) =>
    send<{ ok: boolean; session_id: string | null }>('POST', `/automations/${id}/run`),

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
    const r = await fetch(`${API_BASE}/files/upload${q}`, { method: 'POST', body: file })
    if (!r.ok) throw new Error(`upload → ${r.status}`)
    return r.json() as Promise<{ ok: boolean; path: string; size: number }>
  },

  downloadUrl: (path: string, opts?: { project?: string; session?: string }) => {
    let q = `?path=${encodeURIComponent(path)}`
    if (opts?.project) q += `&project=${opts.project}`
    else if (opts?.session) q += `&session=${opts.session}`
    return `${API_BASE}/files/download${q}`
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
