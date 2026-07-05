// Composer settings: current model, permission mode, Plan/Ask toggles, and the
// live context-usage number (fed by the backend `usage` SSE event in M2, seeded
// here for M1 so the ring renders).
import { create } from 'zustand'
import type { ModelOption } from '../lib/types'

type Perm = '默认权限' | '完全访问权限'

interface UsageDetail {
  pct: number
  used: number
  total: number
  detail: Record<string, number>
}

interface SettingsState {
  model: string
  models: ModelOption[]
  maxMode: boolean
  perm: Perm
  planMode: boolean
  askMode: boolean
  usage: UsageDetail

  setModel: (name: string) => void
  setModels: (m: ModelOption[]) => void
  toggleMax: () => void
  setPerm: (p: Perm) => void
  setPlan: (on: boolean) => void
  setAsk: (on: boolean) => void
  setUsage: (u: Partial<UsageDetail>) => void
}

const MODEL_KEY = 'wb.model'

export const useSettingsStore = create<SettingsState>((set) => ({
  model: localStorage.getItem(MODEL_KEY) ?? 'DeepSeek-V4 Flash:deepseek-v4-flash',
  models: [],
  maxMode: false,
  perm: '默认权限',
  planMode: false,
  askMode: false,
  usage: { pct: 0, used: 0, total: 1_000_000, detail: {} },

  setModel: (name) => {
    localStorage.setItem(MODEL_KEY, name)
    set({ model: name })
  },
  setModels: (models) => set({ models }),
  toggleMax: () => set((s) => ({ maxMode: !s.maxMode })),
  setPerm: (perm) => set({ perm }),
  setPlan: (planMode) => set({ planMode }),
  setAsk: (askMode) => set({ askMode }),
  setUsage: (u) => set((s) => ({ usage: { ...s.usage, ...u } })),
}))
