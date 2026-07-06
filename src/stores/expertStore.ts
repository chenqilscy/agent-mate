// expertStore — 我的专家（自定义专家 · WB-049）。owner 维度，走后端持久化。
import { create } from 'zustand'
import { api } from '../lib/api'
import type { CustomExpert } from '../lib/types'

interface ExpertState {
  experts: CustomExpert[]
  loaded: boolean

  load: () => Promise<void>
  create: (body: { name: string; subtitle?: string; avatar?: string; intro?: string; persona?: string; tags?: string[] }) => Promise<CustomExpert>
  remove: (id: string) => Promise<void>
}

export const useExpertStore = create<ExpertState>((set, get) => ({
  experts: [],
  loaded: false,

  load: async () => {
    try {
      const { experts } = await api.listExperts()
      set({ experts, loaded: true })
    } catch {
      /* backend down — leave list as-is */
    }
  },

  create: async (body) => {
    const e = await api.createExpert(body)
    set({ experts: [e, ...get().experts] })
    return e
  },

  remove: async (id) => {
    await api.deleteExpert(id)
    set({ experts: get().experts.filter((e) => e.id !== id) })
  },
}))
