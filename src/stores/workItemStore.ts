// workItemStore — kanban / task items for the active project (§11 阶段 B).
import { create } from 'zustand'
import { api } from '../lib/api'
import type { WorkItem, WorkStatus } from '../lib/types'

interface WorkItemState {
  projectId: string | null
  items: WorkItem[]
  load: (projectId: string) => Promise<void>
  add: (title: string, status: WorkStatus) => Promise<void>
  move: (id: string, status: WorkStatus) => Promise<void>
  rename: (id: string, title: string) => Promise<void>
  remove: (id: string) => Promise<void>
}

export const useWorkItemStore = create<WorkItemState>((set, get) => ({
  projectId: null,
  items: [],

  load: async (projectId) => {
    set({ projectId, items: [] })
    try {
      const { items } = await api.listWorkItems(projectId)
      // guard against a stale response after the project changed
      if (get().projectId === projectId) set({ items })
    } catch {
      /* backend down */
    }
  },

  add: async (title, status) => {
    const pid = get().projectId
    if (!pid || !title.trim()) return
    const wi = await api.createWorkItem({ project_id: pid, title: title.trim(), status })
    set({ items: [...get().items, wi] })
  },

  // Optimistic move so the drag feels instant; reconcile from the server.
  move: async (id, status) => {
    set({ items: get().items.map((i) => (i.id === id ? { ...i, status } : i)) })
    const wi = await api.updateWorkItem(id, { status })
    set({ items: get().items.map((i) => (i.id === id ? wi : i)) })
  },

  rename: async (id, title) => {
    const wi = await api.updateWorkItem(id, { title })
    set({ items: get().items.map((i) => (i.id === id ? wi : i)) })
  },

  remove: async (id) => {
    set({ items: get().items.filter((i) => i.id !== id) })
    await api.deleteWorkItem(id).catch(() => {})
  },
}))
