// Current Server-sourced account. A Server Bearer token in localStorage
// identifies the user; without one the backend exposes only an anonymous guest
// scope for local execution. Switching account reloads the app so every store
// re-fetches under the new identity.
import { create } from 'zustand'
import { api, TOKEN_KEY } from '../lib/api'
import { ChannelUnavailableError, LOCAL_API_BASE } from '../lib/channels'
import type { Me } from '../lib/types'
import { platform } from '../platform'

async function bindLocalAgent(ownerId: string, token: string): Promise<void> {
  if (platform.isDesktop) {
    const bound = await platform.localAgent.bindIdentity(ownerId, token)
    if (!bound) throw new Error('Local Agent 拒绝绑定 Server 身份')
    return
  }
  // Browser development has no native IPC bridge. A normal authenticated local
  // request lets AuthMiddleware validate the Server token and bind the same
  // identity without exposing the protected Core IPC secret to JavaScript.
  await fetch(`${LOCAL_API_BASE}/me`, { headers: { Authorization: `Bearer ${token}` } }).then((response) => {
    if (!response.ok) throw new Error(`Local Agent identity bind failed (${response.status})`)
  })
}

interface AuthState {
  me: Me | null
  loggedIn: boolean
  load: () => Promise<void>
  login: (name: string, password: string) => Promise<void>
  register: (name: string, password: string) => Promise<void>
  ssoLogin: (provider: string, inviteCode?: string) => Promise<void>
  logout: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  me: null,
  loggedIn: !!localStorage.getItem(TOKEN_KEY),

  load: async () => {
    try {
      const me = await api.me()
      if (!me.authenticated) localStorage.removeItem(TOKEN_KEY)
      set({ me, loggedIn: me.authenticated })
      const token = localStorage.getItem(TOKEN_KEY)
      if (me.authenticated && token) await bindLocalAgent(me.id, token)
    } catch (error) {
      if (error instanceof ChannelUnavailableError && [401, 403].includes(error.status || 0)) {
        localStorage.removeItem(TOKEN_KEY)
        set({ me: null, loggedIn: false })
      }
      // Network outage keeps the signed-in flag and cached business view.
    }
  },

  // login/register throw on failure (caller shows the error); on success they
  // persist the token and reload so all data re-fetches as the new user.
  login: async (name, password) => {
    const { token, user } = await api.login(name, password)
    localStorage.setItem(TOKEN_KEY, token)
    try {
      await bindLocalAgent(user.id, token)
    } catch (error) {
      localStorage.removeItem(TOKEN_KEY)
      throw error
    }
    window.location.reload()
  },

  register: async (name, password) => {
    const { token, user } = await api.register(name, password)
    localStorage.setItem(TOKEN_KEY, token)
    try {
      await bindLocalAgent(user.id, token)
    } catch (error) {
      localStorage.removeItem(TOKEN_KEY)
      throw error
    }
    window.location.reload()
  },

  ssoLogin: async (provider, inviteCode = '') => {
    // Create the window synchronously inside the click gesture. Once noopener is
    // requested, browsers may legitimately return null even when navigation
    // succeeded, so the protocol never relies on a remote WindowProxy.
    const popup = window.open('', '_blank')
    if (!popup) throw new Error('popup_blocked')
    popup.opener = null
    try {
      const attempt = await api.ssoStart(provider, inviteCode)
      popup.location.replace(attempt.auth_url)
      const deadline = Math.min(attempt.expires_at * 1000, Date.now() + 10 * 60_000)
      while (Date.now() < deadline) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000))
        const result = await api.ssoPoll(attempt.attempt_id, attempt.attempt_token)
        if (result.status === 'error') throw new Error(result.error_code || 'sso_failed')
        if (result.status === 'completed') {
          localStorage.setItem(TOKEN_KEY, result.token)
          try {
            await bindLocalAgent(result.user.id, result.token)
          } catch (error) {
            localStorage.removeItem(TOKEN_KEY)
            throw error
          }
          popup.close()
          window.location.reload()
          return
        }
      }
      throw new Error('sso_timeout')
    } finally {
      popup.close()
    }
  },

  logout: async () => {
    const ownerId = useAuthStore.getState().me?.id
    if (ownerId && platform.isDesktop) await platform.localAgent.removeIdentity(ownerId).catch(() => false)
    await api.logout().catch(() => {})
    localStorage.removeItem(TOKEN_KEY)
    window.location.reload()
  },
}))
