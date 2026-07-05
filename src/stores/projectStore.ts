// projectStore — the project list + the active project being executed.
import { create } from 'zustand'
import { api } from '../lib/api'
import type { ProjectInfo } from '../lib/types'

interface ProjectState {
  projects: ProjectInfo[]
  active: ProjectInfo | null

  load: () => Promise<void>
  create: (body: { name: string; instruction: string; connectors: string[]; experts: string[]; skills: string[] }) => Promise<ProjectInfo>
  setActive: (p: ProjectInfo | null) => void
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  active: null,

  load: async () => {
    try {
      const { projects } = await api.listProjects()
      set({ projects })
    } catch {
      /* backend down */
    }
  },

  create: async (body) => {
    const p = await api.createProject(body)
    set({ projects: [p, ...get().projects] })
    return p
  },

  setActive: (p) => set({ active: p }),
}))
