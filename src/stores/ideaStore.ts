import { create } from 'zustand'
import { api } from '../lib/api'
import type { Idea, IdeaDetail, IdeaRelationType, IdeaSettlementType } from '../lib/types'
import { useWorkItemStore } from './workItemStore'

interface CreateIdeaInput {
  title?: string
  content: string
  project_id?: string | null
  tags?: string[]
  source_type?: string
  source_session_id?: string | null
  source_message_id?: string | null
}

interface IdeaState {
  ideas: Idea[]
  loaded: boolean
  loading: boolean
  load: () => Promise<void>
  createIdea: (input: CreateIdeaInput) => Promise<{ idea: Idea; created: boolean }>
  getDetail: (id: string) => Promise<IdeaDetail>
  updateIdea: (id: string, patch: Parameters<typeof api.updateIdea>[1]) => Promise<IdeaDetail>
  addRelation: (id: string, targetId: string, relation: IdeaRelationType) => Promise<IdeaDetail>
  removeRelation: (id: string, targetId: string, relation: IdeaRelationType) => Promise<IdeaDetail>
  applyProcessing: (id: string) => Promise<IdeaDetail>
  settle: (id: string, kind: IdeaSettlementType, memoryBaseSha256?: string) => Promise<IdeaDetail>
}

function upsert(items: Idea[], idea: Idea): Idea[] {
  return [idea, ...items.filter((item) => item.id !== idea.id)]
    .sort((a, b) => b.updated_at - a.updated_at)
}

export const useIdeaStore = create<IdeaState>((set, get) => ({
  ideas: [],
  loaded: false,
  loading: false,

  load: async () => {
    if (get().loading) return
    set({ loading: true })
    try {
      const { ideas } = await api.listIdeas()
      set({ ideas, loaded: true })
    } finally {
      set({ loading: false })
    }
  },

  createIdea: async (input) => {
    const result = await api.createIdea(input)
    set((state) => ({ ideas: upsert(state.ideas, result.idea), loaded: true }))
    return result
  },

  getDetail: (id) => api.getIdea(id),

  updateIdea: async (id, patch) => {
    const idea = await api.updateIdea(id, patch)
    set((state) => ({ ideas: upsert(state.ideas, idea) }))
    return idea
  },

  addRelation: async (id, targetId, relation) => {
    const idea = await api.addIdeaRelation(id, targetId, relation)
    set((state) => ({ ideas: upsert(state.ideas, idea) }))
    return idea
  },

  removeRelation: async (id, targetId, relation) => {
    const idea = await api.removeIdeaRelation(id, targetId, relation)
    set((state) => ({ ideas: upsert(state.ideas, idea) }))
    return idea
  },

  applyProcessing: async (id) => {
    const idea = await api.applyIdeaProcessing(id)
    set((state) => ({ ideas: upsert(state.ideas, idea) }))
    return idea
  },

  settle: async (id, kind, memoryBaseSha256 = '') => {
    const { idea } = await api.settleIdea(id, kind, memoryBaseSha256)
    set((state) => ({ ideas: upsert(state.ideas, idea) }))
    if (kind === 'work_item' && idea.project_id) {
      await useWorkItemStore.getState().load(idea.project_id)
    }
    return idea
  },
}))
