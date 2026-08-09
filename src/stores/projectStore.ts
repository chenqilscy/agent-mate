// projectStore — the project list + the active project being executed.
import { create } from 'zustand'
import { api } from '../lib/api'
import type { ProjectInfo } from '../lib/types'

interface ProjectState {
  projects: ProjectInfo[]
  active: ProjectInfo | null
  loading: boolean
  error: string | null
  updatedAt: number | null

  load: () => Promise<void>
  create: (body: { name: string; instruction: string; connectors: string[]; experts: string[]; skills: string[]; knowledge_ids: string[] }) => Promise<ProjectInfo>
  setActive: (p: ProjectInfo | null) => void
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  active: null,
  loading: false,
  error: null,
  updatedAt: null,

  load: async () => {
    set({ loading: true, error: null })
    try {
      const { projects } = await api.listProjects()
      set({ projects, loading: false, error: null, updatedAt: Date.now() })
    } catch {
      // Keep the last successful result, but never present it as live data.
      set({ loading: false, error: 'Server 项目读取失败' })
    }
  },

  create: async (body) => {
    const p = await api.createProject(body)
    set({ projects: [p, ...get().projects], error: null, updatedAt: Date.now() })
    return p
  },

  setActive: (p) => set({ active: p }),
}))
