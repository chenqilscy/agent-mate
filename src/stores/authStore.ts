// Current Server-sourced account. A Server Bearer token in localStorage
// identifies the user; without one the backend exposes only an anonymous guest
// scope for local execution. Switching account reloads the app so every store
// re-fetches under the new identity.
import { create } from 'zustand'
import { api, TOKEN_KEY } from '../lib/api'
import type { Me } from '../lib/types'

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
    } catch {
      // Backend not up yet — leave null; the UI degrades gracefully.
    }
  },

  // login/register throw on failure (caller shows the error); on success they
  // persist the token and reload so all data re-fetches as the new user.
  login: async (name, password) => {
    const { token } = await api.login(name, password)
    localStorage.setItem(TOKEN_KEY, token)
    window.location.reload()
  },

  register: async (name, password) => {
    const { token } = await api.register(name, password)
    localStorage.setItem(TOKEN_KEY, token)
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
    await api.logout().catch(() => {})
    localStorage.removeItem(TOKEN_KEY)
    window.location.reload()
  },
}))
