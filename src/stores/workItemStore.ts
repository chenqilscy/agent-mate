// workItemStore — kanban / task items for the active project (§11 阶段 B).
import { create } from 'zustand'
import { api } from '../lib/api'
import { toast } from './toastStore'
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
    try {
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
      // 只在仍停留在同一项目时才落到当前看板，防迟到响应写错项目（WB-159）。
      if (get().projectId === pid) set({ items: [...get().items, wi] })
      return wi
    } catch {
      toast('新建任务失败，请重试')
      return null
    }
  },

  // Generic patch for the 待办详情 modal (description / status / due date / attachments).
  update: async (id, patch) => {
    const pid = get().projectId
    try {
      const wi = await api.updateWorkItem(id, patch)
      if (get().projectId === pid) set({ items: get().items.map((i) => (i.id === id ? wi : i)) })
    } catch {
      toast('保存失败，请重试')
    }
  },

  applyRemote: (item) => {
    // Ignore changes for a project whose board isn't loaded (it refetches on open).
    if (item.project_id !== get().projectId) return
    set({ items: get().items.map((i) => (i.id === item.id ? { ...i, status: item.status } : i)) })
  },

  // Optimistic move so the drag feels instant; reconcile from the server.
  // On failure roll the card back so the board doesn't silently drift out of sync
  // with the server until a reload (WB-159).
  move: async (id, status) => {
    const pid = get().projectId
    const prev = get().items.find((i) => i.id === id)?.status
    set({ items: get().items.map((i) => (i.id === id ? { ...i, status } : i)) })
    try {
      const wi = await api.updateWorkItem(id, { status })
      if (get().projectId === pid) set({ items: get().items.map((i) => (i.id === id ? wi : i)) })
    } catch {
      if (get().projectId === pid && prev) {
        set({ items: get().items.map((i) => (i.id === id ? { ...i, status: prev } : i)) })
      }
      toast('移动失败，已回滚')
    }
  },

  rename: async (id, title) => {
    const pid = get().projectId
    try {
      const wi = await api.updateWorkItem(id, { title })
      if (get().projectId === pid) set({ items: get().items.map((i) => (i.id === id ? wi : i)) })
    } catch {
      toast('重命名失败，请重试')
    }
  },

  remove: async (id) => {
    const pid = get().projectId
    const prev = get().items
    set({ items: get().items.filter((i) => i.id !== id) })
    try {
      await api.deleteWorkItem(id)
    } catch {
      // 删除失败 → 恢复，别让下次 reload 卡片「诈尸」还无提示（WB-159）。
      if (get().projectId === pid) set({ items: prev })
      toast('删除失败，已恢复')
    }
  },
}))
