import type { AgentRun, PersonalActionItemsResponse } from './types'

export type WorkbenchDataSource = 'live' | 'cache'

export interface WorkbenchDomainRead<T> {
  value: T
  source: WorkbenchDataSource
  updatedAt: number
}

export interface WorkbenchMergeState {
  actionItems: PersonalActionItemsResponse['items']
  unassignedItems: PersonalActionItemsResponse['unassigned']
  summary: PersonalActionItemsResponse['summary'] | null
  computedAt: number | null
  runs: AgentRun[]
  actionSource: WorkbenchDataSource | null
  runSource: WorkbenchDataSource | null
  actionUpdatedAt: number | null
  runUpdatedAt: number | null
}

export function selectCurrentWorkbenchRuns(runs: AgentRun[]): AgentRun[] {
  const seenWorkItems = new Set<string>()
  const seenSessions = new Set<string>()
  return [...runs]
    .sort((left, right) => (right.updated_at || right.created_at) - (left.updated_at || left.created_at))
    .filter((run) => {
      if (run.work_item_id) {
        if (seenWorkItems.has(run.work_item_id)) return false
        seenWorkItems.add(run.work_item_id)
        return true
      }
      if (seenSessions.has(run.session_id)) return false
      seenSessions.add(run.session_id)
      return true
    })
}

export function mergeWorkbenchDomains(
  current: WorkbenchMergeState,
  actions: PromiseSettledResult<WorkbenchDomainRead<PersonalActionItemsResponse>>,
  runs: PromiseSettledResult<WorkbenchDomainRead<{ runs: AgentRun[] }>>,
): WorkbenchMergeState {
  return {
    actionItems: actions.status === 'fulfilled' ? actions.value.value.items : current.actionItems,
    unassignedItems: actions.status === 'fulfilled' ? actions.value.value.unassigned : current.unassignedItems,
    summary: actions.status === 'fulfilled' ? actions.value.value.summary : current.summary,
    computedAt: actions.status === 'fulfilled' ? actions.value.value.computed_at : current.computedAt,
    runs: runs.status === 'fulfilled' ? runs.value.value.runs : current.runs,
    actionSource: actions.status === 'fulfilled' ? actions.value.source : current.actionSource,
    runSource: runs.status === 'fulfilled' ? runs.value.source : current.runSource,
    actionUpdatedAt: actions.status === 'fulfilled' ? actions.value.updatedAt : current.actionUpdatedAt,
    runUpdatedAt: runs.status === 'fulfilled' ? runs.value.updatedAt : current.runUpdatedAt,
  }
}
