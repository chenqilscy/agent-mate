import { create } from 'zustand'
import { api } from '../lib/api'
import type { AgentRun, PersonalActionItem, PersonalActionItemsResponse } from '../lib/types'

function localDate(): string {
  const value = new Date()
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
}

interface WorkbenchState {
  actionItems: PersonalActionItem[]
  unassignedItems: PersonalActionItem[]
  summary: PersonalActionItemsResponse['summary'] | null
  computedAt: number | null
  runs: AgentRun[]
  loading: boolean
  actionError: string | null
  runError: string | null
  updatedAt: number | null
  load: () => Promise<void>
  clear: () => void
}

export const useWorkbenchStore = create<WorkbenchState>((set) => ({
  actionItems: [],
  unassignedItems: [],
  summary: null,
  computedAt: null,
  runs: [],
  loading: false,
  actionError: null,
  runError: null,
  updatedAt: null,

  load: async () => {
    set({ loading: true, actionError: null, runError: null })
    const [actions, runs] = await Promise.allSettled([
      api.listPersonalActionItems(localDate()),
      api.listRuns(),
    ])
    set((current) => ({
      actionItems: actions.status === 'fulfilled' ? actions.value.items : current.actionItems,
      unassignedItems: actions.status === 'fulfilled' ? actions.value.unassigned : current.unassignedItems,
      summary: actions.status === 'fulfilled' ? actions.value.summary : current.summary,
      computedAt: actions.status === 'fulfilled' ? actions.value.computed_at : current.computedAt,
      runs: runs.status === 'fulfilled' ? runs.value.runs : current.runs,
      loading: false,
      actionError: actions.status === 'rejected' ? 'Server 行动项读取失败' : null,
      runError: runs.status === 'rejected' ? 'Server Run 读取失败' : null,
      updatedAt: actions.status === 'fulfilled' || runs.status === 'fulfilled' ? Date.now() : current.updatedAt,
    }))
  },

  clear: () => set({
    actionItems: [], unassignedItems: [], summary: null, computedAt: null, runs: [],
    loading: false, actionError: null, runError: null, updatedAt: null,
  }),
}))
