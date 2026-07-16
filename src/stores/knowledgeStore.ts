// knowledgeStore — 我的知识库（自托管 WeKnora RAG · WB-173/174）。真调 WeKnora（经本地 backend）。
// API Key 只在后端，前端只拿库/文档元数据。local-first：后端不可达就保持现状、不白屏。
import { create } from 'zustand'
import { api } from '../lib/api'
import type { KbDocument, KnowledgeBase } from '../lib/types'

interface KnowledgeState {
  kbs: KnowledgeBase[]
  loaded: boolean

  load: () => Promise<void>
  create: (body: { name: string; description?: string; icon?: string }) => Promise<string>
  remove: (id: string) => Promise<void>
  listDocs: (id: string) => Promise<KbDocument[]>
  uploadDoc: (id: string, file: File) => Promise<void>
  deleteDoc: (docId: string) => Promise<void>
}

export const useKnowledgeStore = create<KnowledgeState>((set, get) => ({
  kbs: [],
  loaded: false,

  load: async () => {
    try {
      const { list } = await api.listKb()
      set({ kbs: list, loaded: true })
    } catch {
      // 后端不可达 / 未接入 WeKnora（400）——保持现状，视图给引导，不白屏。
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
