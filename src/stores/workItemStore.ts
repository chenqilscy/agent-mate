// workItemStore — kanban / task items for the active project (§11 阶段 B).
import { create } from 'zustand'
import { api } from '../lib/api'
import type { Milestone, WorkAttachment, WorkItem, WorkPriority, WorkStatus } from '../lib/types'

export interface NewWorkItem {
  title: string
  status?: WorkStatus
  description?: string
  due_date?: string | null
  attachments?: WorkAttachment[]
  priority?: WorkPriority
  start_date?: string | null
  labels?: string[]
  parent_id?: string
  milestone_id?: string
}

export interface WorkItemPatch {
  title?: string
  status?: WorkStatus
  description?: string
  due_date?: string | null
  attachments?: WorkAttachment[]
  priority?: WorkPriority
  start_date?: string | null
  labels?: string[]
  milestone_id?: string
  estimate_h?: number
  spent_h?: number
}

interface WorkItemState {
  projectId: string | null
  items: WorkItem[]
  milestones: Milestone[]
  load: (projectId: string) => Promise<void>
  loadMilestones: (projectId: string) => Promise<void>
  addMilestone: (name: string, due_date?: string | null) => Promise<Milestone | null>
  add: (input: NewWorkItem) => Promise<WorkItem | null>
  update: (id: string, patch: WorkItemPatch) => Promise<void>
  // Apply a live change pushed over SSE (WB-031: agent changed a plan item's
  // status). Local-only, no API call; scoped to the active project.
  applyRemote: (item: { id: string; project_id: string; status: WorkStatus }) => void
  move: (id: string, status: WorkStatus) => Promise<void>
  rename: (id: string, title: string) => Promise<void>
  remove: (id: string) => Promise<void>
}

export const useWorkItemStore = create<WorkItemState>((set, get) => ({
  projectId: null,
  items: [],
  milestones: [],

  load: async (projectId) => {
    set({ projectId, items: [], milestones: [] })
    try {
      const { items } = await api.listWorkItems(projectId)
      // guard against a stale response after the project changed
      if (get().projectId === projectId) set({ items })
    } catch {
      /* backend down */
    }
    void get().loadMilestones(projectId)
  },

  loadMilestones: async (projectId) => {
    try {
      const { milestones } = await api.listMilestones(projectId)
      if (get().projectId === projectId) set({ milestones })
    } catch {
      /* backend down / no milestones */
    }
  },

  addMilestone: async (name, due_date = null) => {
    const pid = get().projectId
    if (!pid || !name.trim()) return null
    try {
      const m = await api.createMilestone({ project_id: pid, name: name.trim(), due_date })
      set({ milestones: [...get().milestones, m] })
      return m
    } catch {
      return null
    }
  },

  add: async (input) => {
    const pid = get().projectId
    if (!pid || !input.title.trim()) return null
    const wi = await api.createWorkItem({
      project_id: pid,
      title: input.title.trim(),
      status: input.status,
      description: input.description,
      due_date: input.due_date,
      attachments: input.attachments,
      priority: input.priority,
      start_date: input.start_date,
      labels: input.labels,
      parent_id: input.parent_id,
      milestone_id: input.milestone_id,
    })
    set({ items: [...get().items, wi] })
    return wi
  },

  // Generic patch for the 待办详情 modal (description / status / due date / attachments).
  update: async (id, patch) => {
    const wi = await api.updateWorkItem(id, patch)
    set({ items: get().items.map((i) => (i.id === id ? wi : i)) })
  },

  applyRemote: (item) => {
    // Ignore changes for a project whose board isn't loaded (it refetches on open).
    if (item.project_id !== get().projectId) return
    set({ items: get().items.map((i) => (i.id === item.id ? { ...i, status: item.status } : i)) })
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
