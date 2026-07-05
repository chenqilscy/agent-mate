// Current account (M7 C1: real accounts on the shared backend). A Bearer token
// in localStorage identifies the user; no token → the backend's local owner, so
// the app works without ever logging in. Switching account reloads the app so
// every store re-fetches under the new identity.
import { create } from 'zustand'
import { api, TOKEN_KEY } from '../lib/api'
import type { Me } from '../lib/types'

interface AuthState {
  me: Me | null
  loggedIn: boolean
  load: () => Promise<void>
  login: (name: string, password: string) => Promise<void>
  register: (name: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  me: null,
  loggedIn: !!localStorage.getItem(TOKEN_KEY),

  load: async () => {
    try {
      set({ me: await api.me() })
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

  logout: async () => {
    await api.logout().catch(() => {})
    localStorage.removeItem(TOKEN_KEY)
    window.location.reload()
  },
}))
