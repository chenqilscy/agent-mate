// Composer settings: current model, permission mode, Plan/Ask toggles, and the
// live context-usage number (fed by the backend `usage` SSE event in M2, seeded
// here for M1 so the ring renders).
import { create } from 'zustand'
import { api } from '../lib/api'
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
  reloadModels: () => Promise<void>
  toggleMax: () => void
  setPerm: (p: Perm) => void
  setPlan: (on: boolean) => void
  setAsk: (on: boolean) => void
  setUsage: (u: Partial<UsageDetail>) => void
}

const MODEL_KEY = 'wb.model'

export const useSettingsStore = create<SettingsState>((set) => ({
  // 选择键（WB-128）：'' = 默认(.env 兜底) · '@provider:model' · 自定义名。空串=跟随后端默认。
  model: localStorage.getItem(MODEL_KEY) ?? '',
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
  // 增删改/隐藏后重拉 picker 列表（只含可见项）。WB-124。
  reloadModels: async () => {
    try {
      const r = await api.models()
      set({ models: r.models })
    } catch {
      /* 离线/后端不可达：保留现有列表，不清空 */
    }
  },
  toggleMax: () => set((s) => ({ maxMode: !s.maxMode })),
  setPerm: (perm) => set({ perm }),
  // Plan and Ask are modes, not independent capabilities. Turning one on must
  // turn the other off so the UI never sends contradictory system contracts.
  setPlan: (planMode) => set((s) => ({ planMode, askMode: planMode ? false : s.askMode })),
  setAsk: (askMode) => set((s) => ({ askMode, planMode: askMode ? false : s.planMode })),
  setUsage: (u) => set((s) => ({ usage: { ...s.usage, ...u } })),
}))
