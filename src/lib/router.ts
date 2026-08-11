import type { ViewId } from './types'

export interface AppRoute {
  view: ViewId
  projectId?: string
  sessionId?: string
  valid: boolean
}

export interface RouteOptions {
  projectId?: string
  sessionId?: string
  projectTab?: string
  replace?: boolean
  history?: boolean
}

const STATIC_ROUTES: Partial<Record<ViewId, string>> = {
  home: '/',
  assistant: '/assistants',
  projects: '/projects',
  experts: '/experts',
  skills: '/skills',
  connectors: '/connectors',
  automation: '/automations',
  inspire: '/inspiration',
  myfiles: '/files',
  kdocs: '/kdocs',
  knowledge: '/knowledge',
}

function clean(pathname: string): string {
  const path = pathname.replace(/\/+$/, '')
  return path || '/'
}

function part(value: string | undefined): string | undefined {
  if (!value) return undefined
  try { return decodeURIComponent(value) } catch { return undefined }
}

export function readRoute(pathname = window.location.pathname): AppRoute {
  const path = clean(pathname)
  const staticEntry = Object.entries(STATIC_ROUTES).find(([, p]) => p === path)
  if (staticEntry) return { view: staticEntry[0] as ViewId, valid: true }

  let m = path.match(/^\/chat\/([^/]+)$/)
  if (m && m[1] !== 'new') return { view: 'chat', sessionId: part(m[1]), valid: true }

  m = path.match(/^\/projects\/([^/]+)\/runs\/([^/]+)$/)
  if (m && m[2] !== 'new') {
    return {
      view: 'projexec',
      projectId: part(m[1]),
      sessionId: part(m[2]),
      valid: true,
    }
  }

  m = path.match(/^\/projects\/([^/]+)$/)
  if (m) return { view: 'project', projectId: part(m[1]), valid: true }

  return { view: 'home', valid: false }
}

export function pathForView(view: ViewId, opts: RouteOptions = {}): string {
  if (view === 'chat') return opts.sessionId ? `/chat/${encodeURIComponent(opts.sessionId)}` : '/'
  if (view === 'project') {
    if (!opts.projectId) return '/projects'
    const path = `/projects/${encodeURIComponent(opts.projectId)}`
    return opts.projectTab ? `${path}?tab=${encodeURIComponent(opts.projectTab)}` : path
  }
  if (view === 'projexec') {
    if (!opts.projectId) return '/projects'
    if (!opts.sessionId) return `/projects/${encodeURIComponent(opts.projectId)}`
    return `/projects/${encodeURIComponent(opts.projectId)}/runs/${encodeURIComponent(opts.sessionId)}`
  }
  return STATIC_ROUTES[view] ?? '/'
}
