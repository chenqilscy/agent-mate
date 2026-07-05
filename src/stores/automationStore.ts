// automationStore — scheduled / triggered agent runs (capability build, B).
import { create } from 'zustand'
import { api } from '../lib/api'
import type { Automation, CreateAutomationInput } from '../lib/types'

interface AutomationState {
  items: Automation[]
  loading: boolean
  load: () => Promise<void>
  create: (input: CreateAutomationInput) => Promise<Automation>
  toggle: (id: string, enabled: boolean) => Promise<void>
  update: (id: string, patch: Partial<CreateAutomationInput>) => Promise<void>
  remove: (id: string) => Promise<void>
  runNow: (id: string) => Promise<string | null>
}

export const useAutomationStore = create<AutomationState>((set, get) => ({
  items: [],
  loading: false,

  load: async () => {
    set({ loading: true })
    try {
      const { automations } = await api.listAutomations()
      set({ items: automations })
    } catch {
      /* backend down — keep whatever we have */
    } finally {
      set({ loading: false })
    }
  },

  create: async (input) => {
    const a = await api.createAutomation(input)
    set({ items: [a, ...get().items] })
    return a
  },

  // Optimistic toggle so the switch feels instant; reconcile from the server.
  toggle: async (id, enabled) => {
    set({ items: get().items.map((a) => (a.id === id ? { ...a, enabled } : a)) })
    try {
      const updated = await api.updateAutomation(id, { enabled })
      set({ items: get().items.map((a) => (a.id === id ? updated : a)) })
    } catch {
      set({ items: get().items.map((a) => (a.id === id ? { ...a, enabled: !enabled } : a)) })
    }
  },

  update: async (id, patch) => {
    const updated = await api.updateAutomation(id, patch)
    set({ items: get().items.map((a) => (a.id === id ? updated : a)) })
  },

  remove: async (id) => {
    set({ items: get().items.filter((a) => a.id !== id) })
    await api.deleteAutomation(id).catch(() => {})
  },

  runNow: async (id) => {
    const { session_id } = await api.runAutomation(id)
    // Reflect the run-now: pull fresh state (last_status/session) shortly after.
    get().load()
    return session_id
  },
}))
