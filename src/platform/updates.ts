import { platform, type UpdateResult } from './index'

export type UpdatePreferences = {
  endpoint: string
  channel: 'stable' | 'beta'
  automatic: boolean
  deviceId: string
}
const PREFS_KEY = 'agentmate.desktopUpdate.preferences.v1'
const LAST_CHECK_KEY = 'agentmate.desktopUpdate.lastCheck.v1'
const LAST_RESULT_KEY = 'agentmate.desktopUpdate.lastResult.v1'
const AUTO_INTERVAL_MS = 24 * 60 * 60 * 1000

const createDeviceId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `device-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}

export function getUpdatePreferences(): UpdatePreferences {
  const fallback: UpdatePreferences = {
    endpoint: String(import.meta.env.VITE_AGENTMATE_UPDATE_ENDPOINT || '').trim().replace(/\/$/, ''),
    channel: 'stable',
    automatic: true,
    deviceId: createDeviceId(),
  }
  try {
    const value = JSON.parse(localStorage.getItem(PREFS_KEY) || '{}') as Partial<UpdatePreferences>
    const next = {
      endpoint: typeof value.endpoint === 'string' ? value.endpoint.trim().replace(/\/$/, '') : fallback.endpoint,
      channel: value.channel === 'beta' ? 'beta' as const : 'stable' as const,
      automatic: typeof value.automatic === 'boolean' ? value.automatic : true,
      deviceId: typeof value.deviceId === 'string' && value.deviceId.length >= 8 ? value.deviceId : fallback.deviceId,
    }
    localStorage.setItem(PREFS_KEY, JSON.stringify(next))
    return next
  } catch {
    localStorage.setItem(PREFS_KEY, JSON.stringify(fallback))
    return fallback
  }
}

export function saveUpdatePreferences(value: UpdatePreferences): UpdatePreferences {
  const next = { ...value, endpoint: value.endpoint.trim().replace(/\/$/, '') }
  localStorage.setItem(PREFS_KEY, JSON.stringify(next))
  return next
}

export function getLastUpdateResult(): UpdateResult | null {
  try { return JSON.parse(localStorage.getItem(LAST_RESULT_KEY) || 'null') as UpdateResult | null }
  catch { return null }
}

function publishResult(result: UpdateResult) {
  localStorage.setItem(LAST_RESULT_KEY, JSON.stringify(result))
  window.dispatchEvent(new CustomEvent('agentmate:update-status', { detail: result }))
}

function errorCode(error: unknown, install: boolean) {
  const message = error instanceof Error ? error.message.toLowerCase() : String(error).toLowerCase()
  if (message.includes('signature')) return 'signature_invalid'
  if (message.includes('timeout')) return 'timeout'
  if (message.includes('network') || message.includes('connect')) return 'network_error'
  return install ? 'install_failed' : 'check_failed'
}

async function reportFailure(prefs: UpdatePreferences, result: UpdateResult | null, code: string, install: boolean) {
  if (!prefs.endpoint) return
  try {
    await fetch(`${prefs.endpoint}/api/desktop-updates/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-AgentMate-Device': prefs.deviceId },
      body: JSON.stringify({
        channel: prefs.channel,
        event: install ? 'install_failed' : 'download_failed',
        current_version: result?.current_version || '',
        release_id: result?.release_id || null,
        error_code: code,
      }),
    })
  } catch { /* update telemetry must never block local use */ }
}

export async function checkDesktopUpdate(prefs: UpdatePreferences, install = false): Promise<UpdateResult> {
  if (!platform.isDesktop) return { status: 'unsupported' }
  if (!prefs.endpoint) throw new Error('尚未配置桌面更新服务地址')
  const previous = getLastUpdateResult()
  try {
    const result = await platform.checkForUpdates({ ...prefs, install })
    publishResult(result)
    return result
  } catch (error) {
    void reportFailure(prefs, previous, errorCode(error, install), install)
    throw error
  }
}

export function startAutomaticUpdateCheck() {
  if (!platform.isDesktop) return
  const prefs = getUpdatePreferences()
  if (!prefs.automatic || !prefs.endpoint) return
  const key = `${prefs.endpoint}|${prefs.channel}`
  try {
    const last = JSON.parse(localStorage.getItem(LAST_CHECK_KEY) || '{}') as { key?: string; at?: number }
    if (last.key === key && Date.now() - Number(last.at || 0) < AUTO_INTERVAL_MS) return
  } catch { /* perform a fresh check */ }
  localStorage.setItem(LAST_CHECK_KEY, JSON.stringify({ key, at: Date.now() }))
  void checkDesktopUpdate(prefs).then((result) => {
    if (result.status === 'available') {
      platform.notify('AgentMate 有可用更新', `${result.version || '新版本'} 已准备好，可在设置中心安装。`)
    }
  }).catch(() => { /* visible in settings; startup remains usable */ })
}
