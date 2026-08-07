// Server account and connectivity facade. Business requests go directly to the
// Server client; Local Agent is never used as a general authenticated proxy.
import { create } from 'zustand'
import { api } from '../lib/api'
import { TOKEN_KEY } from '../lib/api'
import { ChannelUnavailableError, channelSnapshot, probeServer, serverApiBase } from '../lib/channels'

interface ServerState {
  enabled: boolean // 本地 backend 是否已配 AGENTMATE_SERVER_URL
  consoleUrl: string
  linked: { account_id: string; name: string } | null // 是否已绑定某 Server 账号
  authState: 'unconfigured' | 'disconnected' | 'online' | 'offline_grace' | 'offline_expired' | 'revoked'
  onlineValidationTtl: number
  offlineGraceRemaining: number
  checked: boolean
  refreshStatus: () => Promise<void>
  connect: (name: string, password: string, register: boolean) => Promise<void> // 失败抛错
  disconnect: () => void
}

export const useServerStore = create<ServerState>((set) => ({
  enabled: false,
  consoleUrl: '',
  linked: null,
  authState: 'unconfigured',
  onlineValidationTtl: 30,
  offlineGraceRemaining: 0,
  checked: false,
  refreshStatus: async () => {
    try {
      await probeServer()
      const base = await serverApiBase()
      let me = null
      if (localStorage.getItem(TOKEN_KEY)) {
        try {
          me = await api.me()
        } catch (error) {
          if (error instanceof ChannelUnavailableError && [401, 403].includes(error.status || 0)) {
            localStorage.removeItem(TOKEN_KEY)
          } else {
            throw error
          }
        }
      }
      set({
        enabled: true,
        consoleUrl: base.replace(/\/api$/, '/'),
        linked: me ? { account_id: me.id, name: me.name } : null,
        authState: me ? 'online' : 'disconnected',
        onlineValidationTtl: 30,
        offlineGraceRemaining: 0,
        checked: true,
      })
    } catch {
      const linked = localStorage.getItem(TOKEN_KEY) ? useServerStore.getState().linked : null
      let configured = false
      let consoleUrl = ''
      try {
        const base = await serverApiBase()
        configured = true
        consoleUrl = base.replace(/\/api$/, '/')
      } catch { /* Desktop Local Agent has no Server origin configured. */ }
      set({
        checked: true,
        enabled: configured,
        consoleUrl,
        authState: linked && channelSnapshot().server.state === 'cached' ? 'offline_grace' : 'disconnected',
      })
    }
  },
  connect: async (name, password, register) => {
    const r = register ? await api.register(name.trim(), password) : await api.login(name.trim(), password)
    localStorage.setItem(TOKEN_KEY, r.token) // 以 Server 账号身份操作
    window.location.reload()
  },
  disconnect: () => {
    void api.logout().catch(() => {})
    localStorage.removeItem(TOKEN_KEY)
    set({ linked: null, authState: 'disconnected', offlineGraceRemaining: 0 })
    window.location.reload()
  },
}))
