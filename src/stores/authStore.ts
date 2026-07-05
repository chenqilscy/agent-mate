// Current user & role (M1: the local user stub from the backend). UI reads role
// from here; when real accounts land in M7 only the backend changes.
import { create } from 'zustand'
import { api } from '../lib/api'
import type { Me } from '../lib/types'

interface AuthState {
  me: Me | null
  load: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set) => ({
  me: null,
  load: async () => {
    try {
      const me = await api.me()
      set({ me })
    } catch {
      // Backend not up yet — leave null; the UI degrades gracefully.
    }
  },
}))
