import { create } from 'zustand'
import { api } from '../lib/api'
import type { ServerConnectionState } from '../lib/channels'
import type { AgentRun, PersonalActionItem, PersonalActionItemsResponse } from '../lib/types'
import { mergeWorkbenchDomains, type WorkbenchDataSource, type WorkbenchDomainRead } from '../lib/workbench'

function localDate(): string {
  const value = new Date()
  const pad = (part: number) => String(part).padStart(2, '0')
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
}

async function readServerDomain<T>(
  load: (onResolvedState: (state: ServerConnectionState) => void) => Promise<T>,
): Promise<WorkbenchDomainRead<T>> {
  let resolvedState: ServerConnectionState | null = null
  const value = await load((state) => { resolvedState = state })
  const server = resolvedState
  return {
    value,
    source: server?.state === 'cached' ? 'cache' : 'live',
    updatedAt: server?.state === 'cached' && server.cachedAt ? server.cachedAt : Date.now(),
  }
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
  actionSource: WorkbenchDataSource | null
  runSource: WorkbenchDataSource | null
  actionUpdatedAt: number | null
  runUpdatedAt: number | null
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
  actionSource: null,
  runSource: null,
  actionUpdatedAt: null,
  runUpdatedAt: null,

  load: async () => {
    set({ loading: true, actionError: null, runError: null })
    const [actions, runs] = await Promise.allSettled([
      readServerDomain((onResolvedState) => api.listPersonalActionItems(localDate(), { onResolvedState })),
      readServerDomain((onResolvedState) => api.listRuns(undefined, { onResolvedState })),
    ])
    set((current) => ({
      ...mergeWorkbenchDomains(current, actions, runs),
      loading: false,
      actionError: actions.status === 'rejected' ? 'Server 行动项读取失败' : null,
      runError: runs.status === 'rejected' ? 'Server Run 读取失败' : null,
    }))
  },

  clear: () => set({
    actionItems: [], unassignedItems: [], summary: null, computedAt: null, runs: [],
    loading: false, actionError: null, runError: null,
    actionSource: null, runSource: null, actionUpdatedAt: null, runUpdatedAt: null,
  }),
}))
