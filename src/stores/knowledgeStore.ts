// knowledgeStore — 我的知识库（GLM RAG · WB-144）。owner 维度，真调 GLM（经本地 backend）。
// key 只在后端，前端只拿库/文档元数据。local-first：后端不可达就保持现状、不白屏。
import { create } from 'zustand'
import { api } from '../lib/api'
import type { KbCapacity, KbDocument, KnowledgeBase } from '../lib/types'

interface KnowledgeState {
  kbs: KnowledgeBase[]
  capacity: KbCapacity | null
  loaded: boolean

  load: () => Promise<void>
  create: (body: { name: string; description?: string; embedding_id?: number; contextual?: number; icon?: string; background?: string }) => Promise<string>
  remove: (id: string) => Promise<void>
  listDocs: (id: string) => Promise<KbDocument[]>
  uploadDoc: (id: string, file: File) => Promise<void>
  deleteDoc: (docId: string) => Promise<void>
}

export const useKnowledgeStore = create<KnowledgeState>((set, get) => ({
  kbs: [],
  capacity: null,
  loaded: false,

  load: async () => {
    try {
      const [{ list }, capacity] = await Promise.all([api.listKb(), api.kbCapacity().catch(() => null)])
      set({ kbs: list, capacity: capacity ?? get().capacity, loaded: true })
    } catch {
      // 后端不可达 / 未配智谱 key（400）——保持现状，视图给引导，不白屏。
      set({ loaded: true })
    }
  },

  create: async (body) => {
    const { id } = await api.createKb(body)
    await get().load()
    return id
  },

  remove: async (id) => {
    await api.deleteKb(id)
    set({ kbs: get().kbs.filter((k) => k.id !== id) })
    get().load()
  },

  listDocs: (id) => api.listKbDocs(id).then((r) => r.list),

  uploadDoc: async (id, file) => {
    await api.uploadKbDoc(id, file, file.name)
  },

  deleteDoc: async (docId) => {
    await api.deleteKbDoc(docId)
  },
}))
