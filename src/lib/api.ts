// Thin REST client. All calls go to the local backend (via Vite's /api proxy in
// dev, or the Tauri sidecar in M5). The API key never lives here — it's backend-only.

import type { Me, ModelOption, SessionInfo } from './types'

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

  filesTree: (root = 'workspace') =>
    get<{ root: string; entries: FileEntry[] }>(`/files/tree?root=${root}`),

  fileContent: (path: string) =>
    get<FileContent>(`/files/content?path=${encodeURIComponent(path)}`),
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
