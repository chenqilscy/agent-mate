import { platform, type LocalAgentStatus } from '../platform'

const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

export const LOCAL_API_BASE =
  import.meta.env.VITE_LOCAL_API_BASE
  ?? import.meta.env.VITE_API_BASE
  ?? (isTauri ? 'http://127.0.0.1:8101/api' : '/api')

export type ServerConnectionState = {
  state: 'unknown' | 'online' | 'offline' | 'cached'
  checkedAt: number | null
  cachedAt: number | null
  error: string
}

type ChannelSnapshot = {
  server: ServerConnectionState
  localAgent: LocalAgentStatus | null
  localAgentChecked: boolean
  localAgentError: string
}

const snapshot: ChannelSnapshot = {
  server: { state: 'unknown', checkedAt: null, cachedAt: null, error: '' },
  localAgent: null,
  localAgentChecked: false,
  localAgentError: '',
}
const listeners = new Set<(value: ChannelSnapshot) => void>()

function publish(): void {
  const value = channelSnapshot()
  listeners.forEach((listener) => listener(value))
}

export function channelSnapshot(): ChannelSnapshot {
  return {
    server: { ...snapshot.server },
    localAgent: snapshot.localAgent,
    localAgentChecked: snapshot.localAgentChecked,
    localAgentError: snapshot.localAgentError,
  }
}

export function subscribeChannels(listener: (value: ChannelSnapshot) => void): () => void {
  listeners.add(listener)
  listener(channelSnapshot())
  return () => listeners.delete(listener)
}

let serverBasePromise: Promise<string> | null = null

function normalizeApiBase(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, '')
  return trimmed.endsWith('/api') ? trimmed : `${trimmed}/api`
}

export async function serverApiBase(): Promise<string> {
  if (!serverBasePromise) {
    serverBasePromise = (async () => {
      const configured = import.meta.env.VITE_SERVER_API_BASE?.trim()
      if (configured) return normalizeApiBase(configured)
      if (!platform.isDesktop) return '/server-api'
      const status = await refreshLocalAgentStatus()
      if (!status?.server_api_url) {
        throw new ChannelUnavailableError('server', 'AgentMate Server 尚未配置')
      }
      return normalizeApiBase(status.server_api_url)
    })().catch((error) => {
      serverBasePromise = null
      throw error
    })
  }
  return serverBasePromise
}

export function resetServerApiBase(): void {
  serverBasePromise = null
}

export class ChannelUnavailableError extends Error {
  readonly channel: 'server' | 'local-agent'
  readonly status: number | null

  constructor(channel: 'server' | 'local-agent', message: string, status: number | null = null) {
    super(message)
    this.name = 'ChannelUnavailableError'
    this.channel = channel
    this.status = status
  }
}

function tokenNamespace(): string {
  const token = localStorage.getItem('wb.token') || 'anonymous'
  let hash = 2166136261
  for (let index = 0; index < token.length; index += 1) {
    hash ^= token.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(36)
}

function cacheKey(path: string): string {
  return `agentmate.server-cache.v1.${tokenNamespace()}.${encodeURIComponent(path)}`
}

type CacheEnvelope<T> = { cachedAt: number; value: T }

function readCache<T>(path: string): CacheEnvelope<T> | null {
  try {
    const raw = localStorage.getItem(cacheKey(path))
    if (!raw) return null
    const parsed = JSON.parse(raw) as CacheEnvelope<T>
    return parsed && typeof parsed.cachedAt === 'number' ? parsed : null
  } catch {
    return null
  }
}

function writeCache<T>(path: string, value: T): void {
  try {
    localStorage.setItem(cacheKey(path), JSON.stringify({ cachedAt: Date.now(), value }))
  } catch {
    // A full/disabled browser cache must never turn a successful Server read into a failure.
  }
}

function markServer(state: ServerConnectionState['state'], error = '', cachedAt: number | null = null): void {
  snapshot.server = { state, checkedAt: Date.now(), cachedAt, error }
  publish()
}

async function responseError(response: Response, method: string, path: string): Promise<Error> {
  let detail = ''
  try {
    const payload = await response.json() as { detail?: unknown }
    detail = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail ?? '')
  } catch {
    // Keep a stable status-only fallback for non-JSON reverse-proxy responses.
  }
  return new ChannelUnavailableError(
    'server', detail || `${method} ${path} → ${response.status}`, response.status,
  )
}

