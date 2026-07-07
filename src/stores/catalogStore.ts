// catalogStore — 橱窗目录（WB-060）。
//
// 原 src/data/catalog.ts 的静态商品卡改由后端 /api/catalog 供给；此处以 catalog.ts 为「静态兜底」
// 初始值，启动时用接口数据覆盖（后端未连则保持兜底，绝不白屏）。zustand 响应式：接口数据到达后
// 消费组件自动重渲染（数据与迁移前逐字一致，无可见变化）。
// 注意：SKILLHUB_*（技能商店浏览列表）不在此——WB-064 负责其实时数据源，其消费仍从 data/catalog.ts 直取。
import { create } from 'zustand'
import { api } from '../lib/api'
import * as C from '../data/catalog'

// 由 API 供给的橱窗键（与后端 storage/db.showcase_all 对齐；不含 SKILLHUB_*）。
type Catalog = Pick<
  typeof C,
  | 'QUICK' | 'PROJ_TPL' | 'EXP_SCENES' | 'EXP_CATS' | 'EXP_GRID' | 'EXP_TEAMS'
  | 'SK_RECO' | 'SK_CATS' | 'SK_GRID' | 'CONNS' | 'CONN_META' | 'AUTO' | 'INSTALLED'
  | 'NP_TPLS' | 'NP_CONNS' | 'NP_EXPERTS' | 'READY_CONNECTORS' | 'NEEDS_TOKEN_CONNECTORS'
  | 'INSP_CATS' | 'INSP'
>

const FALLBACK: Catalog = {
  QUICK: C.QUICK, PROJ_TPL: C.PROJ_TPL, EXP_SCENES: C.EXP_SCENES, EXP_CATS: C.EXP_CATS,
  EXP_GRID: C.EXP_GRID, EXP_TEAMS: C.EXP_TEAMS, SK_RECO: C.SK_RECO, SK_CATS: C.SK_CATS,
  SK_GRID: C.SK_GRID, CONNS: C.CONNS, CONN_META: C.CONN_META, AUTO: C.AUTO,
  INSTALLED: C.INSTALLED, NP_TPLS: C.NP_TPLS, NP_CONNS: C.NP_CONNS, NP_EXPERTS: C.NP_EXPERTS,
  READY_CONNECTORS: C.READY_CONNECTORS, NEEDS_TOKEN_CONNECTORS: C.NEEDS_TOKEN_CONNECTORS,
  INSP_CATS: C.INSP_CATS, INSP: C.INSP,
}

// 后端把 Set 序列化成数组；这两项消费方用 .has()，回填时还原为 Set。
const SET_KEYS = new Set(['READY_CONNECTORS', 'NEEDS_TOKEN_CONNECTORS'])

interface CatalogState extends Catalog {
  loaded: boolean
  load: () => Promise<void>
}

export const useCatalogStore = create<CatalogState>((set) => ({
  ...FALLBACK,
  loaded: false,
  load: async () => {
    try {
      const raw = (await api.getCatalog()) as Record<string, unknown>
      const next: Record<string, unknown> = {}
      for (const k of Object.keys(FALLBACK)) {
        if (raw[k] === undefined) continue // 后端未提供某项 → 保留兜底
        next[k] = SET_KEYS.has(k) ? new Set(raw[k] as string[]) : raw[k]
      }
      set({ ...(next as Partial<CatalogState>), loaded: true })
    } catch {
      set({ loaded: true }) // 后端未连：保留静态兜底，不白屏
    }
  },
}))

// 便捷 hook：取整份目录（组件里按需解构，如 const { EXP_GRID } = useCatalog()）。
export function useCatalog(): Catalog {
  return useCatalogStore((s) => s)
}

// 启动即拉取一次（兜底已就绪，拉到后 set() 触发消费组件重渲染；失败保留兜底、不白屏）。
void useCatalogStore.getState().load()