export function serverAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('wb.token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function serverGet<T>(path: string, options: { cache?: boolean } = {}): Promise<T> {
  const useCache = options.cache !== false
  try {
    const base = await serverApiBase()
    const response = await fetch(`${base}${path}`, { headers: serverAuthHeaders() })
    if (!response.ok) {
      const error = await responseError(response, 'GET', path)
      if (response.status < 500) throw error
      throw error
    }
    const value = await response.json() as T
    if (useCache) writeCache(path, value)
    markServer('online')
    return value
  } catch (error) {
    const status = error instanceof ChannelUnavailableError ? error.status : null
    if (useCache && (status === null || status >= 500)) {
      const cached = readCache<T>(path)
      if (cached) {
        markServer('cached', error instanceof Error ? error.message : String(error), cached.cachedAt)
        return cached.value
      }
    }
    if (status === null || status >= 500) {
      markServer('offline', error instanceof Error ? error.message : String(error))
    }
    throw error
  }
}

export async function serverGetAll<T>(
  path: string,
  key: string,
  limit = 200,
  options: { cache?: boolean } = {},
): Promise<T[]> {
  const items: T[] = []
  let cursor = ''
  for (let page = 0; page < 100; page += 1) {
    const separator = path.includes('?') ? '&' : '?'
    const query = `${path}${separator}limit=${limit}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`
    const result = await serverGet<Record<string, unknown>>(query, options)
    const batch = result[key]
    if (!Array.isArray(batch)) {
      throw new ChannelUnavailableError('server', `Server page ${path} is missing ${key}`)
    }
    items.push(...batch as T[])
    cursor = typeof result.next_cursor === 'string' ? result.next_cursor : ''
    if (!cursor) return items
  }
  throw new ChannelUnavailableError('server', `Server pagination exceeded 100 pages: ${path}`)
}

export async function serverSend<T>(
  method: string,
  path: string,
  body?: unknown,
  options: { headers?: Record<string, string> } = {},
): Promise<T> {
  try {
    const base = await serverApiBase()
    const response = await fetch(`${base}${path}`, {
      method,
      headers: {
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...serverAuthHeaders(),
        ...options.headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
    if (!response.ok) throw await responseError(response, method, path)
    const value = await response.json() as T
    markServer('online')
    return value
  } catch (error) {
    const status = error instanceof ChannelUnavailableError ? error.status : null
    if (status === null || status >= 500) {
      markServer('offline', error instanceof Error ? error.message : String(error))
    }
    throw error
  }
}

export async function refreshLocalAgentStatus(): Promise<LocalAgentStatus | null> {
  if (!platform.isDesktop) {
    snapshot.localAgentChecked = true
    snapshot.localAgent = null
    snapshot.localAgentError = ''
    publish()
    return null
  }
  try {
    const status = await platform.localAgent.status()
    snapshot.localAgent = status
    snapshot.localAgentChecked = true
    snapshot.localAgentError = ''
    publish()
    return status
  } catch (error) {
    snapshot.localAgent = null
    snapshot.localAgentChecked = true
    snapshot.localAgentError = error instanceof Error ? error.message : String(error)
    publish()
    return null
  }
}

export async function probeServer(): Promise<void> {
  await serverGet('/auth/capabilities', { cache: false }).then(() => undefined)
}

function executionSessionKey(serverSessionId: string): string {
  return `agentmate.local-execution-session.v1.${serverSessionId}`
}

export function localExecutionSession(serverSessionId: string): string | undefined {
  return sessionStorage.getItem(executionSessionKey(serverSessionId)) || undefined
}

export function rememberLocalExecutionSession(serverSessionId: string, localSessionId: string): void {
  sessionStorage.setItem(executionSessionKey(serverSessionId), localSessionId)
}
